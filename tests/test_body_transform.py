"""Tests for per-route body_transform feature.

Verifies:
1. The sheet_create helper produces correct Google Spreadsheet
   resource shapes from caller-friendly flat inputs.
2. The body_transform field on RouteDef is wired through the proxy.
3. Existing routes without body_transform still forward params verbatim.
"""

import pytest

from gatekeeper.api.proxy import GoogleProxy
from gatekeeper.modules.route import RouteDef

# ─── Helper unit tests (no DB / proxy init required) ───────────────────────


class TestRestructureSheetCreateBody:
    """Unit tests for the sheet_create helper."""

    def test_flat_title_only(self):
        result = GoogleProxy.sheet_create({"title": "My Sheet"})
        assert result == {"properties": {"title": "My Sheet"}}

    def test_flat_title_with_sheet_titles(self):
        result = GoogleProxy.sheet_create(
            {
                "title": "My Sheet",
                "sheet_titles": ["Sheet1", "Sheet2"],
            }
        )
        assert result == {
            "properties": {"title": "My Sheet"},
            "sheets": [
                {"properties": {"title": "Sheet1", "index": 0}},
                {"properties": {"title": "Sheet2", "index": 1}},
            ],
        }

    def test_flat_title_with_locale_and_timezone(self):
        result = GoogleProxy.sheet_create(
            {
                "title": "My Sheet",
                "locale": "en_US",
                "timeZone": "America/Chicago",
            }
        )
        assert result == {
            "properties": {
                "title": "My Sheet",
                "locale": "en_US",
                "timeZone": "America/Chicago",
            },
        }

    def test_passthrough_already_nested(self):
        """If caller already passed a proper Spreadsheet resource, don't reshape."""
        already_nested = {"properties": {"title": "Power User"}, "sheets": []}
        result = GoogleProxy.sheet_create(already_nested)
        assert result is already_nested

    def test_passthrough_with_sheets_key(self):
        """If caller already provided 'sheets' (even empty), don't reshape."""
        already_nested = {"title": "x", "sheets": [{"properties": {"title": "S1"}}]}
        result = GoogleProxy.sheet_create(already_nested)
        assert result is already_nested

    def test_extra_fields_passthrough(self):
        """Unknown fields are preserved on the Spreadsheet resource."""
        result = GoogleProxy.sheet_create(
            {
                "title": "My Sheet",
                "namedRanges": [{"namedRangeId": "foo"}],
            }
        )
        assert result["namedRanges"] == [{"namedRangeId": "foo"}]
        assert result["properties"]["title"] == "My Sheet"

    def test_empty_sheet_titles_produces_empty_sheets_array(self):
        """Empty list produces an empty 'sheets' array (Google accepts this)."""
        result = GoogleProxy.sheet_create(
            {
                "title": "My Sheet",
                "sheet_titles": [],
            }
        )
        assert result == {"properties": {"title": "My Sheet"}, "sheets": []}

    def test_sheet_titles_only_no_top_level_title(self):
        result = GoogleProxy.sheet_create(
            {
                "sheet_titles": ["Only"],
            }
        )
        assert result == {
            "sheets": [{"properties": {"title": "Only", "index": 0}}],
        }

    def test_handles_camelcase_sheet_titles(self):
        """After snake→camel normalization, sheet_titles becomes sheetTitles.
        The transform must still recognize and convert it correctly.
        """
        result = GoogleProxy.sheet_create(
            {
                "title": "My Sheet",
                "sheetTitles": ["Sheet1", "Sheet2"],
            }
        )
        assert result == {
            "properties": {"title": "My Sheet"},
            "sheets": [
                {"properties": {"title": "Sheet1", "index": 0}},
                {"properties": {"title": "Sheet2", "index": 1}},
            ],
        }

    def test_handles_snake_case_sheet_titles(self):
        """For backwards compat: snake_case key still works."""
        result = GoogleProxy.sheet_create(
            {
                "title": "My Sheet",
                "sheet_titles": ["Only"],
            }
        )
        assert result == {
            "properties": {"title": "My Sheet"},
            "sheets": [{"properties": {"title": "Only", "index": 0}}],
        }

    def test_camelcase_preferred_over_snake_case(self):
        """When both are present, use camelCase (post-normalization form)."""
        result = GoogleProxy.sheet_create(
            {
                "title": "X",
                "sheetTitles": ["FromCamel"],
                "sheet_titles": ["FromSnake"],
            }
        )
        # sheetTitles wins; sheet_titles never gets seen
        sheet_titles_field = result["sheets"][0]["properties"]["title"]
        assert sheet_titles_field == "FromCamel"


