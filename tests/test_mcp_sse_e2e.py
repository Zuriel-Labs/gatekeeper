"""Real HTTP/SSE regression tests for MCP credential handling."""

import asyncio
import json
import logging
import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
import uvicorn
from mcp import ClientSession
from mcp.client.sse import sse_client

from gatekeeper.mcp_server import mount_mcp_server


@pytest.fixture
def server_records():
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    return records, Capture()


@pytest_asyncio.fixture
async def live_server(app, monkeypatch, server_records):
    from sse_starlette.sse import AppStatus

    import gatekeeper.mcp_server as server

    # Uvicorn/sse-starlette hold process-global shutdown state. Isolate each
    # real server so a prior shutdown cannot immediately drain the next one.
    monkeypatch.setattr(AppStatus, "should_exit", False)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    monkeypatch.setattr(server.settings, "port", port)
    mount_mcp_server(app)
    uv = uvicorn.Server(uvicorn.Config(app, log_level="debug", lifespan="off"))
    _, handler = server_records
    access_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger = logging.getLogger("uvicorn")
    access_logger.addHandler(handler)
    uvicorn_logger.addHandler(handler)
    logging.getLogger().addHandler(handler)
    task = asyncio.create_task(uv.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not uv.started:
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        uv.should_exit = True
        await asyncio.wait_for(task, 10)
        access_logger.removeHandler(handler)
        uvicorn_logger.removeHandler(handler)
        logging.getLogger().removeHandler(handler)
        sock.close()
        records, _ = server_records
        assert not [
            record
            for record in records
            if record.name == "uvicorn.error"
            and "Exception in ASGI application" in record.getMessage()
        ], "Uvicorn reported an ASGI application error"


@asynccontextmanager
async def session_at(url, key=None):
    headers = {"X-Gatekeeper-API-Key": key} if key else None
    async with sse_client(f"{url}/mcp/sse", headers=headers) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=5) as session:
            await session.initialize()
            yield session


@pytest.mark.asyncio
async def test_sse_graceful_drain_completes_without_asgi_error(live_server, server_records):
    from sse_starlette.sse import AppStatus

    async with httpx.AsyncClient(timeout=5) as client:
        async with client.stream("GET", f"{live_server}/mcp/sse") as response:
            assert response.status_code == 200
            AppStatus.should_exit = True
            async with asyncio.timeout(5):
                async for _ in response.aiter_bytes():
                    pass
    await asyncio.sleep(0.1)
    assert not [r for r in server_records[0] if r.name == "uvicorn.error" and r.exc_info]


@pytest.mark.asyncio
async def test_mcp_v1_client_compatibility(live_server, api_key):
    python = os.environ.get("MCP_V1_PYTHON")
    if not python:
        pytest.skip("set MCP_V1_PYTHON to a Python environment with mcp==1.30.0")
    with patch("gatekeeper.api.proxy.GoogleProxy") as proxy_cls:
        proxy_cls.return_value.call_google = AsyncMock(return_value={"ok": True})
        process = await asyncio.create_subprocess_exec(
            python,
            str(Path(__file__).with_name("mcp_v1_client.py")),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps({"url": live_server, "key": api_key}).encode()), 20
            )
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        assert process.returncode == 0, (stdout.decode(), stderr.decode())
        assert proxy_cls.return_value.call_google.await_args.kwargs["params"] == {"q": "v1"}


@pytest.mark.asyncio
async def test_sse_auth_and_debug_logs(live_server, api_key, caplog, server_records):
    caplog.set_level(logging.DEBUG)
    # Client and HTTP wire debug logs run in this same process, but are not server logs.
    for name in ("mcp.client", "httpcore", "httpcore2", "httpx", "httpx2"):
        caplog.set_level(logging.WARNING, logger=name)
    secret_argument = "fake-sensitive-argument-value"
    fallback = "fake-fallback-secret"
    secret_response = "fake-sensitive-tool-response"
    session_ids = []
    with patch("gatekeeper.api.proxy.GoogleProxy") as proxy_cls:
        proxy = proxy_cls.return_value
        proxy.call_google = AsyncMock(return_value={"value": secret_response})
        async with sse_client(
            f"{live_server}/mcp/sse",
            headers={"X-Gatekeeper-API-Key": api_key},
            on_session_created=session_ids.append,
        ) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=5) as session:
                await session.initialize()
                result = await session.call_tool(
                    "drive__files_list", {"api_key": fallback, "q": secret_argument}
                )
                assert json.loads(result.content[0].text) == {"value": secret_response}
        assert proxy.call_google.await_args.kwargs["params"] == {"q": secret_argument}

    assert len(session_ids) == 1
    records, _ = server_records
    server_logs = "\n".join(logging.Formatter().format(record) for record in records)
    for secret in (fallback, secret_argument, secret_response, api_key, str(session_ids[0])):
        assert secret not in server_logs
    assert any(record.name == "sse_starlette.sse" for record in records)
    assert any(
        record.name == "uvicorn.access" and '"POST /mcp/messages/ HTTP/' in record.getMessage()
        for record in records
    )
    assert "MCP transport event (details suppressed)" in server_logs


@pytest.mark.asyncio
async def test_sse_tool_call_still_writes_audit_log(live_server, api_key, db_session, monkeypatch):
    from sqlalchemy import select

    import gatekeeper.db
    import gatekeeper.logging
    from gatekeeper.models import AuditLog

    monkeypatch.setattr(gatekeeper.logging, "async_session", gatekeeper.db.async_session)
    with patch("gatekeeper.api.proxy.credential_manager.get_credentials", return_value=None):
        async with session_at(live_server, api_key) as session:
            result = await session.call_tool("drive__files_list", {})
            assert json.loads(result.content[0].text)["status"] == 401

    audit = (await db_session.execute(select(AuditLog))).scalars().all()
    assert len(audit) == 1
    assert (audit[0].module, audit[0].route, audit[0].status_code) == (
        "drive",
        "drive.files.list",
        401,
    )


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
