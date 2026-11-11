"""Hostname routing tests — prove base_url override routes to the correct Google API host.

These tests use the same mocking pattern as tests/test_proxy.py — credential_manager
and httpx.AsyncClient are mocked so we can inspect the URL the proxy constructs
without hitting real Google APIs.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gatekeeper.api.proxy import GoogleProxy
from gatekeeper.models import ApiKey, RoutePolicy
from gatekeeper.modules import _loaded_modules

# --------------------------------------------------------------------------- #
# Helpers (mirror the patterns in tests/test_proxy.py)
# --------------------------------------------------------------------------- #


def _unwrap(response) -> dict:
    return json.loads(response.body.decode())


def _make_api_key(permissions: str = "*") -> ApiKey:
    return ApiKey(
        name="test-key",
        key_hash="$2b$12$fakehashfakehashfakehashfakehashfa",
        key_prefix="gkp_test",
        permissions=permissions,
    )


def _mock_creds(token: str = "mock_access_token") -> MagicMock:
    creds = MagicMock()
    creds.token = token
    creds.expired = False
    creds.refresh_token = "mock_refresh"
    return creds


@pytest.fixture(autouse=True)
def clear_module_cache():
    _loaded_modules.clear()
    yield
    _loaded_modules.clear()


async def _run_proxy(
    db_session,
    module_name: str,
    route_id: str,
    method: str,
    params: dict,
):
    """Drive a single proxy call with mocked credentials/transport.

    Returns the (URL, query_params, body) sent to httpx.
    """
    policy = RoutePolicy(module=module_name, route=route_id, enabled=True, policy_config="{}")
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
        mock_response.json.return_value = {"status": "ok"}
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_method = AsyncMock(return_value=mock_response)
        setattr(mock_client, method.lower(), mock_method)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await proxy.call_google(
            module_name=module_name,
            route_id=route_id,
            params=params,
            api_key_record=api_key,
            request_method=method,
        )

        call_args = mock_method.call_args
        url = call_args[0][0]
        # body/json may be passed positionally or by keyword depending on method
        kwargs = call_args[1] if len(call_args) > 1 else {}
        return url, kwargs.get("params", {}), kwargs.get("json")


# --------------------------------------------------------------------------- #
# Sheets hostname tests
# --------------------------------------------------------------------------- #


class TestSheetsHostname:
    @pytest.mark.asyncio
    async def test_sheets_spreadsheets_get_hits_sheets_host(self, db_session):
        url, _, _ = await _run_proxy(
            db_session,
            "drive",
            "drive.sheets.spreadsheets.get",
            "GET",
            {"spreadsheet_id": "ss123"},
        )
        assert url.startswith("https://sheets.googleapis.com/"), f"Got: {url}"
        assert "/v4/spreadsheets/ss123" in url
        # Critical: must NOT hit www.googleapis.com
        assert "www.googleapis.com" not in url

    @pytest.mark.asyncio
    async def test_sheets_values_get_hits_sheets_host(self, db_session):
        url, params, _ = await _run_proxy(
            db_session,
            "drive",
            "drive.sheets.values.get",
            "GET",
            {"spreadsheet_id": "ss1", "range": "A1:B2"},
        )
        assert url.startswith("https://sheets.googleapis.com/"), f"Got: {url}"
        assert "/v4/spreadsheets/ss1/values/A1:B2" in url
        assert "www.googleapis.com" not in url
        # Range param must NOT appear in the URL (it's in the path)
        assert "range" not in params or "A1:B2" in url

    @pytest.mark.asyncio
    async def test_sheets_values_update_hits_sheets_host(self, db_session):
        url, _, json_body = await _run_proxy(
            db_session,
            "drive",
            "drive.sheets.values.update",
            "PUT",
            {
                "spreadsheet_id": "ss1",
                "range": "A1:B2",
                "values": [["a", 1]],
                "value_input_option": "RAW",
            },
        )
        assert url.startswith("https://sheets.googleapis.com/"), f"Got: {url}"
        assert "/v4/spreadsheets/ss1/values/A1:B2" in url
        # value_inputOption must be in the query string, not the body
        assert json_body is None or "valueInputOption" not in json_body

    @pytest.mark.asyncio
    async def test_sheets_batch_get_passes_ranges_as_query(self, db_session):
        url, params, _ = await _run_proxy(
            db_session,
            "drive",
            "drive.sheets.values.batch_get",
            "GET",
            {"spreadsheet_id": "ss1", "ranges": ["A1:B2", "C3:D4"]},
        )
        assert url.startswith("https://sheets.googleapis.com/")
        assert "ranges=" in url or "ranges" in params


# --------------------------------------------------------------------------- #
# Docs hostname tests
# --------------------------------------------------------------------------- #


class TestDocsHostname:
    @pytest.mark.asyncio
    async def test_docs_documents_get_hits_docs_host(self, db_session):
        url, _, _ = await _run_proxy(
            db_session,
            "drive",
            "drive.docs.documents.get",
            "GET",
            {"document_id": "doc123"},
        )
        assert url.startswith("https://docs.googleapis.com/"), f"Got: {url}"
        assert "/v1/documents/doc123" in url
        assert "www.googleapis.com" not in url

    @pytest.mark.asyncio
    async def test_docs_documents_batch_update_hits_docs_host(self, db_session):
        url, _, json_body = await _run_proxy(
            db_session,
            "drive",
            "drive.docs.documents.batch_update",
            "POST",
            {"document_id": "doc1", "requests": [{"insertText": {"text": "hi"}}]},
        )
        assert url.startswith("https://docs.googleapis.com/")
        assert "/v1/documents/doc1:batchUpdate" in url
        assert json_body and "requests" in json_body


# --------------------------------------------------------------------------- #
# Slides hostname tests
# --------------------------------------------------------------------------- #


class TestSlidesHostname:
    @pytest.mark.asyncio
    async def test_slides_presentations_get_hits_slides_host(self, db_session):
        url, _, _ = await _run_proxy(
            db_session,
            "drive",
            "drive.slides.presentations.get",
            "GET",
            {"presentation_id": "pres123"},
        )
        assert url.startswith("https://slides.googleapis.com/"), f"Got: {url}"
        assert "/v1/presentations/pres123" in url
        assert "www.googleapis.com" not in url

    @pytest.mark.asyncio
    async def test_slides_pages_get_substitutes_both_params(self, db_session):
        url, _, _ = await _run_proxy(
            db_session,
            "drive",
            "drive.slides.presentations.pages.get",
            "GET",
            {"presentation_id": "pres1", "page_object_id": "slide_42"},
        )
        assert url.startswith("https://slides.googleapis.com/")
        assert "/v1/presentations/pres1/pages/slide_42" in url
        assert "www.googleapis.com" not in url


# --------------------------------------------------------------------------- #
# Regression: existing routes still hit www.googleapis.com
# --------------------------------------------------------------------------- #


class TestExistingRoutesUnchanged:
    """Pre-existing Drive/Gmail/Calendar routes must still hit www.googleapis.com."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "module_name,route_id,params",
        [
            ("drive", "drive.files.list", {}),
            ("drive", "drive.files.get", {"file_id": "f1"}),
            ("drive", "drive.permissions.list", {"file_id": "f1"}),
            ("gmail", "gmail.messages.list", {}),
            ("gmail", "gmail.messages.get", {"message_id": "m1"}),
            ("calendar", "calendar.events.list", {}),
            ("calendar", "calendar.events.get", {"event_id": "e1"}),
        ],
    )
    async def test_legacy_routes_use_www_googleapis_com(
        self, db_session, module_name, route_id, params
    ):
        url, _, _ = await _run_proxy(
            db_session,
            module_name,
            route_id,
            "GET",
            params,
        )
        assert url.startswith("https://www.googleapis.com/"), (
            f"{route_id} should still hit www.googleapis.com, got: {url}"
        )
        # No new route's hostname should leak into a legacy route
        for host in (
            "sheets.googleapis.com",
            "docs.googleapis.com",
            "slides.googleapis.com",
            "forms.googleapis.com",
            "script.googleapis.com",
        ):
            assert host not in url, f"{route_id} leaked host {host} (got: {url})"


