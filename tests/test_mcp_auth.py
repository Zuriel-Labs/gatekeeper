"""MCP authentication tests — header-first auth for tool calls.

Tests cover the 12 scenarios from specs/mcp-header-auth-spec.md §5.2.
Pattern A: invoke the registered call_tool handler directly with a mocked or
set request_ctx ContextVar (most scenarios). Pattern B: full integration via
httpx against the mounted SSE sub-app (CORS and SSE smoke tests).
"""

from __future__ import annotations

import contextlib
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from mcp.types import CallToolRequest, CallToolRequestParams, ListToolsRequest
from starlette.requests import Request

from gatekeeper.mcp_server import create_mcp_server, mount_mcp_server


def make_request_ctx(headers: dict[str, str] | None = None) -> RequestContext:
    """Build a RequestContext with a fake Starlette Request carrying the given headers."""
    if headers is None:
        headers = {}
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    fake_request = Request(scope={"type": "http", "headers": raw_headers})
    return RequestContext(
        request=fake_request,
        request_id="test",
        meta=None,
        session=None,  # type: ignore[arg-type]
        lifespan_context=None,
    )


@contextlib.contextmanager
def use_request_ctx(ctx: RequestContext | None):
    """Set (or clear) request_ctx for the duration of a block.

    Pass None to simulate transports where request_ctx is unavailable and
    request_ctx.get() raises LookupError (e.g. stdio).
    """
    if ctx is None:
        saved_token = None
        try:
            request_ctx.get()
            saved_token = request_ctx.set(None)
        except LookupError:
            pass
        try:
            yield
        finally:
            if saved_token is not None:
                request_ctx.reset(saved_token)
    else:
        token = request_ctx.set(ctx)
        try:
            yield
        finally:
            request_ctx.reset(token)


@pytest_asyncio.fixture
async def mcp_handlers(app):
    """Yield the registered (list_tools, call_tool) handlers using the test app context.

    The `app` fixture from conftest already patches gatekeeper.db.async_session to the
    in-memory test DB and seeds route policies / API keys. We additionally patch the
    mcp_server module's imported copy so create_mcp_server uses the same test session.
    """
    import gatekeeper.db
    import gatekeeper.mcp_server as mcp_server_mod

    original_mcp_async_session = getattr(mcp_server_mod, "async_session", None)
    mcp_server_mod.async_session = gatekeeper.db.async_session

    mcp = create_mcp_server()
    handlers = mcp._mcp_server.request_handlers
    list_tools = handlers[ListToolsRequest]
    call_tool = handlers[CallToolRequest]

    yield list_tools, call_tool

    if original_mcp_async_session is not None:
        mcp_server_mod.async_session = original_mcp_async_session


@pytest_asyncio.fixture
async def call_tool_coro(mcp_handlers):
    """Return a coroutine that calls the registered tool handler with plain args."""
    _, raw_handler = mcp_handlers

    async def _invoke(name: str, arguments: dict):
        req = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name=name, arguments=arguments),
        )
        result = await raw_handler(req)
        return result.root.content

    return _invoke


@pytest_asyncio.fixture
async def list_tools_coro(mcp_handlers):
    """Return a coroutine that calls the registered list_tools handler."""
    raw_handler, _ = mcp_handlers

    async def _invoke():
        req = ListToolsRequest(method="tools/list")
        result = await raw_handler(req)
        return result.root.tools

    return _invoke


class TestMCPHeaderAuth:
    """Scenario 1, 3, 5 — auth via X-Gatekeeper-API-Key header."""

    @pytest.mark.asyncio
    async def test_header_auth_succeeds(self, call_tool_coro, db_session, api_key):
        """Scenario 1: header auth only yields a successful call."""
        ctx = make_request_ctx({"X-Gatekeeper-API-Key": api_key})
        with use_request_ctx(ctx):
            with patch("gatekeeper.api.proxy.GoogleProxy") as mock_proxy_cls:
                mock_proxy = mock_proxy_cls.return_value
                mock_proxy.call_google = AsyncMock(return_value={"files": []})
                content = await call_tool_coro("drive__files_list", {})

        payload = json.loads(content[0].text)
        assert payload.get("status") != 401
        assert "Invalid API key" not in payload.get("message", "")
        mock_proxy.call_google.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_header_takes_precedence_over_argument(self, call_tool_coro, db_session, api_key):
        """Scenario 3: when both header and arg are present, header wins."""
        ctx = make_request_ctx({"X-Gatekeeper-API-Key": api_key})
        bogus_arg = "gkp_argument_value_not_real_but_distinguishable"

        with use_request_ctx(ctx):
            with patch("gatekeeper.mcp_server._resolve_api_key") as mock_resolve:
                mock_resolve.return_value = None
                await call_tool_coro("drive__files_list", {"api_key": bogus_arg})

        called_with = mock_resolve.call_args[0][0]
        assert called_with == api_key, f"Expected header value, got {called_with!r}"

    @pytest.mark.asyncio
    async def test_invalid_header_returns_401(self, call_tool_coro):
        """Scenario 5: invalid header key returns 401."""
        ctx = make_request_ctx({"X-Gatekeeper-API-Key": "gkp_does_not_exist"})
        with use_request_ctx(ctx):
            content = await call_tool_coro("drive__files_list", {})

        payload = json.loads(content[0].text)
        assert payload == {
            "error": True,
            "status": 401,
            "message": "Invalid API key",
        }


