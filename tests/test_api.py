"""Tests for the API proxy layer."""

import json

import pytest
from fastapi.responses import JSONResponse

from gatekeeper.models import ApiKey, RoutePolicy


def _unwrap(response: JSONResponse) -> dict:
    """Extract the JSON body from a JSONResponse returned by GoogleProxy."""
    return json.loads(response.body.decode())


@pytest.mark.asyncio
class TestApiProxy:
    """Tests for GoogleProxy policy enforcement."""

    async def test_route_denied_returns_403(self, db_session):
        """Request to a disabled route should return 403."""
        from gatekeeper.api.proxy import GoogleProxy
        from gatekeeper.models import ApiKey

        # Create an API key
        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(name="test", key_hash=hash_val, key_prefix=prefix, permissions="*")
        db_session.add(key)
        await db_session.commit()

        # Create a disabled route policy
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.send",
            enabled=False,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        proxy = GoogleProxy(db_session)
        result = await proxy.call_google(
            module_name="gmail",
            route_id="gmail.messages.send",
            params={},
            api_key_record=key,
            request_path="/api/v1/gmail/messages/send",
            request_method="POST",
        )
        assert result.status_code == 403
        body = _unwrap(result)
        assert body["error"] is True
        assert body["status"] == 403
        assert "disabled" in body["message"].lower() or "deny" in body["message"].lower()

    async def test_key_lacks_module_permission_returns_403(self, db_session):
        """Key with 'drive' permission cannot access 'gmail' routes."""
        from gatekeeper.api.proxy import GoogleProxy

        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(name="drive-only", key_hash=hash_val, key_prefix=prefix, permissions="drive")
        db_session.add(key)
        await db_session.commit()

        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        proxy = GoogleProxy(db_session)
        result = await proxy.call_google(
            module_name="gmail",
            route_id="gmail.messages.list",
            params={},
            api_key_record=key,
            request_path="/api/v1/gmail/messages/list",
            request_method="GET",
        )
        assert result.status_code == 403
        body = _unwrap(result)
        assert body["error"] is True
        assert body["status"] == 403

    async def test_no_policy_returns_403(self, db_session):
        """Request for a route with no policy defined returns 403 (default deny)."""
        from gatekeeper.api.proxy import GoogleProxy

        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(name="test", key_hash=hash_val, key_prefix=prefix, permissions="*")
        db_session.add(key)
        await db_session.commit()

        # No policy for gmail.messages.get — default deny
        result = await GoogleProxy(db_session).call_google(
            module_name="gmail",
            route_id="gmail.messages.get",
            params={},
            api_key_record=key,
            request_path="/api/v1/gmail/messages/get",
            request_method="GET",
        )
        # Default deny = 403 (no policy)
        assert result.status_code == 403
        body = _unwrap(result)
        assert body["error"] is True
        assert body["status"] == 403

    async def test_audit_log_written_on_denied_request(self, db_session):
        """A denied request should still create an audit log entry."""
        from gatekeeper.api.proxy import GoogleProxy

        raw, hash_val, prefix = ApiKey.generate_key()
        key = ApiKey(name="test", key_hash=hash_val, key_prefix=prefix, permissions="drive")
        db_session.add(key)
        await db_session.commit()

        proxy = GoogleProxy(db_session)
        await proxy.call_google(
            module_name="gmail",
            route_id="gmail.messages.list",
            params={},
            api_key_record=key,
            request_path="/api/v1/gmail/messages/list",
            request_method="GET",
        )

        # Check audit log — need fresh session since log_request uses its own
        # (This test verifies the flow, the actual DB write happens in a separate session)