# --------------------------------------------------------------------------- #
# Forms hostname tests
# --------------------------------------------------------------------------- #


class TestFormsHostname:
    @pytest.mark.asyncio
    async def test_forms_create_hits_forms_host(self, db_session):
        url, params, _ = await _run_proxy(
            db_session,
            "forms",
            "forms.forms.create",
            "POST",
            {"title": "My Form"},
        )
        assert url.startswith("https://forms.googleapis.com/"), f"Got: {url}"
        assert url.endswith("/v1/forms"), f"Got: {url}"
        assert "www.googleapis.com" not in url
        # `unpublished` is optional, so it should NOT appear unless explicitly set
        params = params or {}
        assert "unpublished" not in params and "unpublished" not in url

    @pytest.mark.asyncio
    async def test_forms_get_hits_forms_host(self, db_session):
        url, _, _ = await _run_proxy(
            db_session,
            "forms",
            "forms.forms.get",
            "GET",
            {"form_id": "form123"},
        )
        assert url.startswith("https://forms.googleapis.com/")
        assert "/v1/forms/form123" in url
        assert "www.googleapis.com" not in url

    @pytest.mark.asyncio
    async def test_forms_responses_list_passes_pagination_as_query(self, db_session):
        url, params, _ = await _run_proxy(
            db_session,
            "forms",
            "forms.forms.responses.list",
            "GET",
            {"form_id": "f1", "page_size": 10, "page_token": "abc"},
        )
        assert url.startswith("https://forms.googleapis.com/")
        assert "/v1/forms/f1/responses" in url
        # page_size / page_token MUST be in the query string (proxy converts to camelCase)
        assert params.get("pageSize") == 10
        assert params.get("pageToken") == "abc"

    @pytest.mark.asyncio
    async def test_forms_create_unpublished_query_param(self, db_session):
        # When the caller sets unpublished=True, it must reach the URL as
        # ?unpublished=true
        url, params, _ = await _run_proxy(
            db_session,
            "forms",
            "forms.forms.create",
            "POST",
            {"title": "X", "unpublished": True},
        )
        assert url.startswith("https://forms.googleapis.com/")
        # The proxy puts it into query_params (not body) because we listed it in
        # the route's query_params list
        assert params.get("unpublished") is True


