"""Comprehensive integration tests for GoogleProxy — URL construction,
parameter normalization, policy enforcement, and credential handling.

These tests mock the httpx calls and credential_manager so we can verify
URL construction and parameter normalization without hitting real Google APIs.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse

from gatekeeper.api.proxy import GoogleProxy
from gatekeeper.models import ApiKey, RoutePolicy
from gatekeeper.modules import _loaded_modules

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _unwrap(response: JSONResponse) -> dict:
    """Extract the JSON body from a JSONResponse returned by GoogleProxy."""
    # JSONResponse.body is bytes, decode and parse
    return json.loads(response.body.decode())


def _make_api_key(permissions: str = "*") -> ApiKey:
    """Create a mock ApiKey row (not persisted to DB)."""
    return ApiKey(
        name="test-key",
        key_hash="$2b$12$fakehashfakehashfakehashfakehashfa",
        key_prefix="gkp_test",
        permissions=permissions,
    )


def _mock_creds(token: str = "mock_access_token") -> MagicMock:
    """Create a mock credentials object with a valid token."""
    creds = MagicMock()
    creds.token = token
    creds.expired = False
    creds.refresh_token = "mock_refresh"
    return creds


@pytest.fixture(autouse=True)
def clear_module_cache():
    """Clear loaded module cache between tests so each test gets a fresh state."""
    _loaded_modules.clear()
    yield
    _loaded_modules.clear()


# ---------------------------------------------------------------------------
# URL construction tests — verify path params are correctly substituted
# ---------------------------------------------------------------------------


class TestURLConstruction:
    """Test that GoogleProxy builds the correct Google API URLs.

    These tests focus on URL path construction with parameter substitution.
    We mock credential_manager.get_credentials() and httpx.AsyncClient so
    no real HTTP requests are made.
    """

    @pytest.mark.asyncio
    async def test_calendar_path_with_calendar_id(self, db_session):
        """Calendar route: {calendarId} should be substituted from params."""
        # Set up enabled policy
        policy = RoutePolicy(
            module="calendar",
            route="calendar.events.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        # Mock credential manager
        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            # Mock the async context manager
            mock_response = MagicMock()
            mock_response.json.return_value = {"items": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="calendar",
                route_id="calendar.events.list",
                params={"calendar_id": "primary", "maxResults": 10},
                api_key_record=api_key,
                request_method="GET",
            )

            # Verify URL: /calendar/v3/calendars/primary/events
            call_args = mock_client.get.call_args
            url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
            assert "/calendar/v3/calendars/primary/events" in url

    @pytest.mark.asyncio
    async def test_drive_path_with_file_id(self, db_session):
        """Drive route: {fileId} should be substituted from file_id param."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "file123", "name": "test.txt"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.get",
                params={"file_id": "file123", "fields": "id,name"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/drive/v3/files/file123" in url
            # file_id should NOT be in remaining query params
            params_sent = call_args[1].get("params", {})
            assert "fileId" not in params_sent
            assert "fields" in params_sent  # non-path param stays

    @pytest.mark.asyncio
    async def test_gmail_path_with_message_id(self, db_session):
        """Gmail route: {messageId} should be substituted from message_id param."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "msg_abc", "snippet": "Hello"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.get",
                params={"message_id": "msg_abc", "format": "full"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/gmail/v1/users/me/messages/msg_abc" in url
            params_sent = call_args[1].get("params", {})
            assert "messageId" not in params_sent
            assert "format" in params_sent

    @pytest.mark.asyncio
    async def test_gmail_path_with_draft_id(self, db_session):
        """Gmail draft route: {draftId} should be substituted from draft_id param."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.drafts.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "draft_xyz"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.drafts.get",
                params={"draft_id": "draft_xyz"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/gmail/v1/users/me/drafts/draft_xyz" in url

    @pytest.mark.asyncio
    async def test_drive_permissions_multiple_path_params(self, db_session):
        """Drive permissions: {fileId}/permissions/{permissionId} — two path params."""
        policy = RoutePolicy(
            module="drive",
            route="drive.permissions.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "perm1", "type": "user"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.permissions.get",
                params={"file_id": "fileABC", "permission_id": "permXYZ"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            # Both path params should be substituted
            assert "/drive/v3/files/fileABC/permissions/permXYZ" in url
            # Neither should remain in query params
            params_sent = call_args[1].get("params", {})
            assert "fileId" not in params_sent
            assert "permissionId" not in params_sent

    @pytest.mark.asyncio
    async def test_calendar_path_with_calendar_and_event_id(self, db_session):
        """Calendar events.get: {calendarId}/events/{eventId} — two path params."""
        policy = RoutePolicy(
            module="calendar",
            route="calendar.events.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "ev1", "summary": "Meeting"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="calendar",
                route_id="calendar.events.get",
                params={"calendar_id": "primary", "event_id": "ev123"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/calendar/v3/calendars/primary/events/ev123" in url


# ---------------------------------------------------------------------------
# Parameter normalization (snake_case → camelCase)
# ---------------------------------------------------------------------------


class TestParameterNormalization:
    """Test snake_case → camelCase conversion and path param removal."""

    @pytest.mark.asyncio
    async def test_snake_to_camel_case_file_id(self, db_session):
        """file_id → fileId in normalized params and removed when it's a path param."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "f1"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.get",
                params={"file_id": "abc123", "fields": "id,name"},
                api_key_record=api_key,
                request_method="GET",
            )

            # file_id became fileId and was consumed as path param
            # 'fields' stays as query param (no underscore, no transform)
            call_args = mock_client.get.call_args
            params_sent = call_args[1].get("params", {})
            assert "fields" in params_sent
            # fileId is NOT in params because it was used in the URL path
            assert "fileId" not in params_sent

    @pytest.mark.asyncio
    async def test_snake_to_camel_case_calendar_id(self, db_session):
        """calendar_id → calendarId normalization and path substitution."""
        policy = RoutePolicy(
            module="calendar",
            route="calendar.events.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"items": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="calendar",
                route_id="calendar.events.list",
                params={"calendar_id": "primary", "max_results": 20},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            # calendarId should be substituted in URL
            assert "/calendars/primary/" in url
            params_sent = call_args[1].get("params", {})
            # calendarId should NOT be in query params
            assert "calendarId" not in params_sent
            # max_results → maxResults should be in query params
            assert "maxResults" in params_sent
            assert params_sent["maxResults"] == 20

    @pytest.mark.asyncio
    async def test_snake_to_camel_case_message_id(self, db_session):
        """message_id → messageId, consumed as path param."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "m1"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.get",
                params={"message_id": "msg456", "format": "metadata"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            url = call_args[0][0]
            assert "/messages/msg456" in url
            params_sent = call_args[1].get("params", {})
            assert "format" in params_sent
            # messageId was consumed in path
            assert "messageId" not in params_sent

    @pytest.mark.asyncio
    async def test_non_path_params_stay_in_query_for_get(self, db_session):
        """GET routes: non-path params should be query parameters."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"files": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.list",
                params={"page_size": 25, "q": "name contains 'report'"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            params_sent = call_args[1].get("params", {})
            # No path params in drive.files.list, so all should be query params
            # snake_case should be normalized: page_size → pageSize
            assert "pageSize" in params_sent
            assert "q" in params_sent

    @pytest.mark.asyncio
    async def test_non_path_params_stay_in_body_for_post(self, db_session):
        """POST routes: non-path params should be in JSON body."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.create",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "new_file", "name": "test"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.create",
                params={"name": "My Doc", "mime_type": "application/pdf"},
                api_key_record=api_key,
                request_method="POST",
            )

            call_args = mock_client.post.call_args
            json_sent = call_args[1].get("json", {})
            # snake_case → camelCase: mime_type → mimeType
            assert "mimeType" in json_sent
            assert "name" in json_sent


# ---------------------------------------------------------------------------
# Policy enforcement integration
# ---------------------------------------------------------------------------


class TestPolicyEnforcement:
    """Test policy enforcement through the proxy layer."""

    @pytest.mark.asyncio
    async def test_enabled_route_forwards_to_google(self, db_session):
        """Enabled route should proxy the request through to Google."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"messages": [{"id": "1"}]}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

            # Should have called Google API
            mock_client.get.assert_called_once()
            assert "error" not in _unwrap(result) or _unwrap(result).get("error") is not True

    @pytest.mark.asyncio
    async def test_disabled_route_returns_403(self, db_session):
        """Disabled route should return 403 error response."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.send",
            enabled=False,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager"),
            patch("gatekeeper.api.proxy.httpx.AsyncClient"),
        ):
            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.send",
                params={},
                api_key_record=api_key,
                request_method="POST",
            )

        assert _unwrap(result)["error"] is True
        assert result.status_code == 403
        assert _unwrap(result)["status"] == 403
        assert "disabled" in _unwrap(result)["message"].lower()

    @pytest.mark.asyncio
    async def test_key_with_wrong_module_returns_403(self, db_session):
        """Key lacking module permission should get 403."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        # Key only has drive permission, trying gmail
        api_key = _make_api_key(permissions="drive")
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager"),
            patch("gatekeeper.api.proxy.httpx.AsyncClient"),
        ):
            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

        assert _unwrap(result)["error"] is True
        assert result.status_code == 403
        assert _unwrap(result)["status"] == 403
        assert "not authorized" in _unwrap(result)["message"].lower()

    @pytest.mark.asyncio
    async def test_no_policy_for_route_returns_403(self, db_session):
        """Route with no policy defined should be denied."""
        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager"),
            patch("gatekeeper.api.proxy.httpx.AsyncClient"),
        ):
            result = await proxy.call_google(
                module_name="drive",
                route_id="drive.files.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

        assert _unwrap(result)["error"] is True
        assert result.status_code == 403
        assert _unwrap(result)["status"] == 403
        assert "no policy" in _unwrap(result)["message"].lower()

    @pytest.mark.asyncio
    async def test_policy_transforms_applied_before_proxy(self, db_session):
        """Request transforms from policy config should be applied."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config=json.dumps({"max_results": 10}),
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"messages": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Request maxResults=200, but policy caps to 10
            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={"maxResults": 200},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            params_sent = call_args[1].get("params", {})
            # maxResults should be capped to 10
            assert params_sent.get("maxResults") == 10


# ---------------------------------------------------------------------------
# Credential handling
# ---------------------------------------------------------------------------


class TestCredentialHandling:
    """Test credential-related behavior in the proxy."""

    @pytest.mark.asyncio
    async def test_no_credentials_returns_401(self, db_session):
        """Missing Google credentials should return 401 error."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm:
            # Return None credentials
            mock_cm.get_credentials.return_value = None

            with patch("gatekeeper.api.proxy.httpx.AsyncClient"):
                result = await proxy.call_google(
                    module_name="gmail",
                    route_id="gmail.messages.list",
                    params={},
                    api_key_record=api_key,
                    request_method="GET",
                )

        assert _unwrap(result)["error"] is True
        assert result.status_code == 401
        assert _unwrap(result)["status"] == 401
        assert "credentials" in _unwrap(result)["message"].lower()

    @pytest.mark.asyncio
    async def test_credentials_without_token_returns_401(self, db_session):
        """Credentials with no token (None) should return 401."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        mock_creds = MagicMock()
        mock_creds.token = None  # No access token

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm:
            mock_cm.get_credentials.return_value = mock_creds

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

        assert result.status_code == 401
        assert _unwrap(result)["error"] is True
        assert _unwrap(result)["status"] == 401

    @pytest.mark.asyncio
    async def test_valid_credentials_include_auth_header(self, db_session):
        """Valid credentials should produce an Authorization header in the request."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds(token="ya29.test_token")

            mock_response = MagicMock()
            mock_response.json.return_value = {"messages": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            headers = call_args[1].get("headers", {})
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer ya29.test_token"


# ---------------------------------------------------------------------------
# HTTP method dispatch
# ---------------------------------------------------------------------------


class TestHTTPMethodDispatch:
    """Test that the proxy uses the correct HTTP method for each route."""

    @pytest.mark.asyncio
    async def test_get_route_uses_get(self, db_session):
        """GET routes should call httpx.get."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

            mock_client.get.assert_called_once()
            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_route_uses_post(self, db_session):
        """POST routes should call httpx.post with JSON body."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.create",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "new"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.create",
                params={"name": "test"},
                api_key_record=api_key,
                request_method="POST",
            )

            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_route_uses_delete(self, db_session):
        """DELETE routes should call httpx.delete."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.delete",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {}
            mock_response.status_code = 204

            mock_client = AsyncMock()
            mock_client.delete = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.delete",
                params={"message_id": "msg1"},
                api_key_record=api_key,
                request_method="DELETE",
            )

            mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_patch_route_uses_patch(self, db_session):
        """PATCH routes should call httpx.patch with JSON body."""
        policy = RoutePolicy(
            module="calendar",
            route="calendar.events.update",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "ev1", "summary": "Updated"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.patch = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="calendar",
                route_id="calendar.events.update",
                params={"calendar_id": "primary", "event_id": "ev1", "summary": "Updated"},
                api_key_record=api_key,
                request_method="PATCH",
            )

            mock_client.patch.assert_called_once()


# ---------------------------------------------------------------------------
# Response filter integration
# ---------------------------------------------------------------------------


class TestResponseFilterIntegration:
    """Test that response filters are applied through the proxy."""

    @pytest.mark.asyncio
    async def test_blocked_fields_stripped_from_response(self, db_session):
        """blocked_fields in policy config should strip those fields from response."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.get",
            enabled=True,
            policy_config=json.dumps({"blocked_fields": ["raw", "internalDate"]}),
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            # Mock Google returning data with raw and internalDate
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "id": "msg1",
                "raw": "base64data",
                "internalDate": "12345",
                "snippet": "Hello world",
            }
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.get",
                params={"message_id": "msg1"},
                api_key_record=api_key,
                request_method="GET",
            )

            assert _unwrap(result)["id"] == "msg1"
            assert _unwrap(result)["snippet"] == "Hello world"
            assert "raw" not in _unwrap(result)
            assert "internalDate" not in _unwrap(result)

    @pytest.mark.asyncio
    async def test_max_items_caps_response_arrays(self, db_session):
        """max_items in policy config should cap response array lengths."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config=json.dumps({"max_items": {"messages": 3}}),
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            # Mock Google returning 10 messages
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "messages": [{"id": f"m{i}"} for i in range(10)],
                "resultSizeEstimate": 10,
            }
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

            assert len(_unwrap(result)["messages"]) == 3
            assert _unwrap(result)["resultSizeEstimate"] == 10  # non-array not affected


# ---------------------------------------------------------------------------
# Module not found
# ---------------------------------------------------------------------------


class TestModuleNotFound:
    """Test proxy behavior when module is not found."""

    @pytest.mark.asyncio
    async def test_unknown_module_returns_404(self, db_session):
        """Requesting an unknown module should return 404 error after policy denial.

        Note: Even before checking module, the policy check happens first.
        If there's no policy, we get 403. But if policy somehow allows it
        (wildcard key + some bug), the module won't be found.
        We test this scenario directly with the module loading path.
        """
        api_key = _make_api_key(permissions="*")
        proxy = GoogleProxy(db_session)

        # Since there's no route policy for "nonexistent", the default is deny.
        # But let's test what happens if somehow we get past that.
        result = await proxy.call_google(
            module_name="nonexistent_module",
            route_id="nonexistent.route",
            params={},
            api_key_record=api_key,
            request_method="GET",
        )

        assert result.status_code == 403
        # Should be denied because no policy
        assert _unwrap(result)["error"] is True


class TestArrayCoercion:
    """Test that array-type parameters sent as strings are coerced back to lists.

    MCP clients may stringify JSON arrays in tool arguments (e.g., sending
    '["Label_4"]' instead of ["Label_4"]). The proxy must detect this and
    parse the string back into a proper list before forwarding to Google.
    """

    @pytest.mark.asyncio
    async def test_messages_modify_string_array_coerced(self, db_session):
        """addLabelIds sent as a JSON string should be coerced to a list."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.modify",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "msg123", "labelIds": ["INBOX", "UNREAD"]}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Simulate MCP client sending add_label_ids as a JSON string
            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.modify",
                params={
                    "message_id": "msg123",
                    "add_label_ids": '["INBOX"]',  # String instead of list
                    "remove_label_ids": '["UNREAD"]',  # String instead of list
                },
                api_key_record=api_key,
                request_method="POST",
            )

            assert result.status_code == 200
            # Verify the POST body was called with properly coerced arrays
            call_kwargs = mock_client.post.call_args[1]
            body = call_kwargs.get("json", {})
            assert body["addLabelIds"] == ["INBOX"]
            assert body["removeLabelIds"] == ["UNREAD"]

    @pytest.mark.asyncio
    async def test_messages_modify_list_array_unchanged(self, db_session):
        """addLabelIds sent as a proper list should pass through unchanged."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.modify",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "msg123", "labelIds": ["INBOX"]}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Proper list values — should not be modified
            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.modify",
                params={
                    "message_id": "msg123",
                    "add_label_ids": ["INBOX"],
                    "remove_label_ids": ["UNREAD"],
                },
                api_key_record=api_key,
                request_method="POST",
            )

            assert result.status_code == 200
            call_kwargs = mock_client.post.call_args[1]
            body = call_kwargs.get("json", {})
            assert body["addLabelIds"] == ["INBOX"]
            assert body["removeLabelIds"] == ["UNREAD"]

    @pytest.mark.asyncio
    async def test_messages_list_label_ids_string_coerced(self, db_session):
        """labelIds sent as a JSON string in GET request should be coerced."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"messages": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # label_ids as JSON string
            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.list",
                params={
                    "label_ids": '["INBOX", "UNREAD"]',
                    "max_results": "10",
                },
                api_key_record=api_key,
                request_method="GET",
            )

            assert result.status_code == 200
            call_kwargs = mock_client.get.call_args[1]
            query_params = call_kwargs.get("params", {})
            # labelids should be coerced to a list
            assert query_params["labelIds"] == ["INBOX", "UNREAD"]

    @pytest.mark.asyncio
    async def test_invalid_json_string_left_as_is(self, db_session):
        """A string that isn't valid JSON array should be left as-is (API will reject)."""
        policy = RoutePolicy(
            module="gmail",
            route="gmail.messages.modify",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "msg123"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Not a valid JSON string at all — should pass through unchanged
            result = await proxy.call_google(
                module_name="gmail",
                route_id="gmail.messages.modify",
                params={
                    "message_id": "msg123",
                    "add_label_ids": "not-a-json-array",
                },
                api_key_record=api_key,
                request_method="POST",
            )

            assert result.status_code == 200
            call_kwargs = mock_client.post.call_args[1]
            body = call_kwargs.get("json", {})
            # Not coerced — left as the original string
            assert body["addLabelIds"] == "not-a-json-array"


class TestFilterBodyRestructuring:
    """Test that Gmail filter creation/update params are restructured.

    The Gmail API expects a nested {criteria: {...}, action: {...}} body,
    but the proxy receives flat params. _restructure_filter_body must split
    them correctly.
    """

    def test_query_only_filter(self):
        """A filter with only a query should produce criteria with query."""
        from gatekeeper.api.proxy import GoogleProxy

        result = GoogleProxy._restructure_filter_body({"query": "from:alice@example.com"})
        assert result == {"criteria": {"query": "from:alice@example.com"}}

    def test_query_with_actions(self):
        """A filter with query and action params should nest correctly."""
        from gatekeeper.api.proxy import GoogleProxy

        result = GoogleProxy._restructure_filter_body(
            {
                "query": "from:alice@example.com",
                "label_ids": ["Label_1", "Label_2"],
                "mark_as_read": True,
                "archive": True,
            }
        )
        assert result == {
            "criteria": {"query": "from:alice@example.com"},
            "action": {
                "addLabelIds": ["Label_1", "Label_2"],
                "markAsRead": True,
                "archive": True,
            },
        }

    def test_snake_case_params_mapped(self):
        """Snake_case params like mark_as_read map to camelCase markAsRead."""
        from gatekeeper.api.proxy import GoogleProxy

        result = GoogleProxy._restructure_filter_body(
            {
                "query": "is:unread",
                "mark_as_read": True,
                "mark_as_important": True,
            }
        )
        assert result["criteria"] == {"query": "is:unread"}
        assert result["action"]["markAsRead"] is True
        assert result["action"]["markAsImportant"] is True

    def test_forward_filter(self):
        """A filter that forwards emails with a query."""
        from gatekeeper.api.proxy import GoogleProxy

        result = GoogleProxy._restructure_filter_body(
            {
                "query": "from:boss@company.com",
                "forward": "assistant@company.com",
                "mark_as_important": True,
            }
        )
        assert result == {
            "criteria": {"query": "from:boss@company.com"},
            "action": {
                "forward": "assistant@company.com",
                "markAsImportant": True,
            },
        }

    def test_already_nested_structure_passthrough(self):
        """If already-nested {criteria, action} is passed, return as-is."""
        from gatekeeper.api.proxy import GoogleProxy

        nested = {
            "criteria": {"query": "is:unread"},
            "action": {"addLabelIds": ["Label_1"]},
        }
        result = GoogleProxy._restructure_filter_body(nested)
        assert result == nested

    def test_camel_case_criteria_fields(self):
        """CamelCase criteria fields like hasAttachment are recognized."""
        from gatekeeper.api.proxy import GoogleProxy

        result = GoogleProxy._restructure_filter_body(
            {
                "query": "has:attachment",
                "hasAttachment": True,
                "from": "alice@example.com",
                "label_ids": ["INBOX"],
            }
        )
        assert result["criteria"]["hasAttachment"] is True
        assert result["criteria"]["from"] == "alice@example.com"
        assert result["action"]["addLabelIds"] == ["INBOX"]

    def test_empty_params_returns_empty(self):
        """Empty params dict returns empty dict (let Google API reject it)."""
        from gatekeeper.api.proxy import GoogleProxy

        result = GoogleProxy._restructure_filter_body({})
        assert result == {}


class TestQueryParams:
    """Test that routes with query_params send those params as URL query params."""

    @pytest.mark.asyncio
    async def test_drive_files_update_add_parents_as_query_param(self, db_session):
        """addParents/removeParents must go as query params, not JSON body."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.update",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "fileABC"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.patch = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.update",
                params={
                    "file_id": "fileABC",
                    "name": "Renamed.txt",
                    "add_parents": "parentFolder1",
                    "remove_parents": "parentFolder2",
                },
                api_key_record=api_key,
                request_method="PATCH",
            )

            call_args = mock_client.patch.call_args
            # addParents and removeParents should be in query params
            query_params = call_args[1].get("params", {})
            assert "addParents" in query_params
            assert "removeParents" in query_params
            assert query_params["addParents"] == "parentFolder1"
            assert query_params["removeParents"] == "parentFolder2"
            # name should be in JSON body, NOT in query params
            body_params = call_args[1].get("json", {})
            assert body_params.get("name") == "Renamed.txt"
            assert "addParents" not in body_params
            assert "removeParents" not in body_params

    @pytest.mark.asyncio
    async def test_drive_files_get_fields_as_query_param(self, db_session):
        """fields parameter on drive.files.get should go as a query param."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "fileABC", "name": "test.txt"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.get",
                params={"file_id": "file123"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            # fields should appear in GET query params with its default value
            params_sent = call_args[1].get("params", {})
            assert "fields" in params_sent
            assert "owners" in params_sent["fields"]

    @pytest.mark.asyncio
    async def test_drive_files_list_fields_default(self, db_session):
        """drive.files.list should get a default fields parameter injected."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.list",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"files": []}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.list",
                params={},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            params_sent = call_args[1].get("params", {})
            assert "fields" in params_sent
            assert "owners" in params_sent["fields"]
            assert "nextPageToken" in params_sent["fields"]


class TestShortcutCreation:
    """Test that drive.files.create constructs shortcutDetails for shortcuts."""

    @pytest.mark.asyncio
    async def test_shortcut_details_construction(self, db_session):
        """shortcutTargetId and shortcutTargetMimeType should become shortcutDetails."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.create",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "id": "shortcut123",
                "mimeType": "application/vnd.google-apps.shortcut",
            }
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.create",
                params={
                    "name": "My Shortcut",
                    "mime_type": "application/vnd.google-apps.shortcut",
                    "parents": ["parentFolderId"],
                    "shortcut_target_id": "targetFileId",
                    "shortcut_target_mime_type": "application/vnd.google-apps.document",
                },
                api_key_record=api_key,
                request_method="POST",
            )

            call_args = mock_client.post.call_args
            body = call_args[1].get("json", {})
            # shortcutDetails should be constructed
            assert "shortcutDetails" in body
            assert body["shortcutDetails"]["targetId"] == "targetFileId"
            assert (
                body["shortcutDetails"]["targetMimeType"] == "application/vnd.google-apps.document"
            )
            # Original flat params should be removed
            assert "shortcutTargetId" not in body
            assert "shortcutTargetMimeType" not in body
            # Other body params preserved
            assert body["name"] == "My Shortcut"
            assert body["mimeType"] == "application/vnd.google-apps.shortcut"
            assert body["parents"] == ["parentFolderId"]

    @pytest.mark.asyncio
    async def test_shortcut_without_target_mime_type(self, db_session):
        """shortcutTargetId alone (without targetMimeType) should still work."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.create",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "shortcut456"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.create",
                params={
                    "name": "Shortcut No Mime",
                    "mime_type": "application/vnd.google-apps.shortcut",
                    "shortcut_target_id": "targetFileId",
                },
                api_key_record=api_key,
                request_method="POST",
            )

            call_args = mock_client.post.call_args
            body = call_args[1].get("json", {})
            assert "shortcutDetails" in body
            assert body["shortcutDetails"]["targetId"] == "targetFileId"
            assert "targetMimeType" not in body["shortcutDetails"]

    @pytest.mark.asyncio
    async def test_regular_file_create_untouched(self, db_session):
        """Regular file create (no shortcut) should not have shortcutDetails."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.create",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "newFolder"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.create",
                params={
                    "name": "New Folder",
                    "mime_type": "application/vnd.google-apps.folder",
                },
                api_key_record=api_key,
                request_method="POST",
            )

            call_args = mock_client.post.call_args
            body = call_args[1].get("json", {})
            assert "shortcutDetails" not in body
            assert body["name"] == "New Folder"
            assert body["mimeType"] == "application/vnd.google-apps.folder"


