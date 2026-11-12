"""Real HTTP/SSE regression tests for MCP credential handling."""

import asyncio
import json
import logging
import socket
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
import uvicorn
from mcp import ClientSession
from mcp.client.sse import sse_client

from gatekeeper.mcp_server import mount_mcp_server


@pytest_asyncio.fixture
async def live_server(app, monkeypatch):
    import gatekeeper.mcp_server as server

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    monkeypatch.setattr(server.settings, "port", port)
    mount_mcp_server(app)
    uv = uvicorn.Server(uvicorn.Config(app, log_config=None, lifespan="off", access_log=False))
    task = asyncio.create_task(uv.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not uv.started:
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        uv.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()


@asynccontextmanager
async def session_at(url, key=None):
    headers = {"X-Gatekeeper-API-Key": key} if key else None
    async with sse_client(f"{url}/mcp/sse", headers=headers) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=5) as session:
            await session.initialize()
            yield session


@pytest.mark.asyncio
async def test_sse_auth_and_debug_logs(live_server, api_key, caplog):
    caplog.set_level(logging.DEBUG)
    secret_argument = "fake-sensitive-argument-value"
    fallback = "fake-fallback-secret"
    with patch("gatekeeper.api.proxy.GoogleProxy") as proxy_cls:
        proxy = proxy_cls.return_value
        proxy.call_google = AsyncMock(return_value={"ok": True})
        async with session_at(live_server, api_key) as session:
            result = await session.call_tool(
                "drive__files_list", {"api_key": fallback, "q": secret_argument}
            )
            assert json.loads(result.content[0].text) == {"ok": True}
        assert proxy.call_google.await_args.kwargs["params"] == {"q": secret_argument}

    server_logs = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("mcp.server")
    )
    assert fallback not in server_logs
    assert secret_argument not in server_logs
    assert api_key not in server_logs
    assert "MCP transport event (details suppressed)" in server_logs


@pytest.mark.asyncio
async def test_malformed_sse_post_does_not_log_payload(live_server, caplog):
    caplog.set_level(logging.DEBUG, logger="mcp.server.sse")
    session_ids = []
    secret = "fake-malformed-secret"
    async with sse_client(f"{live_server}/mcp/sse", on_session_created=session_ids.append) as (
        read,
        write,
    ):
        async with ClientSession(read, write, read_timeout_seconds=5) as session:
            await session.initialize()
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{live_server}/mcp/messages/?session_id={session_ids[0]}",
                    content=f'{{"api_key":"{secret}"',
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 400
    records = [r for r in caplog.records if r.name == "mcp.server.sse"]
    assert records
    assert all(secret not in logging.Formatter().format(r) for r in records)


@pytest.mark.asyncio
async def test_sse_credentials_and_reconnect(live_server, api_key, inactive_key):
    with patch("gatekeeper.api.proxy.GoogleProxy") as proxy_cls:
        proxy = proxy_cls.return_value
        proxy.call_google = AsyncMock(return_value={"ok": True})
        for header, args, status in [
            (None, {}, 401),
            ("gkp_invalid", {}, 401),
            (inactive_key, {}, 401),
            (None, {"api_key": "gkp_invalid"}, 401),
            ("gkp_invalid", {"api_key": api_key}, 401),
            (None, {"api_key": api_key, "q": "fallback"}, 200),
            (api_key, {"api_key": "gkp_invalid", "q": "header"}, 200),
            (api_key, {"q": "reconnected"}, 200),
        ]:
            async with session_at(live_server, header) as session:
                result = await session.call_tool("drive__files_list", args)
                body = json.loads(result.content[0].text)
                assert body.get("status", 200) == status
        assert [c.kwargs["params"] for c in proxy.call_google.await_args_list] == [
            {"q": "fallback"},
            {"q": "header"},
            {"q": "reconnected"},
        ]


@pytest.mark.asyncio
async def test_sse_cors_preflight_and_actual_origin(live_server):
    origin = "http://localhost:8080"
    async with httpx.AsyncClient(timeout=5) as client:
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-gatekeeper-api-key,content-type",
        }
        preflight = await client.options(f"{live_server}/mcp/messages/", headers=headers)
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin
        assert "x-gatekeeper-api-key" in preflight.headers["access-control-allow-headers"].lower()
        async with client.stream("GET", f"{live_server}/mcp/sse", headers={"Origin": origin}) as r:
            assert r.status_code == 200
            assert r.headers["access-control-allow-origin"] == origin
        bad = await client.options(
            f"{live_server}/mcp/messages/", headers={**headers, "Origin": "https://evil.example"}
        )
        assert bad.status_code == 400
        rejected = await client.get(
            f"{live_server}/mcp/sse", headers={"Origin": "https://evil.example"}
        )
        assert rejected.status_code == 403