# --------------------------------------------------------------------------- #
# Apps Script hostname tests
# --------------------------------------------------------------------------- #


class TestAppsScriptHostname:
    @pytest.mark.asyncio
    async def test_projects_get_hits_script_host(self, db_session):
        url, _, _ = await _run_proxy(
            db_session,
            "appsscript",
            "appsscript.projects.get",
            "GET",
            {"script_id": "proj123"},
        )
        assert url.startswith("https://script.googleapis.com/"), f"Got: {url}"
        assert "/v1/projects/proj123" in url
        assert "www.googleapis.com" not in url

    @pytest.mark.asyncio
    async def test_projects_get_metrics_requires_metrics_granularity(self, db_session):
        # Sanity: passing metrics_granularity=DAILY works; without it the proxy
        # forwards the request as-is (the API will return 400 if missing).
        # We verify the query param is properly converted to camelCase.
        url, params, _ = await _run_proxy(
            db_session,
            "appsscript",
            "appsscript.projects.get_metrics",
            "GET",
            {"script_id": "p1", "metrics_granularity": "DAILY"},
        )
        assert url.startswith("https://script.googleapis.com/")
        assert "/v1/projects/p1/metrics" in url
        # The proxy's snake→camelCase transform turns metrics_granularity into
        # metricsGranularity — which is what the Google API expects
        assert params.get("metricsGranularity") == "DAILY"

    @pytest.mark.asyncio
    async def test_processes_list_uses_flattened_filter_query_params(self, db_session):
        # Verify the FLATTENED userProcessFilterScriptId (not userProcessFilter.scriptId)
        # reaches the query string. Google accepts this flat form even though the
        # canonical form is dotted. See research Observation #2.
        url, params, _ = await _run_proxy(
            db_session,
            "appsscript",
            "appsscript.processes.list",
            "GET",
            {"page_size": 10, "user_process_filter_script_id": "abc123"},
        )
        assert url.startswith("https://script.googleapis.com/")
        assert "/v1/processes" in url
        # The snake→camelCase transform produces userProcessFilterScriptId
        assert params.get("userProcessFilterScriptId") == "abc123"
        assert params.get("pageSize") == 10

    @pytest.mark.asyncio
    async def test_processes_list_script_processes_uses_colon_notation(self, db_session):
        # The path is /v1/processes:listScriptProcesses (colon-notation custom method)
        url, _, _ = await _run_proxy(
            db_session,
            "appsscript",
            "appsscript.processes.list_script_processes",
            "GET",
            {},
        )
        assert url.startswith("https://script.googleapis.com/")
        assert url.endswith("/v1/processes:listScriptProcesses"), f"Got: {url}"
        assert "/v1/processes/listScriptProcesses" not in url  # NOT a sub-resource

    @pytest.mark.asyncio
    async def test_scripts_run_hits_script_host(self, db_session):
        url, _, _ = await _run_proxy(
            db_session,
            "appsscript",
            "appsscript.scripts.run",
            "POST",
            {"script_id": "s1", "function": "myFunc"},
        )
        assert url.startswith("https://script.googleapis.com/")
        assert "/v1/scripts/s1:run" in url
