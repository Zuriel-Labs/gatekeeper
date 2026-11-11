"""Tests for module route definitions — structural checks, not exact counts.

Routes may be added or removed over time, so tests verify properties
that must always hold rather than asserting exact route IDs or counts.
"""

from gatekeeper.modules import load_module


class TestDriveModule:
    """Tests for the Drive module route definitions."""

    def setup_method(self):
        self.mod = load_module("drive")

    def test_has_routes(self):
        assert len(self.mod.get_routes()) > 0

    def test_route_ids_start_with_drive(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("drive."), (
                f"Route {route.route_id} doesn't start with 'drive.'"
            )

    def test_core_read_routes_exist(self):
        """Essential read routes must always be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in ["drive.files.list", "drive.files.get", "drive.files.export"]:
            assert required in ids, f"Missing core route: {required}"

    def test_core_write_routes_exist(self):
        """Essential write routes must be present (even if disabled)."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in ["drive.files.create", "drive.files.delete"]:
            assert required in ids, f"Missing write route: {required}"

    def test_write_routes_disabled_by_default(self):
        write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        # drive.files.update is intentionally enabled by default (basic CRUD)
        allowed_by_default = {"drive.files.update"}
        for route in self.mod.get_routes():
            if route.method in write_methods and route.route_id not in allowed_by_default:
                assert route.enabled_by_default is False, (
                    f"{route.route_id} ({route.method}) should be disabled by default"
                )

    def test_core_read_routes_enabled_by_default(self):
        core_read_routes = {
            "drive.files.list",
            "drive.files.get",
            "drive.files.export",
            "drive.about.get",
            "drive.permissions.list",
            "drive.permissions.get",
        }
        for route in self.mod.get_routes():
            if route.route_id in core_read_routes:
                assert route.enabled_by_default is True, (
                    f"{route.route_id} should be enabled by default"
                )

    def test_each_route_has_input_schema(self):
        for route in self.mod.get_routes():
            assert "type" in route.input_schema, f"{route.route_id} missing input schema type"
            assert route.input_schema["type"] == "object"

    def test_each_route_has_description(self):
        for route in self.mod.get_routes():
            assert len(route.description) > 0, f"{route.route_id} missing description"

    def test_required_scopes(self):
        assert "https://www.googleapis.com/auth/drive" in self.mod.required_scopes

    def test_default_policies_structure(self):
        policies = self.mod.get_default_policies()
        for route_id, policy in policies.items():
            assert isinstance(policy, dict), f"Policy for {route_id} is not a dict"


class TestGmailModule:
    """Tests for the Gmail module route definitions."""

    def setup_method(self):
        self.mod = load_module("gmail")

    def test_has_routes(self):
        assert len(self.mod.get_routes()) > 0

    def test_route_ids_start_with_gmail(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("gmail."), (
                f"Route {route.route_id} doesn't start with 'gmail.'"
            )

    def test_core_read_routes_exist(self):
        """Essential read routes must always be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in ["gmail.messages.list", "gmail.messages.get", "gmail.labels.list"]:
            assert required in ids, f"Missing core route: {required}"

    def test_label_routes_exist(self):
        """Label management routes must be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in [
            "gmail.labels.list",
            "gmail.labels.get",
            "gmail.labels.create",
            "gmail.labels.update",
            "gmail.labels.delete",
        ]:
            assert required in ids, f"Missing label route: {required}"

    def test_filter_routes_exist(self):
        """Filter management routes must be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in [
            "gmail.filters.list",
            "gmail.filters.get",
            "gmail.filters.create",
            "gmail.filters.update",
            "gmail.filters.delete",
        ]:
            assert required in ids, f"Missing filter route: {required}"

    def test_write_routes_disabled_by_default(self):
        write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        # drive.files.update is intentionally enabled by default (basic CRUD)
        allowed_by_default = {"drive.files.update"}
        for route in self.mod.get_routes():
            if route.method in write_methods and route.route_id not in allowed_by_default:
                assert route.enabled_by_default is False, (
                    f"{route.route_id} ({route.method}) should be disabled by default"
                )

    def test_core_read_routes_enabled_by_default(self):
        core_read_routes = {
            "gmail.messages.list",
            "gmail.messages.get",
            "gmail.drafts.list",
            "gmail.drafts.get",
            "gmail.labels.list",
            "gmail.labels.get",
            "gmail.threads.list",
            "gmail.threads.get",
            "gmail.messages.attachments.get",
            "gmail.history.list",
        }
        for route in self.mod.get_routes():
            if route.route_id in core_read_routes:
                assert route.enabled_by_default is True, (
                    f"{route.route_id} should be enabled by default"
                )

    def test_messages_list_has_label_policy(self):
        list_route = next(r for r in self.mod.get_routes() if r.route_id == "gmail.messages.list")
        assert "allowed_labels" in list_route.default_policy
        assert "exclude_labels" in list_route.default_policy
        assert "SPAM" in list_route.default_policy["exclude_labels"]
        assert "TRASH" in list_route.default_policy["exclude_labels"]

    def test_messages_send_has_recipient_limit(self):
        send_route = next(r for r in self.mod.get_routes() if r.route_id == "gmail.messages.send")
        assert "max_recipients" in send_route.default_policy

    def test_required_scopes(self):
        assert "https://www.googleapis.com/auth/gmail.modify" in self.mod.required_scopes
        assert "https://www.googleapis.com/auth/gmail.send" in self.mod.required_scopes

    def test_mcp_tools_naming(self):
        tools = self.mod.get_mcp_tools()
        assert len(tools) > 0
        for tool in tools:
            assert tool["name"].startswith("gmail__")
            assert "description" in tool
            assert "inputSchema" in tool


class TestCalendarModule:
    """Tests for the Calendar module route definitions."""

    def setup_method(self):
        self.mod = load_module("calendar")

    def test_has_routes(self):
        assert len(self.mod.get_routes()) > 0

    def test_route_ids_start_with_calendar(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("calendar."), (
                f"Route {route.route_id} doesn't start with 'calendar.'"
            )

    def test_core_read_routes_exist(self):
        """Essential read routes must always be present."""
        ids = {r.route_id for r in self.mod.get_routes()}
        for required in [
            "calendar.events.list",
            "calendar.events.get",
            "calendar.calendars.list",
            "calendar.freebusy.query",
        ]:
            assert required in ids, f"Missing core route: {required}"

    def test_write_routes_disabled_by_default(self):
        # POST/PUT/PATCH/DELETE routes are disabled by default,
        # except for read-oriented POST routes (freebusy.query, quickAdd)
        read_posts = {"calendar.freebusy.query", "calendar.events.quick_add"}
        for route in self.mod.get_routes():
            if route.method in {"POST", "PUT", "PATCH", "DELETE"}:
                if route.route_id not in read_posts:
                    assert route.enabled_by_default is False, (
                        f"{route.route_id} ({route.method}) should be disabled by default"
                    )

    def test_core_read_routes_enabled_by_default(self):
        core_read_routes = {
            "calendar.events.list",
            "calendar.events.get",
            "calendar.calendars.list",
            "calendar.calendarlist.list",
            "calendar.calendars.get",
            "calendar.freebusy.query",
            "calendar.acl.list",
            "calendar.acl.get",
            "calendar.calendarlist.get",
            "calendar.colors.get",
            "calendar.settings.list",
            "calendar.settings.get",
        }
        for route in self.mod.get_routes():
            if route.route_id in core_read_routes:
                assert route.enabled_by_default is True, (
                    f"{route.route_id} should be enabled by default"
                )

    def test_events_list_has_max_results_policy(self):
        list_route = next(r for r in self.mod.get_routes() if r.route_id == "calendar.events.list")
        assert "max_results" in list_route.default_policy

    def test_required_scopes(self):
        assert "https://www.googleapis.com/auth/calendar" in self.mod.required_scopes
        assert "https://www.googleapis.com/auth/calendar.events" in self.mod.required_scopes

    def test_mcp_tools_naming(self):
        tools = self.mod.get_mcp_tools()
        assert len(tools) > 0
        for tool in tools:
            assert tool["name"].startswith("calendar__")
            assert "description" in tool
            assert "inputSchema" in tool


class TestFormsModule:
    """Tests for the Forms module route definitions."""

    def setup_method(self):
        self.mod = load_module("forms")

    def test_has_routes(self):
        # 10 Forms routes (forms.forms.* + forms.forms.responses.* + forms.forms.watches.*)
        routes = self.mod.get_routes()
        assert len(routes) == 10, f"Expected 10 Forms routes, got {len(routes)}"

    def test_route_ids_start_with_forms(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("forms."), (
                f"Route {route.route_id} doesn't start with 'forms.'"
            )

    def test_all_routes_disabled_by_default(self):
        # Spec: every Forms route is enabled_by_default=False
        for route in self.mod.get_routes():
            assert route.enabled_by_default is False, (
                f"{route.route_id} should be disabled by default (spec requires it)"
            )

    def test_every_route_has_forms_base_url(self):
        # Spec: every Forms route must specify base_url="https://forms.googleapis.com"
        for route in self.mod.get_routes():
            assert route.base_url == "https://forms.googleapis.com", (
                f"{route.route_id} has base_url={route.base_url!r}, "
                f"expected 'https://forms.googleapis.com'"
            )

    def test_every_route_has_input_schema(self):
        for route in self.mod.get_routes():
            assert route.input_schema.get("type") == "object", (
                f"{route.route_id} missing input schema type 'object'"
            )

    def test_required_scopes(self):
        assert "https://www.googleapis.com/auth/forms.body" in self.mod.required_scopes
        assert "https://www.googleapis.com/auth/forms.body.readonly" in self.mod.required_scopes
        assert (
            "https://www.googleapis.com/auth/forms.responses.readonly" in self.mod.required_scopes
        )

    def test_google_path_prefix(self):
        # Every google_path must start with /v1 (per discovery doc)
        for route in self.mod.get_routes():
            assert route.google_path.startswith("/v1"), (
                f"{route.route_id} google_path={route.google_path!r} should start with /v1"
            )

    def test_specific_routes_exist(self):
        ids = {r.route_id for r in self.mod.get_routes()}
        required = {
            "forms.forms.create",
            "forms.forms.get",
            "forms.forms.batch_update",
            "forms.forms.set_publish_settings",
            "forms.forms.responses.get",
            "forms.forms.responses.list",
            "forms.forms.watches.create",
            "forms.forms.watches.delete",
            "forms.forms.watches.list",
            "forms.forms.watches.renew",
        }
        missing = required - ids
        assert not missing, f"Missing Forms routes: {missing}"


class TestAppsScriptModule:
    """Tests for the Apps Script module route definitions."""

    def setup_method(self):
        self.mod = load_module("appsscript")

    def test_has_16_routes(self):
        routes = self.mod.get_routes()
        assert len(routes) == 16, f"Expected 16 Apps Script routes, got {len(routes)}"

    def test_route_ids_start_with_appsscript(self):
        for route in self.mod.get_routes():
            assert route.route_id.startswith("appsscript."), (
                f"Route {route.route_id} doesn't start with 'appsscript.'"
            )

    def test_all_routes_disabled_by_default(self):
        for route in self.mod.get_routes():
            assert route.enabled_by_default is False, (
                f"{route.route_id} should be disabled by default (spec requires it)"
            )

    def test_every_route_has_script_base_url(self):
        for route in self.mod.get_routes():
            assert route.base_url == "https://script.googleapis.com", (
                f"{route.route_id} has base_url={route.base_url!r}, "
                f"expected 'https://script.googleapis.com'"
            )

    def test_every_route_has_input_schema(self):
        for route in self.mod.get_routes():
            assert route.input_schema.get("type") == "object", (
                f"{route.route_id} missing input schema type 'object'"
            )

    def test_required_scopes(self):
        expected = {
            "https://www.googleapis.com/auth/script.projects",
            "https://www.googleapis.com/auth/script.projects.readonly",
            "https://www.googleapis.com/auth/script.deployments",
            "https://www.googleapis.com/auth/script.deployments.readonly",
            "https://www.googleapis.com/auth/script.processes",
            "https://www.googleapis.com/auth/script.metrics",
        }
        missing = expected - set(self.mod.required_scopes)
        assert not missing, f"Missing required scopes: {missing}"

    def test_google_path_prefix(self):
        for route in self.mod.get_routes():
            assert route.google_path.startswith("/v1"), (
                f"{route.route_id} google_path={route.google_path!r} should start with /v1"
            )

    def test_all_specific_routes_exist(self):
        # The 5 deployment routes (research Observation #6: summary table said 4 but
        # there are actually 5). This test pins the count so future refactors notice.
        ids = {r.route_id for r in self.mod.get_routes()}
        required = {
            # Projects
            "appsscript.projects.create",
            "appsscript.projects.get",
            "appsscript.projects.get_content",
            "appsscript.projects.update_content",
            "appsscript.projects.get_metrics",
            # Deployments (5)
            "appsscript.deployments.create",
            "appsscript.deployments.get",
            "appsscript.deployments.list",
            "appsscript.deployments.update",
            "appsscript.deployments.delete",
            # Versions
            "appsscript.versions.create",
            "appsscript.versions.get",
            "appsscript.versions.list",
            # Processes
            "appsscript.processes.list",
            "appsscript.processes.list_script_processes",
            # Scripts
            "appsscript.scripts.run",
        }
        missing = required - ids
        assert not missing, f"Missing Apps Script routes: {missing}"

    def test_get_metrics_requires_metrics_granularity(self):
        # Research Observation #7: the discovery doc says metricsGranularity is
        # required, but the original task inventory listed it as optional.
        # This test pins the required-status so a future refactor notices.
        route = next(
            r for r in self.mod.get_routes() if r.route_id == "appsscript.projects.get_metrics"
        )
        assert "metrics_granularity" in route.input_schema.get("required", []), (
            "appsscript.projects.get_metrics must mark metrics_granularity as required"
        )

    def test_processes_list_has_flattened_filter_query_params(self):
        # Research Observation #2: dotted query params are flattened because the
        # proxy's snake→camelCase transform cannot reintroduce the dot.
        # This test pins the query_params list so future refactors notice.
        route = next(r for r in self.mod.get_routes() if r.route_id == "appsscript.processes.list")
        assert "user_process_filter_script_id" in route.query_params
        assert "user_process_filter_deployment_id" in route.query_params
        assert "user_process_filter_function_name" in route.query_params

    def test_list_script_processes_has_flattened_filter_query_params(self):
        route = next(
            r
            for r in self.mod.get_routes()
            if r.route_id == "appsscript.processes.list_script_processes"
        )
        assert "script_process_filter_function_name" in route.query_params
        assert "script_process_filter_deployment_id" in route.query_params
        assert "script_id" in route.query_params  # scriptId is a query param on this route

    def test_uses_colon_notation_for_list_script_processes(self):
        # Research Observation #1: the discovery path is
        # v1/processes:listScriptProcesses, NOT v1/processes/listScriptProcesses
        route = next(
            r
            for r in self.mod.get_routes()
            if r.route_id == "appsscript.processes.list_script_processes"
        )
        assert route.google_path == "/v1/processes:listScriptProcesses", (
            f"Expected colon-notation path, got: {route.google_path!r}"
        )