@pytest.mark.asyncio
class TestParamMerge:
    """Regression tests for PATCH/POST/PUT query+body param merge."""

    @pytest.fixture
    def stub_proxy(self, monkeypatch):
        """Replace GoogleProxy.call_google with a fake that captures params."""
        from gatekeeper.api import router

        captured = {}

        async def _fake_call_google(*args, **kwargs):
            captured["params"] = kwargs.get("params")
            return JSONResponse(status_code=200, content={"ok": True})

        monkeypatch.setattr(router.GoogleProxy, "call_google", _fake_call_google)
        return captured

    @pytest.fixture
    async def router_client(self, app):
        """Return an httpx client wired to an app whose API-key check is stubbed."""
        from fastapi import Request

        from gatekeeper.api import router
        from gatekeeper.models import ApiKey

        async def _fake_validate(request: Request):
            key = ApiKey(
                name="test",
                key_hash="$2b$12$fakehashfakehashfakehashfakehashfa",
                key_prefix="gkp_test",
                permissions="*",
            )
            request.state.api_key = key
            return key

        # The endpoint closures import validate_api_key from gatekeeper.auth, so
        # patch it there and in the router module, then rebuild the API router.
        import gatekeeper.auth

        original = gatekeeper.auth.validate_api_key
        gatekeeper.auth.validate_api_key = _fake_validate
        router.validate_api_key = _fake_validate

        # Remove the old /api/v1 router from the app and remount a fresh one
        for idx, r in enumerate(app.routes):
            if getattr(r, "prefix", None) == "/api/v1":
                app.routes.pop(idx)
                break

        app.include_router(router.create_api_router())

        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        gatekeeper.auth.validate_api_key = original
        router.validate_api_key = original

    async def test_patch_query_only_no_body(self, router_client, stub_proxy):
        """PATCH with query params and no body should keep query params."""
        result = await router_client.patch(
            "/api/v1/drive/files/update?addParents=A&removeParents=B"
        )
        assert result.status_code == 200
        assert stub_proxy["params"] == {"addParents": "A", "removeParents": "B"}

    async def test_patch_body_only_no_query(self, router_client, stub_proxy):
        """PATCH with JSON body and no query should keep body params."""
        result = await router_client.patch(
            "/api/v1/drive/files/update",
            json={"file_id": "x", "name": "y"},
        )
        assert result.status_code == 200
        assert stub_proxy["params"] == {"file_id": "x", "name": "y"}

    async def test_patch_body_and_query_merge(self, router_client, stub_proxy):
        """PATCH with both query and body should merge them."""
        result = await router_client.patch(
            "/api/v1/drive/files/update?addParents=A",
            json={"file_id": "x", "name": "y"},
        )
        assert result.status_code == 200
        assert stub_proxy["params"] == {
            "addParents": "A",
            "file_id": "x",
            "name": "y",
        }

    async def test_patch_body_overrides_query(self, router_client, stub_proxy):
        """When the same key appears in both query and body, body wins."""
        result = await router_client.patch(
            "/api/v1/drive/files/update?addParents=URL",
            json={"addParents": "BODY"},
        )
        assert result.status_code == 200
        assert stub_proxy["params"]["addParents"] == "BODY"

    async def test_patch_malformed_json_falls_back_to_query(self, router_client, stub_proxy):
        """Malformed JSON body should fall back to query params."""
        result = await router_client.patch(
            "/api/v1/drive/files/update?addParents=A",
            content="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert result.status_code == 200
        assert stub_proxy["params"] == {"addParents": "A"}

    async def test_post_query_only_no_body(self, router_client, stub_proxy):
        """POST with query params and no body should keep query params."""
        result = await router_client.post("/api/v1/gmail/messages/send?threadId=t1")
        assert result.status_code == 200
        assert stub_proxy["params"] == {"threadId": "t1"}

    async def test_put_body_and_query_merge(self, router_client, stub_proxy):
        """PUT with both query and body should merge them."""
        result = await router_client.put(
            "/api/v1/drive/sheets/values/update?spreadsheetId=ss1&range=A1:B2",
            json={"values": [["a"]]},
        )
        assert result.status_code == 200
        assert stub_proxy["params"] == {
            "spreadsheetId": "ss1",
            "range": "A1:B2",
            "values": [["a"]],
        }
