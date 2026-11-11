"""Google Apps Script module — manage, deploy, and execute Apps Script projects."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class AppsScriptModule(GoogleModule):
    name = "appsscript"
    display_name = "Google Apps Script"
    description = "Manage, deploy, and execute Google Apps Script projects"
    icon = "⚙️"

    required_scopes = [
        "https://www.googleapis.com/auth/script.projects",
        "https://www.googleapis.com/auth/script.projects.readonly",
        "https://www.googleapis.com/auth/script.deployments",
        "https://www.googleapis.com/auth/script.deployments.readonly",
        "https://www.googleapis.com/auth/script.processes",
        "https://www.googleapis.com/auth/script.metrics",
    ]

    SCRIPT_BASE = "https://script.googleapis.com"

    def get_routes(self) -> list[RouteDef]:
        return [
            # ── Projects ──
            RouteDef(
                route_id="appsscript.projects.create",
                method="POST",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects",
                description="Create a new Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title for the new project"},
                        "parent_id": {
                            "type": "string",
                            "description": "Drive folder ID where the project is created",
                        },
                    },
                    "required": ["title"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.projects.get",
                method="GET",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}",
                description="Get an Apps Script project's metadata",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                    },
                    "required": ["script_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.projects.get_content",
                method="GET",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/content",
                description="Get the source code of an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "version_number": {
                            "type": "integer",
                            "description": "Version to read; defaults to HEAD",
                        },
                    },
                    "required": ["script_id"],
                },
                query_params=["version_number"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.projects.update_content",
                method="PUT",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/content",
                description="Update the source code of an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "files": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": ("Source files to write (Apps Script Content model)"),
                        },
                    },
                    "required": ["script_id", "files"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.projects.get_metrics",
                method="GET",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/metrics",
                description="Get execution metrics for an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "metrics_granularity": {
                            "type": "string",
                            "description": "Required: granularity bucket (e.g., DAILY, WEEKLY)",
                            # No default — REQUIRED by Google's API
                        },
                        "metrics_filter_deployment_id": {
                            "type": "string",
                            "description": "Optional: filter to a specific deployment ID",
                        },
                    },
                    "required": ["script_id", "metrics_granularity"],
                },
                query_params=["metrics_granularity", "metrics_filter_deployment_id"],
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Deployments ──
            RouteDef(
                route_id="appsscript.deployments.create",
                method="POST",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/deployments",
                description="Create a deployment for an Apps Script project version",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "version_number": {
                            "type": "integer",
                            "description": "The version number to deploy",
                        },
                        "description": {"type": "string", "description": "Deployment description"},
                    },
                    "required": ["script_id", "version_number"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.deployments.get",
                method="GET",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/deployments/{deploymentId}",
                description="Get a deployment of an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "deployment_id": {"type": "string", "description": "The deployment ID"},
                    },
                    "required": ["script_id", "deployment_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.deployments.list",
                method="GET",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/deployments",
                description="List deployments of an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "page_size": {"type": "integer", "description": "Page size", "default": 50},
                        "page_token": {"type": "string", "description": "Continuation token"},
                    },
                    "required": ["script_id"],
                },
                query_params=["page_size", "page_token"],
                default_policy={"max_results": 100},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.deployments.update",
                method="PUT",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/deployments/{deploymentId}",
                description="Update a deployment of an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "deployment_id": {"type": "string", "description": "The deployment ID"},
                        "deployment": {
                            "type": "object",
                            "description": "Updated deployment configuration",
                        },
                    },
                    "required": ["script_id", "deployment_id", "deployment"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.deployments.delete",
                method="DELETE",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/deployments/{deploymentId}",
                description="Delete a deployment of an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "deployment_id": {"type": "string", "description": "The deployment ID"},
                    },
                    "required": ["script_id", "deployment_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Versions ──
            RouteDef(
                route_id="appsscript.versions.create",
                method="POST",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/versions",
                description="Create a new immutable version of an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "description": {"type": "string", "description": "Version description"},
                    },
                    "required": ["script_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.versions.get",
                method="GET",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/versions/{versionNumber}",
                description="Get a specific version of an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "version_number": {
                            "type": "integer",
                            "description": "The version number to retrieve",
                        },
                    },
                    "required": ["script_id", "version_number"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.versions.list",
                method="GET",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/projects/{scriptId}/versions",
                description="List versions of an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "page_size": {"type": "integer", "description": "Page size", "default": 50},
                        "page_token": {"type": "string", "description": "Continuation token"},
                    },
                    "required": ["script_id"],
                },
                query_params=["page_size", "page_token"],
                default_policy={"max_results": 100},
                enabled_by_default=False,
            ),
            # ── Processes (FLATTENED dotted query params — see Observation #2) ──
            RouteDef(
                route_id="appsscript.processes.list",
                method="GET",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/processes",
                description="List recent process executions (user-scoped)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_size": {"type": "integer", "description": "Page size", "default": 50},
                        "page_token": {"type": "string", "description": "Continuation token"},
                        "user_process_filter_script_id": {
                            "type": "string",
                            "description": "Filter to a specific script project",
                        },
                        "user_process_filter_deployment_id": {
                            "type": "string",
                            "description": "Filter to a specific deployment",
                        },
                        "user_process_filter_function_name": {
                            "type": "string",
                            "description": "Filter to a specific function name",
                        },
                        "user_process_filter_start_time": {
                            "type": "string",
                            "description": "Filter: process start time (RFC3339)",
                        },
                        "user_process_filter_end_time": {
                            "type": "string",
                            "description": "Filter: process end time (RFC3339)",
                        },
                        "user_process_filter_statuses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by process status",
                        },
                        "user_process_filter_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by process type",
                        },
                        "user_process_filter_user_access_levels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by user access level",
                        },
                        "user_process_filter_project_name": {
                            "type": "string",
                            "description": "Filter to a project name",
                        },
                    },
                },
                # IMPORTANT: query_params use the FLATTENED form (dotted dots replaced
                # with underscores). The proxy's snake→camelCase transform produces
                # userProcessFilterScriptId, etc. — the API also accepts these in
                # flat form. The canonical dotted form (userProcessFilter.scriptId)
                # is NOT used here because the proxy cannot reintroduce the dot.
                query_params=[
                    "page_size",
                    "page_token",
                    "user_process_filter_script_id",
                    "user_process_filter_deployment_id",
                    "user_process_filter_function_name",
                    "user_process_filter_start_time",
                    "user_process_filter_end_time",
                    "user_process_filter_statuses",
                    "user_process_filter_types",
                    "user_process_filter_user_access_levels",
                    "user_process_filter_project_name",
                ],
                default_policy={"max_results": 100},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="appsscript.processes.list_script_processes",
                method="GET",
                base_url=self.SCRIPT_BASE,
                # Note: colon-notation custom method on the processes resource
                google_path="/v1/processes:listScriptProcesses",
                description="List recent process executions (script-scoped)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_size": {"type": "integer", "description": "Page size", "default": 50},
                        "page_token": {"type": "string", "description": "Continuation token"},
                        "script_id": {
                            "type": "string",
                            "description": "Filter to a specific script project (query, NOT path)",
                        },
                        "script_process_filter_function_name": {
                            "type": "string",
                            "description": "Filter to a specific function name",
                        },
                        "script_process_filter_start_time": {
                            "type": "string",
                            "description": "Filter: process start time (RFC3339)",
                        },
                        "script_process_filter_end_time": {
                            "type": "string",
                            "description": "Filter: process end time (RFC3339)",
                        },
                        "script_process_filter_statuses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by process status",
                        },
                        "script_process_filter_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by process type",
                        },
                        "script_process_filter_deployment_id": {
                            "type": "string",
                            "description": "Filter to a specific deployment",
                        },
                        "script_process_filter_user_access_levels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by user access level",
                        },
                    },
                },
                # Same FLATTENED convention as processes.list — see comment above.
                query_params=[
                    "page_size",
                    "page_token",
                    "script_id",
                    "script_process_filter_function_name",
                    "script_process_filter_start_time",
                    "script_process_filter_end_time",
                    "script_process_filter_statuses",
                    "script_process_filter_types",
                    "script_process_filter_deployment_id",
                    "script_process_filter_user_access_levels",
                ],
                default_policy={"max_results": 100},
                enabled_by_default=False,
            ),
            # ── Scripts run ──
            RouteDef(
                route_id="appsscript.scripts.run",
                method="POST",
                base_url=self.SCRIPT_BASE,
                google_path="/v1/scripts/{scriptId}:run",
                description="Run a function in an Apps Script project",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script_id": {"type": "string", "description": "The script project ID"},
                        "function": {
                            "type": "string",
                            "description": "Name of the function to execute",
                        },
                        "parameters": {
                            "type": "array",
                            "items": {},
                            "description": "Array of parameters to pass to the function",
                        },
                        "dev_mode": {
                            "type": "boolean",
                            "description": (
                                "Run against the saved HEAD version instead of the deployed version"
                            ),
                            "default": False,
                        },
                    },
                    "required": ["script_id", "function"],
                },
                # WARNING: scripts.run executes arbitrary user-defined code with the
                # OAuth credentials of the authenticated user. Default policy is empty
                # — admins who enable this route MUST also configure a restrictive
                # policy (e.g., max_recipients-equivalent, allowlist of script_id).
                default_policy={},
                enabled_by_default=False,
            ),
        ]


Module = AppsScriptModule
