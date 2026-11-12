"""MCP server setup — dynamic tool registration from enabled routes.

Uses the MCP Python SDK v2 to expose enabled Gatekeeper
routes as MCP tools discoverable by AI agents over SSE transport.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI
from starlette.responses import JSONResponse

from gatekeeper.config import settings
from gatekeeper.models import ApiKey
from gatekeeper.policy import PolicyEngine

logger = logging.getLogger(__name__)


class _SafeMCPTransportLog(logging.Filter):
    """Keep severity and source while suppressing untrusted SDK payloads."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = "MCP transport event (details suppressed)"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class _SafeMCPAccessLog(logging.Filter):
    """Keep access metadata but never log MCP query parameters (session IDs)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, path, version, status = record.args
            if isinstance(path, str) and path.startswith("/mcp/") and "?" in path:
                record.args = (client, method, path.split("?", 1)[0], version, status)
        return True


def _get_async_session():
    """Return the current async_session callable,
    allowing tests to patch gatekeeper.db.async_session."""
    import gatekeeper.db

    return gatekeeper.db.async_session


def _get_session():
    """Return an AsyncSession from the current async_session callable."""
    return _get_async_session()()


# Lazy-initialised singleton
_mcp_instance: Any | None = None


def _build_transport_security() -> Any:
    """Build transport security settings that allow the configured hosts.

    The MCP SDK enables DNS rebinding protection by default, which rejects
    all requests unless ``allowed_hosts`` is explicitly configured.

    Defaults to localhost/127.0.0.1 on the configured port (secure-by-default).
    Users add additional hosts (Tailscale, LAN IPs, wildcards) via:
      - GATEKEEPER_MCP_ALLOWED_HOSTS env var (JSON array)
      - gatekeeper hosts add <host>
    """
    from mcp.server.transport_security import TransportSecuritySettings

    port = settings.port
    hosts = set()

    # Always allow localhost variants (secure defaults)
    hosts.add(f"localhost:{port}")
    hosts.add(f"127.0.0.1:{port}")

    # Add user-configured hosts from GATEKEEPER_MCP_ALLOWED_HOSTS
    for host in settings.mcp_allowed_hosts:
        # Support port-less hosts by appending the server port
        if ":" not in host:
            hosts.add(f"{host}:{port}")
        else:
            hosts.add(host)

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(hosts),
        # Origins are scheme-qualified; host:port entries cannot match a
        # browser Origin header. Do not make wildcard CORS disable rebinding
        # protection: only explicitly configured origins are accepted.
        allowed_origins=[origin for origin in settings.cors_origins if origin != "*"],
    )


async def _resolve_api_key(raw_key: str) -> ApiKey | None:
    """Look up an API key by prefix+bcrypt verification.

    Returns the ApiKey record if found and active, else None.
    """
    import bcrypt
    from sqlalchemy import select

    async with _get_session() as session:
        result = await session.execute(select(ApiKey).where(ApiKey.is_active == True))  # noqa: E712
        keys = result.scalars().all()
        for k in keys:
            if raw_key.startswith(k.key_prefix):
                if bcrypt.checkpw(raw_key.encode(), k.key_hash.encode()):
                    # Touch last_used_at
                    k.last_used_at = __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    )
                    await session.commit()
                    return k
    return None


def create_mcp_server() -> Any:
    """Create a FastMCP instance that exposes enabled routes as tools.

    Tools are discovered dynamically on each list_tools call so that
    admin toggles (enabling/disabling routes) take effect immediately
    without a server restart.

    Tool names follow the pattern:  {module}__{route_suffix_with_underscores}
    where route_suffix strips the leading module prefix from route_id.
    For example:  gmail.messages.list → gmail__messages_list
    drive.files.list_shared → drive__files_list_shared

    Each tool accepts all the route's input_schema parameters and an optional
    ``api_key`` argument as a fallback when the HTTP header is absent.
    """
    from mcp.server.mcpserver import MCPServer
    from mcp.types import CallToolResult

    class GatekeeperMCPServer(MCPServer):
        async def list_tools(self):
            return await list_tools()

        async def call_tool(self, name, arguments, context=None):
            request = context.request_context.request if context else None
            content = await call_tool(name, arguments, request)
            return CallToolResult(content=content)

    mcp = GatekeeperMCPServer(
        name="gatekeeper",
        instructions=(
            "Gatekeeper MCP server — a policy gateway for Google Workspace APIs "
            "(Drive, Gmail, Calendar). Each tool proxies a single Google API route "
            "through the policy engine. Authentication is via the X-Gatekeeper-API-Key "
            "HTTP header on the POST /mcp/messages/ request. As a fallback for clients "
            "that cannot send custom headers, an api_key argument is also accepted, "
            "but header auth is preferred because it keeps the key out of the LLM "
            "context. Available tools depend on which routes are enabled by the "
            "administrator — call list_tools to see what's currently available. Do not "
            "assume any route is enabled or disabled; if a tool call returns a 403 "
            "error, that route is disabled and only the administrator can enable it. "
            "You cannot bypass disabled routes, modify policies, or access admin "
            "settings."
        ),
    )

    # ------------------------------------------------------------------ #
    #  list_tools — dynamically build the tool list from the DB           #
    # ------------------------------------------------------------------ #
    async def list_tools():
        """Return MCP tools for all enabled routes."""
        from mcp.types import Tool as MCPTool

        from gatekeeper.modules import AVAILABLE_MODULES, load_module

        tools: list[MCPTool] = []

        async with _get_session() as session:
            policy_engine = PolicyEngine(session)

            for module_name in AVAILABLE_MODULES:
                mod = load_module(module_name)
                if mod is None:
                    continue

                for route in mod.get_routes():
                    # Check if route is enabled via policy
                    decision = await policy_engine.check_route(module_name, route.route_id)
                    if decision.allowed:
                        # Merge the route's input_schema with api_key param
                        schema = dict(route.input_schema)
                        props = dict(schema.get("properties", {}))
                        props["api_key"] = {
                            "type": "string",
                            "description": (
                                "Gatekeeper API key. Optional when the "
                                "X-Gatekeeper-API-Key HTTP header "
                                "is set on the request; otherwise required for authentication."
                            ),
                        }
                        required = list(schema.get("required", []))
                        # api_key is no longer required; header auth is preferred.

                        # Strip module prefix from route_id to avoid redundancy
                        # e.g., "gmail.messages.list" → suffix "messages.list"
                        #     → tool name "gmail__messages_list"
                        route_suffix = (
                            route.route_id.split(".", 1)[1]
                            if "." in route.route_id
                            else route.route_id
                        )
                        tool_name = f"{module_name}__{route_suffix.replace('.', '_')}"
                        tools.append(
                            MCPTool(
                                name=tool_name,
                                description=route.description or f"{route.method} {route.route_id}",
                                input_schema={
                                    **schema,
                                    "properties": props,
                                    "required": required,
                                },
                            )
                        )

        return tools

    # ------------------------------------------------------------------ #
    #  call_tool — authenticate & proxy through the policy engine         #
    # ------------------------------------------------------------------ #
    async def call_tool(name: str, arguments: dict[str, Any], request=None) -> list:
        """Call a tool by name, routing through the policy engine."""
        import mcp.types as types

        from gatekeeper.api.proxy import GoogleProxy
        from gatekeeper.modules import load_module

        # ---- AUTH: header first, argument fallback, always pop ----
        api_key: str | None = None
        if request is not None:
            api_key = request.headers.get("X-Gatekeeper-API-Key") or None

        # Always pop api_key from arguments so it never reaches the proxy,
        # regardless of whether header auth was used.
        arg_api_key = arguments.pop("api_key", None)
        if not api_key:
            api_key = arg_api_key

        if not api_key:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": True,
                            "status": 401,
                            "message": (
                                "API key required (set X-Gatekeeper-API-Key "
                                "header or pass api_key argument)"
                            ),
                        }
                    ),
                )
            ]

        key_record = await _resolve_api_key(api_key)
        if not key_record:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": True, "status": 401, "message": "Invalid API key"}),
                )
            ]

        # Parse module and route from tool name using module registry
        # Tool name format: "{module}__{route_suffix_with_underscores}"
        # e.g., "gmail__messages_list" → module="gmail",
        #     look up route starting with "gmail.messages"
        parts = name.split("__", 1)
        if len(parts) != 2:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": True, "message": f"Invalid tool name: {name}"}),
                )
            ]

        module_name = parts[0]
        route_suffix = parts[1]

        # Look up the route by finding a matching route in the module
        # route_suffix uses underscores where the original had dots
        # e.g., "files_list_shared" matches "drive.files.list_shared"
        mod = load_module(module_name)
        if mod is None:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"error": True, "message": f"Module {module_name} not found"}),
                )
            ]

        # Find the route by converting each route's suffix to underscore form
        # and comparing with the tool name suffix
        route_id = None
        for route in mod.get_routes():
            route_suffix_part = (
                route.route_id.split(".", 1)[1] if "." in route.route_id else route.route_id
            )
            if route_suffix_part.replace(".", "_") == route_suffix:
                route_id = route.route_id
                break

        if route_id is None:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {"error": True, "message": f"Route not found for tool: {name}"}
                    ),
                )
            ]

        async with _get_session() as session:
            proxy = GoogleProxy(session)
            result = await proxy.call_google(
                module_name=module_name,
                route_id=route_id,
                params=arguments,
                api_key_record=key_record,
                request_path=f"/mcp/{name}",
                request_method="POST",
            )

        # Extract the response body — call_google returns a JSONResponse
        if isinstance(result, JSONResponse):
            # JSONResponse.body is bytes (JSON-encoded)
            result_body = result.body
            if isinstance(result_body, (bytes, memoryview)):
                result_body = bytes(result_body).decode("utf-8")
            return [
                types.TextContent(
                    type="text",
                    text=str(result_body),
                )
            ]

        # Fallback for dict or other types
        return [
            types.TextContent(
                type="text",
                text=json.dumps(result) if isinstance(result, dict) else str(result),
            )
        ]

    return mcp


def mount_mcp_server(app: FastAPI) -> None:
    """Mount the MCP SSE server onto the FastAPI app at /mcp.

    This creates a Starlette sub-app via FastMCP.sse_app() and mounts
    it under FastAPI so that:

      GET  /mcp/sse        → SSE endpoint (client connects here)
      POST /mcp/messages/  → message endpoint (client sends JSON-RPC here)

    The SSE transport lets remote AI agents discover and call Gatekeeper
    tools over HTTP.
    """
    global _mcp_instance

    try:
        # SDK SSE debug messages include entire POST bodies and parsed frames;
        # parse exceptions can also contain attacker-controlled input. A logger
        # filter runs before any handler, even when DEBUG is explicitly enabled.
        # Do not try to parse/redact secrets: arbitrary arguments are sensitive.
        # The runner can also log a frame received before initialization.
        # sse-starlette logs outgoing chunks, including session IDs and responses.
        for name in ("mcp.server.sse", "mcp.server.runner", "sse_starlette.sse"):
            sdk_logger = logging.getLogger(name)
            if not any(isinstance(f, _SafeMCPTransportLog) for f in sdk_logger.filters):
                sdk_logger.addFilter(_SafeMCPTransportLog())
        access_logger = logging.getLogger("uvicorn.access")
        if not any(isinstance(f, _SafeMCPAccessLog) for f in access_logger.filters):
            access_logger.addFilter(_SafeMCPAccessLog())
        mcp = create_mcp_server()
        _mcp_instance = mcp

        # Get the Starlette SSE app from FastMCP
        # No mount_path here — FastAPI's app.mount("/mcp", ...) already
        # provides the /mcp prefix. Setting mount_path="/mcp" would cause
        # the SSE client to POST to /mcp/mcp/messages/ (double path).
        starlette_app = mcp.sse_app(
            host=settings.host,
            transport_security=_build_transport_security(),
        )

        # Mount the Starlette app as a sub-app under FastAPI
        # Routes become: GET /mcp/sse, POST /mcp/messages/
        app.mount("/mcp", starlette_app)

        logger.info("MCP SSE server mounted at /mcp")

    except ImportError as exc:
        logger.warning("MCP package not installed. Install with: pip install mcp — %s", exc)
    except Exception as exc:
        logger.error("Failed to mount MCP server: %s", exc, exc_info=True)
