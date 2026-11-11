"""URL construction validation for ALL registered routes.

For every route in every module, this test:
1. Creates a RoutePolicy (enabled)
2. Builds mock parameters for any path params
3. Calls GoogleProxy.call_google with mock credentials
4. Verifies the final URL was built correctly with placeholders substituted.

This catches:
- Missing/incorrect path params in input schemas
- Wrong google_path definitions
- CamelCase vs snake_case key mismatches
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gatekeeper.api.proxy import GoogleProxy
from gatekeeper.models import ApiKey, RoutePolicy
from gatekeeper.modules import AVAILABLE_MODULES, load_module


def _make_api_key(permissions: str = "*") -> ApiKey:
    return ApiKey(
        name="test-key",
        key_hash="$2b$12$fakehashfakehashfakehashfakehashfa",
        key_prefix="gkp_test",
        permissions=permissions,
    )


def _mock_creds() -> MagicMock:
    creds = MagicMock()
    creds.token = "mock_access_token"
    creds.expired = False
    creds.refresh_token = "mock_refresh"
    return creds


def _extract_path_params(google_path: str) -> list[str]:
    """Extract {paramName} placeholders from a path."""
    return re.findall(r"\{([^}]+)\}", google_path)


def _snake_case(s: str) -> str:
    """Convert camelCase to snake_case."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def _route_to_url_path(module_name: str, route_id: str) -> str:
    """Convert route_id to the REST API path endpoint uses."""
    parts = route_id.split(".", 1)
    if len(parts) > 1:
        return "_".join(parts[1].split("."))
    return parts[0]


@pytest.mark.parametrize(
    "module_name,route_id,method,google_path",
    [
        pytest.param(
            module_name,
            route.route_id,
            route.method,
            route.google_path,
            id=route.route_id,
        )
        for module_name in AVAILABLE_MODULES
        for route in load_module(module_name).get_routes()
    ],
)
@pytest.mark.asyncio
async def test_url_construction(
    db_session, module_name: str, route_id: str, method: str, google_path: str
):
    """Every route must produce a valid URL with no remaining placeholders."""
    policy = RoutePolicy(
        module=module_name,
        route=route_id,
        enabled=True,
        policy_config="{}",
    )
    db_session.add(policy)
    await db_session.commit()

    api_key = _make_api_key()
    proxy = GoogleProxy(db_session)

    # Build params with fake values for all path params
    # For multipart upload routes, also provide base64_content
    from gatekeeper.modules import load_module

    routes = load_module(module_name).get_routes()
    route_obj = next(r for r in routes if r.route_id == route_id)
    path_params = _extract_path_params(google_path)
    params = {}
    for pp in path_params:
        snake = _snake_case(pp)
        fake_value = f"fake_{snake}"
        if module_name == "gmail" and "userId" in pp:
            fake_value = "me"
        params[snake] = fake_value

    if route_obj.multipart_upload:
        # multipart upload routes validate base64_content before URL construction
        import base64 as _b64

        params["base64_content"] = _b64.b64encode(b"test upload body").decode()
        params["name"] = "test.txt"

    with (
        patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
        patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_cm.get_credentials.return_value = _mock_creds()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        # Attach mock method for the expected HTTP verb
        mock_method = AsyncMock(return_value=mock_response)
        setattr(mock_client, method.lower(), mock_method)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        resp = await proxy.call_google(
            module_name=module_name,
            route_id=route_id,
            params=params,
            api_key_record=api_key,
            request_method=method,
        )

        # Response should be successful
        assert resp.status_code == 200

        # The correct HTTP method must have been used
        assert mock_method.called, f"Expected {method} to be called for {route_id}"

        call_args = mock_method.call_args
        actual_url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")

        # No placeholders should remain in the URL
        remaining_placeholders = _extract_path_params(actual_url)
        assert remaining_placeholders == [], (
            f"{route_id}: URL still has placeholders: {remaining_placeholders} — url={actual_url}"
        )

        # Verify the URL contains the fake values (path params were substituted)
        for pp in path_params:
            expected_in_url = f"fake_{_snake_case(pp)}"
            if module_name == "gmail" and "userId" in pp:
                expected_in_url = "me"
            assert expected_in_url in actual_url, (
                f"{route_id}: Expected '{expected_in_url}' in URL {actual_url}"
            )
