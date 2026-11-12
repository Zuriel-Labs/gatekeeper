"""MCP v2 authentication regression tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from starlette.requests import Request

from gatekeeper.mcp_server import create_mcp_server


def make_context(api_key: str | None):
    headers = [] if api_key is None else [(b"x-gatekeeper-api-key", api_key.encode())]
    request = Request(scope={"type": "http", "headers": headers})
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


@pytest_asyncio.fixture
async def mcp(app):
    return create_mcp_server()


@pytest.mark.asyncio
async def test_header_auth_succeeds_and_secret_is_not_forwarded(mcp, db_session, api_key):
    with patch("gatekeeper.api.proxy.GoogleProxy") as proxy_cls:
        proxy = proxy_cls.return_value
        proxy.call_google = AsyncMock(return_value={"files": []})
        result = await mcp.call_tool("drive__files_list", {}, context=make_context(api_key))
    assert not result.is_error
    proxy.call_google.assert_awaited_once()
    params = proxy.call_google.await_args.kwargs["params"]
    assert "api_key" not in params
    assert api_key not in json.dumps(params)


@pytest.mark.asyncio
async def test_invalid_header_is_rejected(mcp):
    result = await mcp.call_tool(
        "drive__files_list", {}, context=make_context("gkp_does_not_exist")
    )
    assert json.loads(result.content[0].text) == {
        "error": True,
        "status": 401,
        "message": "Invalid API key",
    }


@pytest.mark.asyncio
async def test_missing_credentials_are_rejected(mcp):
    result = await mcp.call_tool("drive__files_list", {}, context=make_context(None))
    assert json.loads(result.content[0].text)["status"] == 401


@pytest.mark.asyncio
async def test_argument_fallback_secret_is_not_forwarded(mcp, db_session, api_key):
    with patch("gatekeeper.api.proxy.GoogleProxy") as proxy_cls:
        proxy = proxy_cls.return_value
        proxy.call_google = AsyncMock(return_value={"files": []})
        result = await mcp.call_tool(
            "drive__files_list", {"api_key": api_key}, context=make_context(None)
        )
    assert not result.is_error
    assert "api_key" not in proxy.call_google.await_args.kwargs["params"]


@pytest.mark.asyncio
async def test_tool_listing_keeps_api_key_optional(mcp):
    tools = await mcp.list_tools()
    assert tools
    assert all("api_key" in tool.input_schema["properties"] for tool in tools)
    assert all("api_key" not in tool.input_schema.get("required", []) for tool in tools)