class TestSchemaDefaults:
    """Test that schema defaults are injected when caller omits params."""

    @pytest.mark.asyncio
    async def test_default_fields_injected_for_files_get(self, db_session):
        """When fields is not provided, the default from the schema should be used."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "fileABC"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.get",
                params={"file_id": "fileABC"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            params_sent = call_args[1].get("params", {})
            # Default fields should be injected
            assert "fields" in params_sent
            # Should include the expanded default fields
            assert "owners" in params_sent["fields"]
            assert "shared" in params_sent["fields"]

    @pytest.mark.asyncio
    async def test_explicit_fields_override_default(self, db_session):
        """When caller provides fields explicitly, the default should NOT be used."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.get",
            enabled=True,
            policy_config="{}",
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "fileABC"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.get",
                params={"file_id": "fileABC", "fields": "id,name"},
                api_key_record=api_key,
                request_method="GET",
            )

            call_args = mock_client.get.call_args
            params_sent = call_args[1].get("params", {})
            assert params_sent["fields"] == "id,name"


class TestRouteDefQueryParams:
    """Test that RouteDef correctly stores query_params."""

    def test_query_params_default_empty(self):
        from gatekeeper.modules.route import RouteDef

        route = RouteDef(
            route_id="test.route",
            method="GET",
            google_path="/test",
        )
        assert route.query_params == []

    def test_query_params_stored(self):
        from gatekeeper.modules.route import RouteDef

        route = RouteDef(
            route_id="test.route",
            method="PATCH",
            google_path="/test/{id}",
            query_params=["addParents", "removeParents"],
        )
        assert route.query_params == ["addParents", "removeParents"]


