"""Structural tests for the Sheets, Docs, and Slides routes added to the Drive module."""

from gatekeeper.modules.drive import DriveModule

# ── Sheets ──


def test_sheets_routes_present():
    ids = {r.route_id for r in DriveModule().get_routes()}
    expected = [
        "drive.sheets.spreadsheets.get",
        "drive.sheets.values.get",
        "drive.sheets.values.batch_get",
        "drive.sheets.values.update",
        "drive.sheets.values.append",
        "drive.sheets.values.clear",
        "drive.sheets.values.batch_update",
        "drive.sheets.spreadsheets.create",
        "drive.sheets.spreadsheets.batch_update",
    ]
    for rid in expected:
        assert rid in ids, f"Missing Sheets route: {rid}"


def test_sheets_routes_have_correct_base_url():
    """Every Sheets route must target sheets.googleapis.com."""
    routes = [r for r in DriveModule().get_routes() if r.route_id.startswith("drive.sheets.")]
    assert len(routes) == 9, f"Expected 9 sheets routes, found {len(routes)}"
    for r in routes:
        assert r.base_url == "https://sheets.googleapis.com", (
            f"{r.route_id} has base_url={r.base_url!r}"
        )


def test_sheets_mcp_tool_names():
    tools = {t["name"] for t in DriveModule().get_mcp_tools()}
    for name in (
        "drive__sheets_spreadsheets_get",
        "drive__sheets_values_get",
        "drive__sheets_values_update",
        "drive__sheets_values_append",
        "drive__sheets_values_clear",
        "drive__sheets_values_batch_get",
        "drive__sheets_values_batch_update",
        "drive__sheets_spreadsheets_create",
        "drive__sheets_spreadsheets_batch_update",
    ):
        assert name in tools, f"Missing MCP tool: {name}"


def test_sheets_read_enabled_by_default():
    routes = {r.route_id: r for r in DriveModule().get_routes()}
    for rid in (
        "drive.sheets.spreadsheets.get",
        "drive.sheets.values.get",
        "drive.sheets.values.batch_get",
    ):
        assert routes[rid].enabled_by_default is True, f"{rid} should be on by default"


def test_sheets_write_disabled_by_default():
    routes = {r.route_id: r for r in DriveModule().get_routes()}
    for rid in (
        "drive.sheets.values.update",
        "drive.sheets.values.append",
        "drive.sheets.values.clear",
        "drive.sheets.spreadsheets.create",
        "drive.sheets.spreadsheets.batch_update",
    ):
        assert routes[rid].enabled_by_default is False, f"{rid} should be off by default"


# ── Docs ──


def test_docs_routes_present():
    ids = {r.route_id for r in DriveModule().get_routes()}
    for rid in (
        "drive.docs.documents.get",
        "drive.docs.documents.create",
        "drive.docs.documents.batch_update",
    ):
        assert rid in ids, f"Missing Docs route: {rid}"


def test_docs_routes_have_correct_base_url():
    routes = [r for r in DriveModule().get_routes() if r.route_id.startswith("drive.docs.")]
    assert len(routes) == 3
    for r in routes:
        assert r.base_url == "https://docs.googleapis.com", (
            f"{r.route_id} has base_url={r.base_url!r}"
        )


def test_docs_read_enabled_docs_write_disabled():
    routes = {r.route_id: r for r in DriveModule().get_routes()}
    assert routes["drive.docs.documents.get"].enabled_by_default is True
    assert routes["drive.docs.documents.create"].enabled_by_default is False
    assert routes["drive.docs.documents.batch_update"].enabled_by_default is False


# ── Slides ──


def test_slides_routes_present():
    ids = {r.route_id for r in DriveModule().get_routes()}
    for rid in (
        "drive.slides.presentations.get",
        "drive.slides.presentations.pages.get",
        "drive.slides.presentations.create",
        "drive.slides.presentations.batch_update",
    ):
        assert rid in ids, f"Missing Slides route: {rid}"


def test_slides_routes_have_correct_base_url():
    routes = [r for r in DriveModule().get_routes() if r.route_id.startswith("drive.slides.")]
    assert len(routes) == 4
    for r in routes:
        assert r.base_url == "https://slides.googleapis.com", (
            f"{r.route_id} has base_url={r.base_url!r}"
        )


def test_slides_read_enabled_slides_write_disabled():
    routes = {r.route_id: r for r in DriveModule().get_routes()}
    assert routes["drive.slides.presentations.get"].enabled_by_default is True
    assert routes["drive.slides.presentations.pages.get"].enabled_by_default is True
    assert routes["drive.slides.presentations.create"].enabled_by_default is False
    assert routes["drive.slides.presentations.batch_update"].enabled_by_default is False


# ── Scopes ──


def test_drive_module_has_all_four_scopes():
    scopes = DriveModule().required_scopes
    for required in (
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/presentations",
    ):
        assert required in scopes, f"Missing scope: {required}"


# ── Cross-cutting ──


def test_no_route_uses_global_base_for_new_routes():
    """Defensive: confirm the new routes do NOT inherit GOOGLE_API_BASE via accident."""
    bad = [
        r
        for r in DriveModule().get_routes()
        if r.route_id.startswith(("drive.sheets.", "drive.docs.", "drive.slides."))
        and r.base_url is None
    ]
    assert bad == [], f"New routes missing base_url: {[r.route_id for r in bad]}"


def test_existing_drive_routes_have_no_base_url():
    """Pre-existing Drive routes should NOT have base_url set (they use the default)."""
    for r in DriveModule().get_routes():
        if r.route_id.startswith("drive.files.") or r.route_id.startswith("drive.permissions."):
            assert r.base_url is None, (
                f"Existing route {r.route_id} unexpectedly has base_url={r.base_url!r}"
            )