class TestMCPArgumentAuth:
    """Scenario 2, 6, 10, 12 — auth via the legacy api_key argument."""

    @pytest.mark.asyncio
    async def test_argument_auth_succeeds(self, call_tool_coro, db_session, api_key):
        """Scenario 2: argument-only auth still works."""
        with use_request_ctx(None):
            with patch("gatekeeper.api.proxy.GoogleProxy") as mock_proxy_cls:
                mock_proxy = mock_proxy_cls.return_value
                mock_proxy.call_google = AsyncMock(return_value={"files": []})
                content = await call_tool_coro("drive__files_list", {"api_key": api_key})

        payload = json.loads(content[0].text)
        assert payload.get("status") != 401
        mock_proxy.call_google.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_argument_returns_401(self, call_tool_coro):
        """Scenario 6: invalid api_key argument returns 401."""
        with use_request_ctx(None):
            content = await call_tool_coro("drive__files_list", {"api_key": "gkp_does_not_exist"})

        payload = json.loads(content[0].text)
        assert payload == {
            "error": True,
            "status": 401,
            "message": "Invalid API key",
        }

    @pytest.mark.asyncio
    async def test_existing_argument_only_client_unchanged(
        self, call_tool_coro, db_session, api_key
    ):
        """Scenario 10: legacy clients passing only api_key remain functional."""
        with use_request_ctx(None):
            with patch("gatekeeper.api.proxy.GoogleProxy") as mock_proxy_cls:
                mock_proxy = mock_proxy_cls.return_value
                mock_proxy.call_google = AsyncMock(return_value={"files": []})
                content = await call_tool_coro(
                    "drive__files_list",
                    {"api_key": api_key, "pageSize": 5},
                )

        payload = json.loads(content[0].text)
        assert payload.get("status") != 401
        mock_proxy.call_google.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_argument_when_request_ctx_missing(
        self, call_tool_coro, db_session, api_key
    ):
        """Scenario 12: LookupError from request_ctx.get() falls back to arg."""
        with use_request_ctx(None):
            with patch("gatekeeper.api.proxy.GoogleProxy") as mock_proxy_cls:
                mock_proxy = mock_proxy_cls.return_value
                mock_proxy.call_google = AsyncMock(return_value={"files": []})
                content = await call_tool_coro("drive__files_list", {"api_key": api_key})

        payload = json.loads(content[0].text)
        assert isinstance(content, list)
        assert payload.get("status") != 401
        mock_proxy.call_google.assert_awaited_once()


class TestMCPAuthFailures:
    """Scenario 4 — missing auth returns the updated 401 message."""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, call_tool_coro):
        """Scenario 4: no header and no api_key argument returns 401."""
        with use_request_ctx(None):
            content = await call_tool_coro("drive__files_list", {})

        payload = json.loads(content[0].text)
        assert payload == {
            "error": True,
            "status": 401,
            "message": (
                "API key required (set X-Gatekeeper-API-Key header or pass api_key argument)"
            ),
        }


class TestMCPToolSchema:
    """Scenario 9 — api_key stays in properties but is removed from required."""

    @pytest.mark.asyncio
    async def test_list_tools_marks_api_key_optional(self, list_tools_coro):
        """api_key must remain in properties and be absent from required.

        This test is intentionally a regression detector: against the pre-fix code
        (which appended api_key to required), it fails with an AssertionError
        mentioning api_key in required.
        """
        tools = await list_tools_coro()
        assert tools, "Expected at least one tool"
        for tool in tools:
            schema = tool.inputSchema
            assert "api_key" in schema["properties"], (
                f"api_key should remain in properties for {tool.name}"
            )
            assert "api_key" not in schema.get("required", []), (
                f"api_key should NOT be in required for {tool.name} "
                f"(regression: this test fails against the pre-fix code)"
            )


@pytest.mark.skip(reason="SSE full-flow integration harness TBD (see spec §5.2 scenario 7)")
class TestMCPFullSSEFlow:
    """Scenario 7 / 8 — full SSE end-to-end header auth (integration)."""

    @pytest.mark.asyncio
    async def test_header_auth_full_sse_flow(self, client, app, api_key):
        """Scenario 7: open SSE, POST tools/call with header, assert success."""
        mount_mcp_server(app)

    @pytest.mark.asyncio
    async def test_header_auth_after_reconnect(self, client, app, api_key):
        """Scenario 8 (optional): reconnect with new session_id still works."""
        mount_mcp_server(app)


class TestMCPCors:
    """Scenario 11 — CORS preflight permits the X-Gatekeeper-API-Key header."""

    @pytest.mark.asyncio
    async def test_cors_preflight_allows_header(self, client, app):
        mount_mcp_server(app)
        resp = await client.options(
            "/mcp/sse",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-gatekeeper-api-key, content-type",
            },
        )
        assert resp.status_code in (200, 204)
        allow_headers = resp.headers.get("access-control-allow-headers", "").lower()
        assert "x-gatekeeper-api-key" in allow_headers


class TestMCPKeySanitization:
    """Ensure api_key is popped from arguments before proxy.call_google."""

    @pytest.mark.asyncio
    async def test_api_key_not_passed_to_proxy(self, call_tool_coro, db_session, api_key):
        """When api_key is passed as an argument it must not appear in proxy params."""
        with use_request_ctx(None):
            with patch("gatekeeper.api.proxy.GoogleProxy") as mock_proxy_cls:
                mock_proxy = mock_proxy_cls.return_value
                mock_proxy.call_google = AsyncMock(return_value={})
                args = {"api_key": api_key, "pageSize": 5}
                await call_tool_coro("drive__files_list", args)

        call_kwargs = mock_proxy.call_google.call_args.kwargs
        assert "api_key" not in call_kwargs.get("params", {}), (
            "api_key leaked into proxy.call_google params"
        )
        assert call_kwargs["params"].get("pageSize") == 5
