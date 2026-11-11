"""Google Gmail module — read and send email with policy controls."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class GmailModule(GoogleModule):
    name = "gmail"
    display_name = "Google Gmail"
    description = "Read, search, and send email via Gmail"
    icon = "📧"

    required_scopes = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.settings.basic",
    ]

    def get_routes(self) -> list[RouteDef]:
        return [
            # ── Messages: read (on by default) ──
            RouteDef(
                route_id="gmail.messages.list",
                method="GET",
                google_path="/gmail/v1/users/me/messages",
                description="List messages in the user's mailbox",
                input_schema={
                    "type": "object",
                    "properties": {
                        "label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to filter by (e.g., ['INBOX', 'UNREAD'])",
                        },
                        "q": {
                            "type": "string",
                            "description": (
                                "Gmail search query (e.g., 'from:alice subject:report')"
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of messages to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={
                    "max_results": 50,
                    "allowed_labels": ["INBOX", "SENT", "DRAFT", "UNREAD", "IMPORTANT"],
                    "exclude_labels": ["SPAM", "TRASH"],
                },
            ),
            RouteDef(
                route_id="gmail.messages.get",
                method="GET",
                google_path="/gmail/v1/users/me/messages/{messageId}",
                description="Get a specific message by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "The ID of the message to retrieve",
                        },
                        "format": {
                            "type": "string",
                            "description": "Format: full, minimal, raw, metadata",
                            "default": "full",
                        },
                    },
                    "required": ["message_id"],
                },
                default_policy={},
            ),
            # ── Messages: write (off by default) ──
            RouteDef(
                route_id="gmail.messages.send",
                method="POST",
                google_path="/gmail/v1/users/me/messages/send",
                description="Send an email message",
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Recipient email addresses",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject line",
                        },
                        "body": {
                            "type": "string",
                            "description": "Email body text",
                        },
                    },
                    "required": ["to", "subject", "body"],
                },
                default_policy={
                    "max_recipients": 5,
                    "max_attachment_size_mb": 10,
                    "require_body": True,
                },
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.messages.modify",
                method="POST",
                google_path="/gmail/v1/users/me/messages/{messageId}/modify",
                description="Change labels on a message (archive, mark read, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "The ID of the message to modify",
                        },
                        "add_label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to add",
                        },
                        "remove_label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to remove",
                        },
                    },
                    "required": ["message_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.messages.trash",
                method="POST",
                google_path="/gmail/v1/users/me/messages/{messageId}/trash",
                description="Move a message to trash (recoverable)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "The ID of the message to trash",
                        },
                    },
                    "required": ["message_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.messages.delete",
                method="DELETE",
                google_path="/gmail/v1/users/me/messages/{messageId}",
                description="Permanently delete a message (cannot be undone)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "The ID of the message to permanently delete",
                        },
                    },
                    "required": ["message_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Drafts ──
            RouteDef(
                route_id="gmail.drafts.list",
                method="GET",
                google_path="/gmail/v1/users/me/drafts",
                description="List draft messages",
                input_schema={
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of drafts to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="gmail.drafts.get",
                method="GET",
                google_path="/gmail/v1/users/me/drafts/{draftId}",
                description="Get a specific draft by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "draft_id": {
                            "type": "string",
                            "description": "The ID of the draft to retrieve",
                        },
                        "format": {
                            "type": "string",
                            "description": "Format: full, minimal, raw, metadata",
                            "default": "full",
                        },
                    },
                    "required": ["draft_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.drafts.create",
                method="POST",
                google_path="/gmail/v1/users/me/drafts",
                description="Create a new draft message",
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Recipient email addresses",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject line",
                        },
                        "body": {
                            "type": "string",
                            "description": "Email body text",
                        },
                    },
                    "required": ["to", "subject", "body"],
                },
                default_policy={"max_recipients": 5},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.drafts.update",
                method="PUT",
                google_path="/gmail/v1/users/me/drafts/{draftId}",
                description="Edit an existing draft",
                input_schema={
                    "type": "object",
                    "properties": {
                        "draft_id": {
                            "type": "string",
                            "description": "The ID of the draft to update",
                        },
                        "to": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Updated recipient email addresses",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Updated email subject line",
                        },
                        "body": {
                            "type": "string",
                            "description": "Updated email body text",
                        },
                    },
                    "required": ["draft_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.drafts.send",
                method="POST",
                google_path="/gmail/v1/users/me/drafts/send",
                description="Send an existing draft (separate from messages.send)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "draft_id": {
                            "type": "string",
                            "description": "The ID of the draft to send",
                        },
                    },
                    "required": ["draft_id"],
                },
                default_policy={"max_recipients": 5},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.drafts.delete",
                method="DELETE",
                google_path="/gmail/v1/users/me/drafts/{draftId}",
                description="Delete a draft",
                input_schema={
                    "type": "object",
                    "properties": {
                        "draft_id": {
                            "type": "string",
                            "description": "The ID of the draft to delete",
                        },
                    },
                    "required": ["draft_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Labels ──
            RouteDef(
                route_id="gmail.labels.list",
                method="GET",
                google_path="/gmail/v1/users/me/labels",
                description="List all labels in the user's mailbox",
                input_schema={"type": "object", "properties": {}},
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.labels.get",
                method="GET",
                google_path="/gmail/v1/users/me/labels/{labelId}",
                description="Get details of a specific label",
                input_schema={
                    "type": "object",
                    "properties": {
                        "label_id": {
                            "type": "string",
                            "description": "The ID of the label to retrieve",
                        },
                    },
                    "required": ["label_id"],
                },
                default_policy={},
            ),
            # ── Filters (off by default) ──
            RouteDef(
                route_id="gmail.filters.list",
                method="GET",
                google_path="/gmail/v1/users/me/settings/filters",
                description="List all email filters",
                input_schema={"type": "object", "properties": {}},
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.filters.get",
                method="GET",
                google_path="/gmail/v1/users/me/settings/filters/{filterId}",
                description="Get details of a specific filter",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filter_id": {
                            "type": "string",
                            "description": "The ID of the filter to retrieve",
                        },
                    },
                    "required": ["filter_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.filters.create",
                method="POST",
                google_path="/gmail/v1/users/me/settings/filters",
                description="Create a new email filter with criteria and actions",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Gmail search query for the filter criteria "
                                "(e.g., 'from:alice@example.com')"
                            ),
                        },
                        "label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to apply to matching messages",
                        },
                        "forward": {
                            "type": "string",
                            "description": "Email address to forward matching messages to",
                        },
                        "mark_as_read": {
                            "type": "boolean",
                            "description": "Whether to mark matching messages as read",
                        },
                        "mark_as_important": {
                            "type": "boolean",
                            "description": "Whether to mark matching messages as important",
                        },
                        "archive": {
                            "type": "boolean",
                            "description": "Whether to archive matching messages (skip inbox)",
                        },
                        "delete": {
                            "type": "boolean",
                            "description": "Whether to send matching messages to trash",
                        },
                        "star": {
                            "type": "boolean",
                            "description": "Whether to star matching messages",
                        },
                    },
                    "required": ["query"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.filters.update",
                method="PATCH",
                google_path="/gmail/v1/users/me/settings/filters/{filterId}",
                description="Update an existing filter's criteria or actions",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filter_id": {
                            "type": "string",
                            "description": "The ID of the filter to update",
                        },
                        "query": {
                            "type": "string",
                            "description": "New Gmail search query for the filter criteria",
                        },
                        "label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "New label IDs to apply",
                        },
                        "mark_as_read": {
                            "type": "boolean",
                            "description": "Whether to mark matching messages as read",
                        },
                        "mark_as_important": {
                            "type": "boolean",
                            "description": "Whether to mark matching messages as important",
                        },
                        "archive": {
                            "type": "boolean",
                            "description": "Whether to archive matching messages",
                        },
                    },
                    "required": ["filter_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.filters.delete",
                method="DELETE",
                google_path="/gmail/v1/users/me/settings/filters/{filterId}",
                description="Delete an email filter",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filter_id": {
                            "type": "string",
                            "description": "The ID of the filter to delete",
                        },
                    },
                    "required": ["filter_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Labels: write (off by default) ──
            RouteDef(
                route_id="gmail.labels.create",
                method="POST",
                google_path="/gmail/v1/users/me/labels",
                description="Create a new custom label",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Display name of the label",
                        },
                        "label_list_visibility": {
                            "type": "string",
                            "description": (
                                "Whether the label is visible in the "
                                "label list: 'labelShow' or 'labelHide'"
                            ),
                            "default": "labelShow",
                        },
                        "message_list_visibility": {
                            "type": "string",
                            "description": (
                                "Whether messages with this label are "
                                "visible in the message list: 'show' or 'hide'"
                            ),
                            "default": "show",
                        },
                    },
                    "required": ["name"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.labels.update",
                method="PATCH",
                google_path="/gmail/v1/users/me/labels/{labelId}",
                description="Update a label (rename, change visibility, color)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "label_id": {
                            "type": "string",
                            "description": "The ID of the label to update",
                        },
                        "name": {
                            "type": "string",
                            "description": "New display name for the label",
                        },
                        "label_list_visibility": {
                            "type": "string",
                            "description": (
                                "Whether the label is visible in the "
                                "label list: 'labelShow' or 'labelHide'"
                            ),
                        },
                        "message_list_visibility": {
                            "type": "string",
                            "description": (
                                "Whether messages with this label are "
                                "visible in the message list: 'show' or 'hide'"
                            ),
                        },
                    },
                    "required": ["label_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.labels.delete",
                method="DELETE",
                google_path="/gmail/v1/users/me/labels/{labelId}",
                description="Delete a custom label",
                input_schema={
                    "type": "object",
                    "properties": {
                        "label_id": {
                            "type": "string",
                            "description": "The ID of the label to delete",
                        },
                    },
                    "required": ["label_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Message untrash ──
            RouteDef(
                route_id="gmail.messages.untrash",
                method="POST",
                google_path="/gmail/v1/users/me/messages/{messageId}/untrash",
                description="Untrash a message (recover from trash)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "The ID of the message to untrash",
                        },
                    },
                    "required": ["message_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Message batch operations ──
            RouteDef(
                route_id="gmail.messages.batch_modify",
                method="POST",
                google_path="/gmail/v1/users/me/messages/batchModify",
                description="Modify labels on multiple messages at once",
                input_schema={
                    "type": "object",
                    "properties": {
                        "ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of message IDs to modify",
                        },
                        "add_label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to add",
                        },
                        "remove_label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to remove",
                        },
                    },
                    "required": ["ids"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.messages.batch_delete",
                method="POST",
                google_path="/gmail/v1/users/me/messages/batchDelete",
                description="Delete multiple messages at once",
                input_schema={
                    "type": "object",
                    "properties": {
                        "ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of message IDs to delete",
                        },
                    },
                    "required": ["ids"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Message attachments ──
            RouteDef(
                route_id="gmail.messages.attachments.get",
                method="GET",
                google_path=("/gmail/v1/users/me/messages/{messageId}/attachments/{attachmentId}"),
                description="Download a message attachment",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "The ID of the message",
                        },
                        "attachment_id": {
                            "type": "string",
                            "description": "The ID of the attachment",
                        },
                    },
                    "required": ["message_id", "attachment_id"],
                },
                default_policy={},
            ),
            # ── Threads ──
            RouteDef(
                route_id="gmail.threads.list",
                method="GET",
                google_path="/gmail/v1/users/me/threads",
                description="List email threads (conversations)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "q": {
                            "type": "string",
                            "description": "Gmail search query",
                        },
                        "label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to filter by",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of threads to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.threads.get",
                method="GET",
                google_path="/gmail/v1/users/me/threads/{threadId}",
                description="Get a thread with all its messages",
                input_schema={
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "The ID of the thread",
                        },
                        "format": {
                            "type": "string",
                            "description": ("Format: full, minimal, raw, metadata"),
                            "default": "full",
                        },
                    },
                    "required": ["thread_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.threads.modify",
                method="POST",
                google_path="/gmail/v1/users/me/threads/{threadId}/modify",
                description="Modify labels on all messages in a thread",
                input_schema={
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "The ID of the thread",
                        },
                        "add_label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to add",
                        },
                        "remove_label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Label IDs to remove",
                        },
                    },
                    "required": ["thread_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.threads.trash",
                method="POST",
                google_path="/gmail/v1/users/me/threads/{threadId}/trash",
                description="Trash a thread and all its messages",
                input_schema={
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "The ID of the thread to trash",
                        },
                    },
                    "required": ["thread_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.threads.untrash",
                method="POST",
                google_path="/gmail/v1/users/me/threads/{threadId}/untrash",
                description="Untrash a thread",
                input_schema={
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "The ID of the thread to untrash",
                        },
                    },
                    "required": ["thread_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.threads.delete",
                method="DELETE",
                google_path="/gmail/v1/users/me/threads/{threadId}",
                description="Permanently delete a thread",
                input_schema={
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": ("The ID of the thread to permanently delete"),
                        },
                    },
                    "required": ["thread_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── History ──
            RouteDef(
                route_id="gmail.history.list",
                method="GET",
                google_path="/gmail/v1/users/me/history",
                description="List mailbox history (incremental sync)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "start_history_id": {
                            "type": "string",
                            "description": "Starting history ID for the listing",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": ("Maximum number of history records to return"),
                            "default": 100,
                        },
                        "label_id": {
                            "type": "string",
                            "description": ("Only return history for this label"),
                        },
                    },
                },
                default_policy={},
            ),
            # ── Settings: forwarding ──
            RouteDef(
                route_id="gmail.settings.forwarding_addresses.list",
                method="GET",
                google_path=("/gmail/v1/users/me/settings/forwardingAddresses"),
                description="List forwarding addresses",
                input_schema={"type": "object", "properties": {}},
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.settings.forwarding_addresses.get",
                method="GET",
                google_path=("/gmail/v1/users/me/settings/forwardingAddresses/{forwardingEmail}"),
                description="Get a forwarding address",
                input_schema={
                    "type": "object",
                    "properties": {
                        "forwarding_email": {
                            "type": "string",
                            "description": "The forwarding email address",
                        },
                    },
                    "required": ["forwarding_email"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.settings.forwarding_addresses.create",
                method="POST",
                google_path=("/gmail/v1/users/me/settings/forwardingAddresses"),
                description="Create a forwarding address",
                input_schema={
                    "type": "object",
                    "properties": {
                        "forwarding_email": {
                            "type": "string",
                            "description": "The email address to forward to",
                        },
                    },
                    "required": ["forwarding_email"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.settings.forwarding_addresses.delete",
                method="DELETE",
                google_path=("/gmail/v1/users/me/settings/forwardingAddresses/{forwardingEmail}"),
                description="Delete a forwarding address",
                input_schema={
                    "type": "object",
                    "properties": {
                        "forwarding_email": {
                            "type": "string",
                            "description": ("The forwarding email address to delete"),
                        },
                    },
                    "required": ["forwarding_email"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.get_profile",
                method="GET",
                google_path="/gmail/v1/users/me/profile",
                description="Gets the current user's Gmail profile.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.watch",
                method="POST",
                google_path="/gmail/v1/users/me/watch",
                description="Set up or update a push notification watch on the given user mailbox.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.stop",
                method="POST",
                google_path="/gmail/v1/users/me/stop",
                description="Turn off push notification delivery for the given user mailbox.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.messages.import",
                method="POST",
                google_path="/gmail/v1/users/me/messages/import",
                description="Imports a message into only this user's mailbox.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=[
                    "deleted",
                    "internalDateSource",
                    "neverMarkSpam",
                    "processForCalendar",
                ],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.messages.insert",
                method="POST",
                google_path="/gmail/v1/users/me/messages",
                description="Directly inserts a message into only this user's mailbox.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["deleted", "internalDateSource"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.labels.patch",
                method="PATCH",
                google_path="/gmail/v1/users/me/labels/{id}",
                description="Patch the specified label.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.settings.get_imap",
                method="GET",
                google_path="/gmail/v1/users/me/settings/imap",
                description="Gets IMAP settings.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.settings.update_imap",
                method="PUT",
                google_path="/gmail/v1/users/me/settings/imap",
                description="Updates IMAP settings.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.settings.get_pop",
                method="GET",
                google_path="/gmail/v1/users/me/settings/pop",
                description="Gets POP settings.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.settings.update_pop",
                method="PUT",
                google_path="/gmail/v1/users/me/settings/pop",
                description="Updates POP settings.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.settings.get_vacation",
                method="GET",
                google_path="/gmail/v1/users/me/settings/vacation",
                description="Gets vacation responder settings.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.settings.update_vacation",
                method="PUT",
                google_path="/gmail/v1/users/me/settings/vacation",
                description="Updates vacation responder settings.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.settings.get_language",
                method="GET",
                google_path="/gmail/v1/users/me/settings/language",
                description="Gets language settings.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.settings.update_language",
                method="PUT",
                google_path="/gmail/v1/users/me/settings/language",
                description="Updates language settings.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="gmail.settings.get_auto_forwarding",
                method="GET",
                google_path="/gmail/v1/users/me/settings/autoForwarding",
                description="Gets the auto-forwarding setting for the specified account.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="gmail.settings.update_auto_forwarding",
                method="PUT",
                google_path="/gmail/v1/users/me/settings/autoForwarding",
                description="Updates the auto-forwarding setting for the specified account.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
        ]


Module = GmailModule