# ─── RouteDef + integration tests ───────────────────────────────────────────


def test_route_def_accepts_body_transform_field():
    """RouteDef should accept body_transform without breaking construction."""
    route = RouteDef(
        route_id="test.route",
        method="POST",
        google_path="/v1/test",
        body_transform="my_transform",
    )
    assert route.body_transform == "my_transform"


def test_route_def_body_transform_defaults_to_none():
    """Existing routes (no body_transform) should default to None."""
    route = RouteDef(
        route_id="test.route",
        method="GET",
        google_path="/v1/test",
    )
    assert route.body_transform is None


def test_sheets_create_route_has_body_transform_wired(db_session):
    """The drive.sheets.spreadsheets.create route must declare body_transform."""
    from gatekeeper.modules.drive import DriveModule

    drive = DriveModule()
    sheets_create = None
    for route in drive.get_routes():
        if route.route_id == "drive.sheets.spreadsheets.create":
            sheets_create = route
            break
    assert sheets_create is not None, "Route drive.sheets.spreadsheets.create not found"
    assert sheets_create.body_transform == "sheet_create"


@pytest.mark.asyncio
async def test_proxy_dispatches_body_transform(db_session, monkeypatch):
    """End-to-end: when route declares body_transform, proxy calls the helper.

    Uses MockTransport-style pattern via monkeypatched httpx to capture
    the body that would be sent to Google.
    """
    import httpx

    from gatekeeper.api.proxy import GoogleProxy

    # Capture what httpx posts
    captured = {}

    async def fake_post(self, url, **kwargs):
        captured["url"] = str(url)
        captured["json"] = kwargs.get("json")
        # Return a minimal valid Spreadsheet response
        return httpx.Response(
            200,
            json={
                "spreadsheetId": "fake_id",
                "properties": {"title": "fake"},
                "sheets": [],
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    # Build the proxy and call the route
    proxy = GoogleProxy(db_session)
    # Find the sheets create route
    from gatekeeper.modules.drive import DriveModule

    drive = DriveModule()
    next(r for r in drive.get_routes() if r.route_id == "drive.sheets.spreadsheets.create")

    # We need an enabled route policy for the proxy to proceed. The fixture
    # `db_session` should have already seeded routes for the drive module —
    # if not, this test will be skipped via the assert below.
    from gatekeeper.models import ApiKey

    # Create a minimal ApiKey record for the proxy
    key = ApiKey(
        name="test-body-transform",
        key_hash=b"x" * 32,
        key_prefix="gkp_test",
        permissions="*",
        is_active=True,
    )
    db_session.add(key)
    await db_session.commit()
    await db_session.refresh(key)

    # If the route policy isn't enabled in the seeded DB, skip.
    from sqlalchemy import select

    from gatekeeper.models import RoutePolicy

    policy_result = await db_session.execute(
        select(RoutePolicy).where(
            RoutePolicy.module == "drive",
            RoutePolicy.route == "drive.sheets.spreadsheets.create",
        )
    )
    policy = policy_result.scalar_one_or_none()
    if policy is None or not policy.enabled:
        pytest.skip("Route drive.sheets.spreadsheets.create not enabled in test DB")

    # Make the call
    await proxy.call_google(
        module_name="drive",
        route_id="drive.sheets.spreadsheets.create",
        params={"title": "My Sheet", "sheet_titles": ["Sheet1"]},
        api_key_record=key,
        request_method="POST",
        request_path="/api/v1/drive/sheets/spreadsheets/create",
    )

    # Verify the helper was applied — Google received the proper Spreadsheet shape
    assert captured["json"] == {
        "properties": {"title": "My Sheet"},
        "sheets": [{"properties": {"title": "Sheet1", "index": 0}}],
    }
