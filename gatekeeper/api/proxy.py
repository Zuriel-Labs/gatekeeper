"""Google API proxy — policy-enforced request forwarding."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from gatekeeper.google_client import credential_manager
from gatekeeper.logging import log_request
from gatekeeper.models import ApiKey
from gatekeeper.modules import get_loaded_modules, load_module
from gatekeeper.policy import PolicyEngine

logger = logging.getLogger(__name__)

# Google API base URL
GOOGLE_API_BASE = "https://www.googleapis.com"

# Module name to API service path prefix mapping
MODULE_API_MAP = {
    "drive": "/drive/v3",
    "gmail": "/gmail/v1",
    "calendar": "/calendar/v3",
}

# File download storage for binary responses larger than max_inline_size_mb
DOWNLOAD_DIR = Path(
    os.environ.get(
        "GATEKEEPER_DOWNLOAD_DIR",
        os.path.expanduser("~/.gatekeeper/downloads"),
    )
)


class GoogleProxy:
    """Proxies requests to Google APIs through the policy engine."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.policy_engine = PolicyEngine(session)

    async def call_google(
        self,
        module_name: str,
        route_id: str,
        params: dict[str, Any],
        api_key_record: ApiKey,
        request_path: str = "",
        request_method: str = "GET",
    ) -> JSONResponse:
        """Proxy a request to Google API through the policy engine.

        1. Check policy (allow/deny)
        2. Apply request transforms
        3. Get Google credentials
        4. Call Google API
        5. Apply response filters
        6. Log to audit
        7. Return filtered response with correct HTTP status code

        Returns a JSONResponse with the appropriate HTTP status code.
        """
        # Check policy
        decision = await self.policy_engine.check_route(
            module_name, route_id, api_key_record.permissions
        )

        if not decision.allowed:
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=403,
                response_summary=decision.reason,
                response_message=decision.reason,
            )
            return JSONResponse(
                status_code=403,
                content={"error": True, "status": 403, "message": decision.reason},
            )

        # Find the module and route
        modules = get_loaded_modules()
        module = modules.get(module_name)
        if not module:
            module = load_module(module_name)
            if not module:
                await log_request(
                    api_key_prefix=api_key_record.key_prefix,
                    module=module_name,
                    route=route_id,
                    method=request_method,
                    path=request_path,
                    status_code=404,
                    response_summary=f"Module {module_name} not found",
                    response_message=f"Module {module_name} not found",
                )
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": True,
                        "status": 404,
                        "message": f"Module {module_name} not found",
                    },
                )

        route = None
        for r in module.get_routes():
            if r.route_id == route_id:
                route = r
                break

        if not route:
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=404,
                response_summary=f"Route {route_id} not found",
                response_message=f"Route {route_id} not found",
            )
            return JSONResponse(
                status_code=404,
                content={"error": True, "status": 404, "message": f"Route {route_id} not found"},
            )

        # Inject schema defaults for params the caller didn't provide.
        # This must happen BEFORE policy transforms so that defaults can be
        # capped/overridden by policy (e.g., maxResults capping pageSize).
        schema_props = route.input_schema.get("properties", {})
        for schema_key, schema_val in schema_props.items():
            if "default" in schema_val and schema_key not in params:
                params[schema_key] = schema_val["default"]

        # Apply request transforms (policy caps, overrides, etc.)
        transformed_params = self.policy_engine.apply_request_transforms(
            params, decision.policy_config
        )

        # Get Google credentials
        creds = credential_manager.get_credentials()
        if not creds or not creds.token:
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=401,
                response_summary="Google credentials not configured",
                response_message="Google credentials not configured. Run 'gatekeeper auth'.",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": True,
                    "status": 401,
                    "message": ("Google credentials not configured. Run 'gatekeeper auth'."),
                },
            )

        # Build Google API URL
        # Normalize param keys: snake_case → camelCase to match google_path placeholders
        # e.g., "file_id" → "fileId", "calendar_id" → "calendarId"
        normalized_params = {}
        for key, value in transformed_params.items():
            parts = key.split("_")
            camel_key = parts[0] + "".join(p.capitalize() for p in parts[1:])
            normalized_params[camel_key] = value

        # Coerce array-type parameters that arrive as strings back to lists.
        # MCP clients may stringify JSON arrays in tool arguments, and the
        # direct REST API can also receive strings for array fields.
        # Uses the route's input_schema to identify which params should be arrays.
        schema_props = route.input_schema.get("properties", {})
        # Map snake_case schema keys to their camelCase counterparts
        schema_key_map = {}
        for schema_key, schema_val in schema_props.items():
            parts = schema_key.split("_")
            camel = parts[0] + "".join(p.capitalize() for p in parts[1:])
            schema_key_map[camel] = schema_val

        for key in list(normalized_params.keys()):
            value = normalized_params[key]
            # Check if this param is defined as array type in the schema
            prop_schema = schema_key_map.get(key, {})
            if prop_schema.get("type") == "array" and isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        normalized_params[key] = parsed
                    # If parsed isn't a list, leave as-is (let Google API reject it)
                except (json.JSONDecodeError, TypeError):
                    # Not valid JSON — leave as string and let the API reject it
                    pass

        # Replace path parameters (e.g., {calendarId} -> actual value) in google_path
        google_path = route.google_path
        for key, value in list(normalized_params.items()):
            placeholder = "{" + key + "}"
            if placeholder in google_path:
                google_path = google_path.replace(placeholder, str(value))
                del normalized_params[key]

        # Binary download routes: inject alt=media so Google serves raw bytes.
        # export routes have their own alt param via mime_type – skip those.
        if route.binary_response and "export" not in route.route_id:
            normalized_params["alt"] = "media"

        # Construct the final URL
        # Per-route base_url (set on Sheets/Docs/Slides routes) takes priority
        # over the global GOOGLE_API_BASE; everything else falls back to the
        # default Google API host. This is the only URL-construction change
        # needed to support APIs on different hostnames.
        base = route.base_url or GOOGLE_API_BASE
        if route.google_path.startswith("/"):
            # google_path already includes full API path (e.g., /calendar/v3/...)
            url = f"{base}{google_path}"
        else:
            # Relative path — prepend the module API prefix
            api_prefix = MODULE_API_MAP.get(module_name, f"/{module_name}/v1")
            url = f"{base}{api_prefix}/{google_path}"

        # Remove path params from normalized_params — remaining ones are query/body params
        # (path params were already extracted and substituted above)

        # Gmail filter routes need special body transformation:
        # The Gmail API expects nested {criteria: {...}, action: {...}} but
        # the proxy receives flat parameters. Restructure before sending.
        if route_id in ("gmail.filters.create", "gmail.filters.update"):
            normalized_params = self._restructure_filter_body(normalized_params)

        # Drive shortcut creation: when mimeType is shortcut and shortcutTargetId
        # is provided, construct the shortcutDetails object that the Drive API
        # requires. Without this, creating a shortcut returns 400 Bad Request.
        if route_id == "drive.files.create" and "shortcutTargetId" in normalized_params:
            shortcut_details = {"targetId": normalized_params.pop("shortcutTargetId")}
            if "shortcutTargetMimeType" in normalized_params:
                shortcut_details["targetMimeType"] = normalized_params.pop("shortcutTargetMimeType")
            normalized_params["shortcutDetails"] = shortcut_details

        # Generic per-route body transform. Routes declare a method name on
        # GoogleProxy that takes normalized_params and returns the new body.
        # Used when the user-friendly input schema differs from the Google
        # API's required request shape (e.g., sheets spreadsheets.create
        # needs the body to be a Spreadsheet resource, not flat fields).
        if route.body_transform:
            transform_method = getattr(self, route.body_transform, None)
            if transform_method is None:
                # Programmer error in the route definition — surface it loudly
                # rather than forwarding a wrong-shape body to Google.
                raise RuntimeError(
                    f"Route {route_id} declares body_transform={route.body_transform!r} "
                    f"but GoogleProxy has no such method"
                )
            normalized_params = transform_method(normalized_params)

        # Some routes (e.g. drive.files.update) require certain params to be
        # sent as URL query parameters rather than in the JSON body.
        # Google's API silently ignores addParents/removeParents if they're
        # in the PATCH body — they MUST be query params.
        # Route definitions use snake_case, but normalized params use camelCase,
        # so compare against the camelCase form of each configured query param.
        query_params = {}
        body_params = {}
        camel_query_keys = {
            parts[0] + "".join(p.capitalize() for p in parts[1:])
            for qp in route.query_params
            for parts in [qp.split("_")]
        }
        for key, value in normalized_params.items():
            if key in camel_query_keys:
                query_params[key] = value
            else:
                body_params[key] = value

        # Make the request
        headers = {"Authorization": f"Bearer {creds.token}"}

        # Multipart upload: build multipart/related body
        multipart_body = None
        if route.multipart_upload:
            query_params["uploadType"] = "multipart"

            b64_content = body_params.pop("base64Content", None)
            if not b64_content or not isinstance(b64_content, str):
                await log_request(
                    api_key_prefix=api_key_record.key_prefix,
                    module=module_name,
                    route=route_id,
                    method=request_method,
                    path=request_path,
                    status_code=400,
                    response_summary="Missing required base64_content parameter",
                    response_message="Missing required 'base64_content' parameter",
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": True,
                        "status": 400,
                        "message": "Missing required 'base64_content' parameter",
                    },
                )
            try:
                file_bytes = base64.b64decode(b64_content)
            except Exception:
                await log_request(
                    api_key_prefix=api_key_record.key_prefix,
                    module=module_name,
                    route=route_id,
                    method=request_method,
                    path=request_path,
                    status_code=400,
                    response_summary="Invalid base64 content",
                    response_message="Invalid base64 content",
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": True,
                        "status": 400,
                        "message": "Invalid base64 content",
                    },
                )

            # Check size against policy
            size_mb = len(file_bytes) / (1024 * 1024)
            max_size = float(decision.policy_config.get("max_file_size_mb", 25))
            if size_mb > max_size:
                await log_request(
                    api_key_prefix=api_key_record.key_prefix,
                    module=module_name,
                    route=route_id,
                    method=request_method,
                    path=request_path,
                    status_code=413,
                    response_summary=f"File size {size_mb:.2f} MB exceeds max {max_size} MB",
                    response_message=f"File size {size_mb:.2f} MB exceeds max {max_size} MB",
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": True,
                        "status": 413,
                        "message": f"File size {size_mb:.2f} MB exceeds max {max_size} MB",
                    },
                )

            # Build metadata JSON from remaining body params
            metadata = {}
            metadata_fields = {"name", "mimeType", "parents", "description"}
            for key in list(body_params.keys()):
                if key in metadata_fields:
                    metadata[key] = body_params.pop(key)

            # Guess mime_type from filename if not provided
            if "mimeType" not in metadata:
                guessed, _ = mimetypes.guess_type(metadata.get("name", ""))
                if guessed:
                    metadata["mimeType"] = guessed

            metadata_json = json.dumps(metadata, separators=(",", ":"))

            # Build multipart body
            boundary = f"gatekeeper_boundary_{uuid.uuid4().hex}"
            mime_type = metadata.get("mimeType", "application/octet-stream")

            buf = io.BytesIO()
            buf.write(f"--{boundary}\r\n".encode())
            buf.write(b"Content-Type: application/json; charset=UTF-8\r\n\r\n")
            buf.write(metadata_json.encode("utf-8"))
            buf.write(f"\r\n--{boundary}\r\n".encode())
            buf.write(f"Content-Type: {mime_type}\r\n\r\n".encode())
            buf.write(file_bytes)
            buf.write(f"\r\n--{boundary}--\r\n".encode())
            multipart_body = buf.getvalue()

            headers["Content-Type"] = f"multipart/related; boundary={boundary}"

        try:
            async with httpx.AsyncClient() as client:
                if route.method == "GET":
                    # For GET requests, all params go as query params (no body)
                    all_query = {**query_params, **body_params}
                    response = await client.get(url, params=all_query, headers=headers)
                elif route.method == "POST":
                    if multipart_body is not None:
                        response = await client.post(
                            url, params=query_params, content=multipart_body, headers=headers
                        )
                    else:
                        response = await client.post(
                            url, params=query_params or None, json=body_params, headers=headers
                        )
                elif route.method == "PATCH":
                    response = await client.patch(
                        url,
                        params=query_params or None,
                        json=body_params or None,
                        headers=headers,
                    )
                elif route.method == "DELETE":
                    response = await client.delete(
                        url, params=query_params or None, headers=headers
                    )
                elif route.method == "PUT":
                    response = await client.put(
                        url, params=query_params or None, json=body_params or None, headers=headers
                    )
                else:
                    response = await client.request(
                        route.method,
                        url,
                        params=query_params or None,
                        json=body_params or None,
                        headers=headers,
                    )

            # Handle binary responses (exports, downloads) vs JSON responses
            if route.binary_response:
                result = self._handle_binary_response(
                    response=response,
                    file_id=params.get("file_id", "unknown"),
                    route_id=route_id,
                    decision=decision,
                )
                await log_request(
                    api_key_prefix=api_key_record.key_prefix,
                    module=module_name,
                    route=route_id,
                    method=request_method,
                    path=request_path,
                    status_code=response.status_code,
                    response_summary=result.get("summary", "binary")
                    if isinstance(result, dict)
                    else "binary",
                )
                return JSONResponse(status_code=response.status_code, content=result)

            # Parse JSON response
            try:
                response_data = response.json()
            except Exception:
                response_data = {"raw_response": response.text}

            # Apply response filters
            if isinstance(response_data, dict):
                response_data = self.policy_engine.apply_response_filter(
                    response_data, decision.policy_config
                )

            # Log successful request
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=response.status_code,
                response_summary=str(response_data)[:200] if response_data else None,
            )

            # Return with the Google API's status code
            return JSONResponse(status_code=response.status_code, content=response_data)

        except httpx.HTTPError as e:
            logger.error(f"Google API request failed: {e}")
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=502,
                response_summary=f"HTTP error: {str(e)[:150]}",
                response_message=f"Google API request failed: {e}",
            )
            return JSONResponse(
                status_code=502,
                content={
                    "error": True,
                    "status": 502,
                    "message": f"Google API request failed: {e}",
                },
            )

        except Exception as e:
            logger.error(f"Unexpected error in proxy: {e}")
            await log_request(
                api_key_prefix=api_key_record.key_prefix,
                module=module_name,
                route=route_id,
                method=request_method,
                path=request_path,
                status_code=500,
                response_summary=f"Internal error: {str(e)[:150]}",
                response_message=f"Internal error: {e}",
            )
            return JSONResponse(
                status_code=500,
                content={"error": True, "status": 500, "message": f"Internal error: {e}"},
            )

    def _handle_binary_response(
        self,
        response: httpx.Response,
        file_id: str,
        route_id: str,
        decision: Any,
    ) -> dict[str, Any]:
        """Handle binary responses: inline base64 or save to disk.

        Uses the ``max_inline_size_mb`` policy key (defaults to 1) to decide
        whether to base64-encode the file in the JSON response or save it
        to the download directory and return a file path.

        Also handles error responses from Google (which are JSON even for
        binary routes).
        """
        # Google may return JSON errors for binary routes
        content_type = response.headers.get("content-type", "").lower()
        if response.status_code != 200 or "json" in content_type:
            try:
                return response.json()
            except Exception:
                return {
                    "error": True,
                    "status": response.status_code,
                    "message": response.text,
                }

        raw_bytes = response.content
        size_mb = len(raw_bytes) / (1024 * 1024)
        threshold_mb = float(decision.policy_config.get("max_inline_size_mb", 1))

        # Derive a filename
        content_disposition = response.headers.get("content-disposition", "")
        filename = None
        if "filename=" in content_disposition:
            filename = content_disposition.split("filename=")[-1].strip('"')
        if not filename:
            # Try to guess from Content-Type
            ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ".bin"
            filename = f"{file_id}{ext}"

        # Under threshold → inline base64
        if size_mb <= threshold_mb:
            return {
                "content_type": content_type.split(";")[0].strip(),
                "size_bytes": len(raw_bytes),
                "base64": base64.b64encode(raw_bytes).decode("ascii"),
                "filename": filename,
            }

        # Over threshold → save to disk
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        short_id = hashlib.sha256(file_id.encode()).hexdigest()[:8]
        unique_name = f"{short_id}_{uuid.uuid4().hex[:8]}_{filename}"
        file_path = DOWNLOAD_DIR / unique_name
        file_path.write_bytes(raw_bytes)

        return {
            "content_type": content_type.split(";")[0].strip(),
            "size_bytes": len(raw_bytes),
            "file_path": str(file_path),
            "filename": filename,
            "saved_to_disk": True,
        }

    @staticmethod
    def _restructure_filter_body(params: dict[str, Any]) -> dict[str, Any]:
        """Restructure flat filter params into Gmail's nested format.

        The Gmail filters.create and filters.update APIs expect a body like:
        {
            "criteria": {"query": "...", "from": "...", ...},
            "action": {"addLabelIds": [...], "forward": "...", ...}
        }

        But the proxy receives flat parameters from MCP/REST callers:
        {"query": "...", "label_ids": [...], "forward": "...", ...}

        This method splits flat params into the nested structure.
        """
        # Filter criteria fields (as accepted by the Gmail API)
        criteria_fields = {
            "query",
            "from",
            "to",
            "subject",
            "negatedQuery",
            "hasAttachment",
            "excludeChats",
            "size",
            "sizeComparison",
        }
        # Action fields
        action_fields = {
            "addLabelIds",
            "removeLabelIds",
            "forward",
            "archive",
            "delete",
            "markAsImportant",
            "markAsRead",
            "star",
        }

        # Map our snake_case names to Gmail's camelCase action names
        snake_to_camel_action = {
            "label_ids": "addLabelIds",
            "mark_as_read": "markAsRead",
            "mark_as_important": "markAsImportant",
            "archive": "archive",
            "delete": "delete",
            "forward": "forward",
            "star": "star",
        }

        body: dict[str, Any] = {}

        # Also preserve any already-nested structures passed through
        if "criteria" in params or "action" in params:
            return params

        criteria: dict[str, Any] = {}
        action: dict[str, Any] = {}

        for key, value in params.items():
            # Skip path params that were already used
            if key in ("filterId", "userId"):
                continue

            # Direct camelCase criteria match
            if key in criteria_fields:
                criteria[key] = value
            # Direct camelCase action match
            elif key in action_fields:
                action[key] = value
            # Map snake_case action names
            elif key in snake_to_camel_action:
                action[snake_to_camel_action[key]] = value
            # labelIds → addLabelIds (common snake_case variant)
            elif key == "labelIds":
                action["addLabelIds"] = value

        if criteria:
            body["criteria"] = criteria
        if action:
            body["action"] = action

        # If neither criteria nor action was populated, just return params as-is
        # (let Google API reject with a clear error)
        if not body:
            return params

        return body

    @staticmethod
    def sheet_create(params: dict[str, Any]) -> dict[str, Any]:
        """Transform flat {title, sheet_titles, locale, timeZone} into a Google
        Sheets Spreadsheet resource shape.

        The Sheets API v4 POST /v4/spreadsheets endpoint expects the request
        body to BE the Spreadsheet resource itself — top-level `properties`,
        `sheets`, `namedRanges`, etc. The route's input_schema accepts a
        friendly flat subset; this method reshapes it for Google's API.

        This is called AFTER snake_case → camelCase normalization, so the
        keys arrive here as `title`, `sheetTitles`, `locale`, `timeZone`
        (not the snake_case forms).

        Google canonical example:
            {"properties": {"title": "My Sheet"}, "sheets": [{"properties": {"title": "Sheet1"}}]}

        Caller-friendly shape (this route's public input contract):
            {"title": "My Sheet", "sheet_titles": ["Sheet1", "Sheet2"]}

        If the caller already passed a properly nested Spreadsheet resource,
        return it unchanged (passthrough for power users).
        """
        # Passthrough: caller already shaped it correctly.
        if "properties" in params or "sheets" in params:
            return params

        spreadsheet: dict[str, Any] = {}

        # Top-level Spreadsheet properties.
        # Note: callers may use snake_case sheet_titles (pre-normalization) OR
        # camelCase sheetTitles (post-normalization) — handle both for safety.
        if "title" in params:
            spreadsheet.setdefault("properties", {})["title"] = params.pop("title")
        if "locale" in params:
            spreadsheet.setdefault("properties", {})["locale"] = params.pop("locale")
        if "timeZone" in params:
            spreadsheet.setdefault("properties", {})["timeZone"] = params.pop("timeZone")

        # sheetTitles (camelCase, post-normalization) or sheet_titles (snake_case)
        # → sheets array (each with index)
        sheet_titles_key = "sheetTitles" if "sheetTitles" in params else "sheet_titles"
        if sheet_titles_key in params:
            sheet_titles = params.pop(sheet_titles_key)
            if isinstance(sheet_titles, list):
                spreadsheet["sheets"] = [
                    {"properties": {"title": t, "index": i}} for i, t in enumerate(sheet_titles)
                ]

        # Pass through any other fields the caller provided (namedRanges, etc.)
        for key, value in params.items():
            spreadsheet[key] = value

        return spreadsheet