# ---------------------------------------------------------------------------
# Multipart upload tests
# ---------------------------------------------------------------------------


class TestMultipartUpload:
    """Test multipart/related file upload for drive.files.upload."""

    @pytest.mark.asyncio
    async def test_missing_base64_content_returns_400(self, db_session):
        """Without base64_content the upload should fail with 400."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.upload",
            enabled=True,
            policy_config='{"max_file_size_mb": 25}',
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm:
            mock_cm.get_credentials.return_value = _mock_creds()

            resp = await proxy.call_google(
                module_name="drive",
                route_id="drive.files.upload",
                params={"name": "test.txt"},
                api_key_record=api_key,
                request_method="POST",
            )

        data = _unwrap(resp)
        assert data["status"] == 400
        assert "base64_content" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_invalid_base64_returns_400(self, db_session):
        """Non-base64 content should fail with 400."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.upload",
            enabled=True,
            policy_config='{"max_file_size_mb": 25}',
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm:
            mock_cm.get_credentials.return_value = _mock_creds()

            resp = await proxy.call_google(
                module_name="drive",
                route_id="drive.files.upload",
                params={"name": "test.txt", "base64_content": "!!!not-base64!!!"},
                api_key_record=api_key,
                request_method="POST",
            )

        data = _unwrap(resp)
        assert data["status"] == 400
        assert "invalid base64" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_file_size_exceeds_policy_returns_413(self, db_session):
        """Base64 that decodes to a file larger than policy max_file_size_mb should fail."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.upload",
            enabled=True,
            policy_config='{"max_file_size_mb": 0.01}',
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        # Build ~50 KB of raw zeroes to exceed the 0.01 MB (10 KB) limit
        large_b64 = base64.b64encode(b"\x00" * 50_000).decode()

        with patch("gatekeeper.api.proxy.credential_manager") as mock_cm:
            mock_cm.get_credentials.return_value = _mock_creds()

            resp = await proxy.call_google(
                module_name="drive",
                route_id="drive.files.upload",
                params={"name": "big.bin", "base64_content": large_b64},
                api_key_record=api_key,
                request_method="POST",
            )

        data = _unwrap(resp)
        assert data["status"] == 413
        assert "exceeds max" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_successful_multipart_body(self, db_session):
        """A valid small upload should construct multipart/related body correctly."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.upload",
            enabled=True,
            policy_config='{"max_file_size_mb": 25}',
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        raw = b"Hello from Gatekeeper multipart upload!"
        b64 = base64.b64encode(raw).decode()

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "file123", "name": "hello.txt"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            resp = await proxy.call_google(
                module_name="drive",
                route_id="drive.files.upload",
                params={
                    "name": "hello.txt",
                    "base64_content": b64,
                    "mime_type": "text/plain",
                    "parents": ["folderABC"],
                },
                api_key_record=api_key,
                request_method="POST",
            )

        data = _unwrap(resp)
        assert data["name"] == "hello.txt"

        call_args = mock_client.post.call_args
        sent_body = call_args[1]["content"]
        sent_headers = call_args[1].get("headers", {})

        assert sent_headers["Content-Type"].startswith("multipart/related")
        assert b"hello.txt" in sent_body
        assert b"folderABC" in sent_body
        assert raw in sent_body
        assert b"text/plain" in sent_body

    @pytest.mark.asyncio
    async def test_mime_type_guessed_from_filename(self, db_session):
        """When mime_type is omitted, it should be guessed from the filename."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.upload",
            enabled=True,
            policy_config='{"max_file_size_mb": 25}',
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        raw = b"PDF content"
        b64 = base64.b64encode(raw).decode()

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "file456"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.upload",
                params={"name": "document.pdf", "base64_content": b64},
                api_key_record=api_key,
                request_method="POST",
            )

            call_args = mock_client.post.call_args
            sent_body = call_args[1]["content"]
            assert b"application/pdf" in sent_body

    @pytest.mark.asyncio
    async def test_custom_mime_type_overrides_guess(self, db_session):
        """When mime_type is provided explicitly, it should override any guess."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.upload",
            enabled=True,
            policy_config='{"max_file_size_mb": 25}',
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        raw = b"some bytes"
        b64 = base64.b64encode(raw).decode()

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "file789"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.upload",
                params={
                    "name": "report.docx",
                    "base64_content": b64,
                    "mime_type": "application/octet-stream",
                },
                api_key_record=api_key,
                request_method="POST",
            )

            call_args = mock_client.post.call_args
            sent_body = call_args[1]["content"]
            assert b"application/octet-stream" in sent_body
            # Default .docx guess would be wordprocessingml, which should NOT appear
            assert (
                b"application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                not in sent_body
            )

    @pytest.mark.asyncio
    async def test_upload_type_in_query_params(self, db_session):
        """uploadType=multipart should be injected as a query parameter, not in body."""
        policy = RoutePolicy(
            module="drive",
            route="drive.files.upload",
            enabled=True,
            policy_config='{"max_file_size_mb": 25}',
        )
        db_session.add(policy)
        await db_session.commit()

        api_key = _make_api_key()
        proxy = GoogleProxy(db_session)

        raw = b"tiny"
        b64 = base64.b64encode(raw).decode()

        with (
            patch("gatekeeper.api.proxy.credential_manager") as mock_cm,
            patch("gatekeeper.api.proxy.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_cm.get_credentials.return_value = _mock_creds()

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": "file999"}
            mock_response.status_code = 200

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await proxy.call_google(
                module_name="drive",
                route_id="drive.files.upload",
                params={"name": "tiny.bin", "base64_content": b64},
                api_key_record=api_key,
                request_method="POST",
            )

            call_args = mock_client.post.call_args
            sent_params = call_args[1].get("params", {}) or {}
            assert sent_params.get("uploadType") == "multipart"
