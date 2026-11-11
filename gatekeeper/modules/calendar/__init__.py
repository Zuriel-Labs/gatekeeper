"""Google Calendar module — events and calendar management with policy controls."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class CalendarModule(GoogleModule):
    name = "calendar"
    display_name = "Google Calendar"
    description = "View, create, and manage calendar events"
    icon = "📅"

    required_scopes = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    def get_routes(self) -> list[RouteDef]:
        return [
            # ── Events: read (on by default) ──
            RouteDef(
                route_id="calendar.events.list",
                method="GET",
                google_path="/calendar/v3/calendars/{calendarId}/events",
                description="List events in a calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier (use 'primary' for default)",
                            "default": "primary",
                        },
                        "time_min": {
                            "type": "string",
                            "description": "Lower bound for event start time (RFC3339)",
                        },
                        "time_max": {
                            "type": "string",
                            "description": "Upper bound for event end time (RFC3339)",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of events to return",
                            "default": 20,
                        },
                        "q": {
                            "type": "string",
                            "description": "Free text search terms to find events",
                        },
                    },
                },
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="calendar.events.get",
                method="GET",
                google_path="/calendar/v3/calendars/{calendarId}/events/{eventId}",
                description="Get a specific event by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "event_id": {
                            "type": "string",
                            "description": "Event identifier",
                        },
                    },
                    "required": ["event_id"],
                },
                default_policy={},
            ),
            # ── Events: write (off by default) ──
            RouteDef(
                route_id="calendar.events.create",
                method="POST",
                google_path="/calendar/v3/calendars/{calendarId}/events",
                description="Create a new calendar event",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Event title",
                        },
                        "start": {
                            "type": "object",
                            "description": "Start time with 'dateTime' and 'timeZone'",
                        },
                        "end": {
                            "type": "object",
                            "description": "End time with 'dateTime' and 'timeZone'",
                        },
                        "description": {
                            "type": "string",
                            "description": "Event description",
                        },
                    },
                    "required": ["summary", "start", "end"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.events.update",
                method="PATCH",
                google_path="/calendar/v3/calendars/{calendarId}/events/{eventId}",
                description="Update an existing calendar event",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "event_id": {
                            "type": "string",
                            "description": "Event identifier",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Updated event title",
                        },
                    },
                    "required": ["event_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.events.delete",
                method="DELETE",
                google_path="/calendar/v3/calendars/{calendarId}/events/{eventId}",
                description="Delete a calendar event",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "event_id": {
                            "type": "string",
                            "description": "Event identifier to delete",
                        },
                    },
                    "required": ["event_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.events.quick_add",
                method="POST",
                google_path="/calendar/v3/calendars/{calendarId}/events/quickAdd",
                description=(
                    "Create event from natural text (e.g., 'Lunch with Alex tomorrow at noon')"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "text": {
                            "type": "string",
                            "description": "Natural language event description",
                        },
                    },
                    "required": ["text"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Calendars ──
            RouteDef(
                route_id="calendar.calendars.list",
                method="GET",
                google_path="/calendar/v3/users/me/calendarList",
                description="List calendars on the user's calendar list",
                input_schema={"type": "object", "properties": {}},
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.calendarlist.list",
                method="GET",
                google_path="/calendar/v3/users/me/calendarList",
                description="List calendar entries for the user",
                input_schema={
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of calendars to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="calendar.calendars.get",
                method="GET",
                google_path="/calendar/v3/calendars/{calendarId}",
                description="Get details of a specific calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier (use 'primary' for default)",
                            "default": "primary",
                        },
                    },
                    "required": ["calendar_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.calendars.create",
                method="POST",
                google_path="/calendar/v3/calendars",
                description="Create a new calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Title of the new calendar",
                        },
                        "description": {
                            "type": "string",
                            "description": "Description of the new calendar",
                        },
                        "timezone": {
                            "type": "string",
                            "description": "Time zone for the calendar (e.g., 'America/Chicago')",
                        },
                    },
                    "required": ["summary"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.calendars.delete",
                method="DELETE",
                google_path="/calendar/v3/calendars/{calendarId}",
                description="Delete a calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier to delete",
                        },
                    },
                    "required": ["calendar_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Free/Busy ──
            RouteDef(
                route_id="calendar.freebusy.query",
                method="POST",
                google_path="/calendar/v3/freeBusy",
                description="Query free/busy information for calendars",
                input_schema={
                    "type": "object",
                    "properties": {
                        "time_min": {
                            "type": "string",
                            "description": "Start of query range (RFC3339)",
                        },
                        "time_max": {
                            "type": "string",
                            "description": "End of query range (RFC3339)",
                        },
                        "calendar_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Calendar IDs to query",
                        },
                    },
                    "required": ["time_min", "time_max"],
                },
                default_policy={},
            ),
            # ── ACL (sharing) ──
            RouteDef(
                route_id="calendar.acl.list",
                method="GET",
                google_path="/calendar/v3/calendars/{calendarId}/acl",
                description="List calendar access control rules",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                    },
                    "required": ["calendar_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.acl.get",
                method="GET",
                google_path="/calendar/v3/calendars/{calendarId}/acl/{ruleId}",
                description="Get a specific ACL rule",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "rule_id": {
                            "type": "string",
                            "description": "The ACL rule ID to retrieve",
                        },
                    },
                    "required": ["calendar_id", "rule_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.acl.create",
                method="POST",
                google_path="/calendar/v3/calendars/{calendarId}/acl",
                description="Create an ACL rule (share a calendar)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "role": {
                            "type": "string",
                            "description": ("Role to grant: reader, writer, or owner"),
                        },
                        "scope_type": {
                            "type": "string",
                            "description": "Scope type: user, group, or default",
                        },
                        "scope_value": {
                            "type": "string",
                            "description": ("Email address or group email for the scope"),
                        },
                    },
                    "required": ["calendar_id", "role", "scope_type"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.acl.delete",
                method="DELETE",
                google_path="/calendar/v3/calendars/{calendarId}/acl/{ruleId}",
                description="Delete an ACL rule",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "rule_id": {
                            "type": "string",
                            "description": "The ACL rule ID to delete",
                        },
                    },
                    "required": ["calendar_id", "rule_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Calendar List ──
            RouteDef(
                route_id="calendar.calendarlist.get",
                method="GET",
                google_path=("/calendar/v3/users/me/calendarList/{calendarId}"),
                description="Get a calendar list entry",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                        },
                    },
                    "required": ["calendar_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.calendarlist.insert",
                method="POST",
                google_path="/calendar/v3/users/me/calendarList",
                description="Add a calendar to the user's list",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "ID of the calendar to add",
                        },
                        "summary_override": {
                            "type": "string",
                            "description": "Custom name for the calendar",
                        },
                    },
                    "required": ["calendar_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.calendarlist.update",
                method="PUT",
                google_path=("/calendar/v3/users/me/calendarList/{calendarId}"),
                description="Update a calendar list entry",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                        },
                        "summary_override": {
                            "type": "string",
                            "description": "New custom name",
                        },
                        "hidden": {
                            "type": "boolean",
                            "description": ("Whether the calendar is hidden from the list"),
                        },
                        "selected": {
                            "type": "boolean",
                            "description": "Whether the calendar is selected",
                        },
                    },
                    "required": ["calendar_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.calendarlist.delete",
                method="DELETE",
                google_path=("/calendar/v3/users/me/calendarList/{calendarId}"),
                description="Remove a calendar from the user's list",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier to remove",
                        },
                    },
                    "required": ["calendar_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Calendars (update/clear) ──
            RouteDef(
                route_id="calendar.calendars.update",
                method="PUT",
                google_path="/calendar/v3/calendars/{calendarId}",
                description="Update calendar metadata",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                        "summary": {
                            "type": "string",
                            "description": "New title for the calendar",
                        },
                        "description": {
                            "type": "string",
                            "description": "New description for the calendar",
                        },
                        "timezone": {
                            "type": "string",
                            "description": ("New time zone (e.g., 'America/Chicago')"),
                        },
                    },
                    "required": ["calendar_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.calendars.clear",
                method="POST",
                google_path="/calendar/v3/calendars/{calendarId}/clear",
                description="Clear all events from a calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Calendar identifier",
                            "default": "primary",
                        },
                    },
                    "required": ["calendar_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Colors ──
            RouteDef(
                route_id="calendar.colors.get",
                method="GET",
                google_path="/calendar/v3/colors",
                description="Get color definitions for calendars and events",
                input_schema={"type": "object", "properties": {}},
                default_policy={},
            ),
            # ── Events: move ──
            RouteDef(
                route_id="calendar.events.move",
                method="POST",
                google_path=("/calendar/v3/calendars/{calendarId}/events/{eventId}/move"),
                description="Move an event to another calendar",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {
                            "type": "string",
                            "description": "Source calendar identifier",
                        },
                        "event_id": {
                            "type": "string",
                            "description": "Event identifier",
                        },
                        "destination": {
                            "type": "string",
                            "description": "Destination calendar identifier",
                        },
                    },
                    "required": ["calendar_id", "event_id", "destination"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Settings ──
            RouteDef(
                route_id="calendar.settings.list",
                method="GET",
                google_path="/calendar/v3/users/me/settings",
                description="List user settings",
                input_schema={"type": "object", "properties": {}},
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.settings.get",
                method="GET",
                google_path="/calendar/v3/users/me/settings/{setting}",
                description="Get a specific user setting",
                input_schema={
                    "type": "object",
                    "properties": {
                        "setting": {
                            "type": "string",
                            "description": ("The setting ID (e.g., 'timezone')"),
                        },
                    },
                    "required": ["setting"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.acl.patch",
                method="PATCH",
                google_path="/calendar/v3/calendars/{calendarId}/acl/{ruleId}",
                description="Updates an access control rule. This method supports patch semantics.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["sendNotifications"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.acl.update",
                method="PUT",
                google_path="/calendar/v3/calendars/{calendarId}/acl/{ruleId}",
                description="Updates an access control rule.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["sendNotifications"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.acl.watch",
                method="POST",
                google_path="/calendar/v3/calendars/{calendarId}/acl/watch",
                description="Watch for changes to ACL resources.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["maxResults", "pageToken", "showDeleted", "syncToken"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.calendar_list.patch",
                method="PATCH",
                google_path="/calendar/v3/users/me/calendarList/{calendarId}",
                description=(
                    "Updates an existing calendar on the user's calendar "
                    "list. This method supports patch semantics."
                ),
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["colorRgbFormat"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.calendar_list.watch",
                method="POST",
                google_path="/calendar/v3/users/me/calendarList/watch",
                description="Watch for changes to CalendarList resources.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=[
                    "maxResults",
                    "minAccessRole",
                    "pageToken",
                    "showDeleted",
                    "showHidden",
                    "syncToken",
                ],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.calendars.patch",
                method="PATCH",
                google_path="/calendar/v3/calendars/{calendarId}",
                description=(
                    "Updates metadata for a calendar. This method supports patch semantics."
                ),
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.channels.stop",
                method="POST",
                google_path="/calendar/v3/channels/stop",
                description="Stop watching resources through this channel",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.events.import",
                method="POST",
                google_path="/calendar/v3/calendars/{calendarId}/events/import",
                description=(
                    "Imports an event. This operation is used to add a "
                    "private copy of an existing event to a calendar."
                ),
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["conferenceDataVersion", "supportsAttachments"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.events.instances",
                method="GET",
                google_path="/calendar/v3/calendars/{calendarId}/events/{eventId}/instances",
                description="Returns instances of the specified recurring event.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=[
                    "alwaysIncludeEmail",
                    "maxAttendees",
                    "maxResults",
                    "originalStart",
                    "pageToken",
                    "showDeleted",
                    "timeMax",
                    "timeMin",
                    "timeZone",
                ],
                default_policy={},
            ),
            RouteDef(
                route_id="calendar.events.patch",
                method="PATCH",
                google_path="/calendar/v3/calendars/{calendarId}/events/{eventId}",
                description="Updates an event. This method supports patch semantics.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=[
                    "alwaysIncludeEmail",
                    "conferenceDataVersion",
                    "maxAttendees",
                    "sendNotifications",
                    "sendUpdates",
                    "supportsAttachments",
                ],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.events.watch",
                method="POST",
                google_path="/calendar/v3/calendars/{calendarId}/events/watch",
                description="Watch for changes to Events resources.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=[
                    "alwaysIncludeEmail",
                    "eventTypes",
                    "iCalUID",
                    "maxAttendees",
                    "maxResults",
                    "orderBy",
                    "pageToken",
                    "privateExtendedProperty",
                    "q",
                    "sharedExtendedProperty",
                    "showDeleted",
                    "showHiddenInvitations",
                    "singleEvents",
                    "syncToken",
                    "timeMax",
                    "timeMin",
                    "timeZone",
                    "updatedMin",
                ],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="calendar.settings.watch",
                method="POST",
                google_path="/calendar/v3/users/me/settings/watch",
                description="Watch for changes to Settings resources.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["maxResults", "pageToken", "syncToken"],
                default_policy={},
                enabled_by_default=False,
            ),
        ]


Module = CalendarModule
