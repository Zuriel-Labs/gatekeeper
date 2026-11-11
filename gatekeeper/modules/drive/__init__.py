"""Google Drive module — file and folder operations."""

from __future__ import annotations

from gatekeeper.modules.base import GoogleModule
from gatekeeper.modules.route import RouteDef


class DriveModule(GoogleModule):
    name = "drive"
    display_name = "Google Drive"
    description = (
        "Browse, search, and read files in Google Drive, including Sheets, Docs, and Slides content"
    )
    icon = "📁"

    required_scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/presentations",
    ]

    def get_routes(self) -> list[RouteDef]:
        return [
            # ── Read operations (on by default) ──
            RouteDef(
                route_id="drive.files.list",
                method="GET",
                google_path="/drive/v3/files",
                description="List and search for files in Drive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "q": {
                            "type": "string",
                            "description": (
                                "Drive query string "
                                "(e.g., \"name contains 'report'\"). "
                                "See: https://developers.google.com/"
                                "drive/api/v3/search-files"
                            ),
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of files to return (max 100)",
                            "default": 20,
                        },
                        "order_by": {
                            "type": "string",
                            "description": "Sort field (e.g., 'modifiedTime')",
                            "default": "modifiedTime",
                        },
                        "fields": {
                            "type": "string",
                            "description": (
                                "Fields to include in the response "
                                "(e.g., 'files(id,name,mimeType)')"
                            ),
                            "default": (
                                "files(id,name,mimeType,modifiedTime,"
                                "size,owners,shared,parents),nextPageToken"
                            ),
                        },
                    },
                },
                # fields must be a query param — Google Drive API ignores it in the body
                query_params=["fields"],
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="drive.files.get",
                method="GET",
                google_path="/drive/v3/files/{fileId}",
                description="Get file metadata by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to retrieve",
                        },
                        "fields": {
                            "type": "string",
                            "description": "Fields to include in the response",
                            "default": "id,name,mimeType,modifiedTime,size,owners,shared,parents",
                        },
                    },
                    "required": ["file_id"],
                },
                # fields must be a query param — Google Drive API ignores it in the body
                query_params=["fields"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.files.export",
                method="GET",
                google_path="/drive/v3/files/{fileId}/export",
                description="Export a Google Workspace document to a given MIME type",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to export",
                        },
                        "mime_type": {
                            "type": "string",
                            "description": "Target MIME type (e.g., 'application/pdf')",
                            "default": "application/pdf",
                        },
                    },
                    "required": ["file_id"],
                },
                binary_response=True,
                default_policy={"max_inline_size_mb": 1},
            ),
            # ── File downloads ──
            RouteDef(
                route_id="drive.files.download",
                method="GET",
                google_path="/drive/v3/files/{fileId}",
                description="Download a file's binary content from Google Drive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to download",
                        },
                        "acknowledge_abuse": {
                            "type": "boolean",
                            "description": "Acknowledge potential abuse if flagged by Google",
                            "default": False,
                        },
                    },
                    "required": ["file_id"],
                },
                binary_response=True,
                default_policy={"max_inline_size_mb": 1},
            ),
            RouteDef(
                route_id="drive.files.list_shared",
                method="GET",
                google_path="/drive/v3/files",
                description="List files shared with the user",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_size": {
                            "type": "integer",
                            "description": "Number of files to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={"max_results": 50, "query_filter": "sharedWithMe=true"},
            ),
            # ── Write operations (off by default) ──
            RouteDef(
                route_id="drive.files.copy",
                method="POST",
                google_path="/drive/v3/files/{fileId}/copy",
                description="Copy a file (requires drive scope)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file to copy",
                        },
                        "name": {
                            "type": "string",
                            "description": "Name for the copy",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.create",
                method="POST",
                google_path="/drive/v3/files",
                description="Upload or create a new file in Drive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the new file",
                        },
                        "mime_type": {
                            "type": "string",
                            "description": "MIME type of the file",
                        },
                        "parents": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Parent folder IDs to add the file to",
                        },
                        "shortcut_target_id": {
                            "type": "string",
                            "description": (
                                "File ID the shortcut points to "
                                "(only used when mime_type is shortcut)"
                            ),
                        },
                        "shortcut_target_mime_type": {
                            "type": "string",
                            "description": (
                                "MIME type of the target file "
                                "(only used when mime_type is shortcut)"
                            ),
                        },
                    },
                    "required": ["name"],
                },
                default_policy={"max_file_size_mb": 25},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.upload",
                method="POST",
                google_path="/upload/drive/v3/files",
                description="Upload a new file with content to Google Drive via multipart",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the new file",
                        },
                        "base64_content": {
                            "type": "string",
                            "description": "Base64-encoded file content",
                        },
                        "mime_type": {
                            "type": "string",
                            "description": "MIME type of the file. Guessed from name if omitted.",
                        },
                        "parents": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Parent folder IDs to add the file to",
                        },
                        "description": {
                            "type": "string",
                            "description": "File description",
                        },
                    },
                    "required": ["name", "base64_content"],
                },
                query_params=["uploadType"],
                multipart_upload=True,
                default_policy={"max_file_size_mb": 25},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.update",
                method="PATCH",
                google_path="/drive/v3/files/{fileId}",
                description="Update file metadata or content",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to update",
                        },
                        "name": {
                            "type": "string",
                            "description": "New name for the file",
                        },
                        "description": {
                            "type": "string",
                            "description": "New description for the file",
                        },
                        "starred": {
                            "type": "boolean",
                            "description": "Whether the file is starred",
                        },
                        "add_parents": {
                            "type": "string",
                            "description": (
                                "Comma-separated parent folder IDs to add (for moving files)"
                            ),
                        },
                        "remove_parents": {
                            "type": "string",
                            "description": (
                                "Comma-separated parent folder IDs to remove (for moving files)"
                            ),
                        },
                    },
                    "required": ["file_id"],
                },
                # addParents/removeParents MUST be query params, not body —
                # Google Drive API silently ignores them in the PATCH body.
                query_params=["addParents", "removeParents"],
                default_policy={},
                enabled_by_default=True,
            ),
            RouteDef(
                route_id="drive.files.delete",
                method="DELETE",
                google_path="/drive/v3/files/{fileId}",
                description="Permanently delete a file (cannot be undone)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to permanently delete",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.trash",
                method="POST",
                google_path="/drive/v3/files/{fileId}",
                description="Move a file to trash (recoverable)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to trash",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Permissions ──
            RouteDef(
                route_id="drive.permissions.list",
                method="GET",
                google_path="/drive/v3/files/{fileId}/permissions",
                description="See who a file is shared with",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to check permissions for",
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.permissions.get",
                method="GET",
                google_path="/drive/v3/files/{fileId}/permissions/{permissionId}",
                description="Get details of a specific permission on a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file",
                        },
                        "permission_id": {
                            "type": "string",
                            "description": "The ID of the permission to retrieve",
                        },
                    },
                    "required": ["file_id", "permission_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.permissions.create",
                method="POST",
                google_path="/drive/v3/files/{fileId}/permissions",
                description="Share a file with someone — add a new permission",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file to share",
                        },
                        "email_address": {
                            "type": "string",
                            "description": "Email address of the person to share with",
                        },
                        "role": {
                            "type": "string",
                            "description": "Role to grant: reader, writer, organizer, or owner",
                            "default": "reader",
                        },
                        "type": {
                            "type": "string",
                            "description": "Permission type: user, group, or anyone",
                            "default": "user",
                        },
                    },
                    "required": ["file_id", "email_address"],
                },
                default_policy={"max_recipients": 5},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.permissions.delete",
                method="DELETE",
                google_path="/drive/v3/files/{fileId}/permissions/{permissionId}",
                description="Remove someone's access to a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "The ID of the file",
                        },
                        "permission_id": {
                            "type": "string",
                            "description": "The ID of the permission to remove",
                        },
                    },
                    "required": ["file_id", "permission_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── About ──
            RouteDef(
                route_id="drive.about.get",
                method="GET",
                google_path="/drive/v3/about",
                description="Get user Drive storage quota and usage info",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            # ── Changes ──
            RouteDef(
                route_id="drive.changes.list",
                method="GET",
                google_path="/drive/v3/changes",
                description="List changes to files (incremental sync)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_token": {
                            "type": "string",
                            "description": ("Token for continuing a previous list request"),
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of changes to return",
                            "default": 100,
                        },
                    },
                },
                default_policy={"max_results": 100},
            ),
            RouteDef(
                route_id="drive.changes.get_start_page_token",
                method="GET",
                google_path="/drive/v3/changes/startPageToken",
                description="Get start page token for change tracking",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            # ── Comments ──
            RouteDef(
                route_id="drive.comments.list",
                method="GET",
                google_path="/drive/v3/files/{fileId}/comments",
                description="List comments on a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of comments to return",
                            "default": 20,
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.comments.get",
                method="GET",
                google_path=("/drive/v3/files/{fileId}/comments/{commentId}"),
                description="Get a comment by ID",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "comment_id": {
                            "type": "string",
                            "description": "ID of the comment",
                        },
                    },
                    "required": ["file_id", "comment_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.comments.create",
                method="POST",
                google_path="/drive/v3/files/{fileId}/comments",
                description="Create a comment on a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "content": {
                            "type": "string",
                            "description": "Comment text",
                        },
                    },
                    "required": ["file_id", "content"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Shared Drives ──
            RouteDef(
                route_id="drive.drives.list",
                method="GET",
                google_path="/drive/v3/drives",
                description="List shared drives",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_size": {
                            "type": "integer",
                            "description": "Number of drives to return",
                            "default": 20,
                        },
                    },
                },
                default_policy={"max_results": 50},
            ),
            RouteDef(
                route_id="drive.drives.get",
                method="GET",
                google_path="/drive/v3/drives/{driveId}",
                description="Get shared drive metadata",
                input_schema={
                    "type": "object",
                    "properties": {
                        "drive_id": {
                            "type": "string",
                            "description": "ID of the shared drive",
                        },
                    },
                    "required": ["drive_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.drives.create",
                method="POST",
                google_path="/drive/v3/drives",
                description="Create a shared drive",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the new shared drive",
                        },
                    },
                    "required": ["name"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Files (additional) ──
            RouteDef(
                route_id="drive.files.empty_trash",
                method="DELETE",
                google_path="/drive/v3/files/trash",
                description="Permanently delete all trashed files",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.generate_ids",
                method="GET",
                google_path="/drive/v3/files/generateIds",
                description="Generate file IDs for future uploads",
                input_schema={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of IDs to generate",
                            "default": 10,
                        },
                    },
                },
                default_policy={},
            ),
            # ── Permissions (continued) ──
            RouteDef(
                route_id="drive.permissions.update",
                method="PATCH",
                google_path=("/drive/v3/files/{fileId}/permissions/{permissionId}"),
                description="Update a permission on a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "permission_id": {
                            "type": "string",
                            "description": "ID of the permission to update",
                        },
                        "role": {
                            "type": "string",
                            "description": ("New role: reader, writer, organizer, or owner"),
                        },
                    },
                    "required": ["file_id", "permission_id"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Revisions ──
            RouteDef(
                route_id="drive.revisions.list",
                method="GET",
                google_path="/drive/v3/files/{fileId}/revisions",
                description="List file revisions",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of revisions to return",
                            "default": 20,
                        },
                    },
                    "required": ["file_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.revisions.get",
                method="GET",
                google_path=("/drive/v3/files/{fileId}/revisions/{revisionId}"),
                description="Get a specific file revision",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "ID of the file",
                        },
                        "revision_id": {
                            "type": "string",
                            "description": "ID of the revision",
                        },
                    },
                    "required": ["file_id", "revision_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.accessproposals.get",
                method="GET",
                google_path="/drive/v3/files/{fileId}/accessproposals/{proposalId}",
                description="Retrieves an access proposal by ID.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.accessproposals.resolve",
                method="POST",
                google_path="/drive/v3/files/{fileId}/accessproposals/{proposalId}:resolve",
                description="Approves or denies an access proposal.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.accessproposals.list",
                method="GET",
                google_path="/drive/v3/files/{fileId}/accessproposals",
                description="List the access proposals on a file.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["pageSize", "pageToken"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.approvals.get",
                method="GET",
                google_path="/drive/v3/files/{fileId}/approvals/{approvalId}",
                description="Gets an approval by ID.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.approvals.list",
                method="GET",
                google_path="/drive/v3/files/{fileId}/approvals",
                description="Lists the approvals on a file.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["pageSize", "pageToken"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.approvals.start",
                method="POST",
                google_path="/drive/v3/files/{fileId}/approvals:start",
                description="Starts an approval on a file.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.approvals.approve",
                method="POST",
                google_path="/drive/v3/files/{fileId}/approvals/{approvalId}:approve",
                description="Approves an approval.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.approvals.decline",
                method="POST",
                google_path="/drive/v3/files/{fileId}/approvals/{approvalId}:decline",
                description="Declines an approval.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.approvals.cancel",
                method="POST",
                google_path="/drive/v3/files/{fileId}/approvals/{approvalId}:cancel",
                description="Cancels an approval.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.approvals.comment",
                method="POST",
                google_path="/drive/v3/files/{fileId}/approvals/{approvalId}:comment",
                description="Comments on an approval.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.approvals.reassign",
                method="POST",
                google_path="/drive/v3/files/{fileId}/approvals/{approvalId}:reassign",
                description="Reassigns the reviewers on an approval.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.apps.get",
                method="GET",
                google_path="/drive/v3/apps/{appId}",
                description="Gets a specific app.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.apps.list",
                method="GET",
                google_path="/drive/v3/apps",
                description="Lists a user's installed apps.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["appFilterExtensions", "appFilterMimeTypes", "languageCode"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.changes.watch",
                method="POST",
                google_path="/drive/v3/changes/watch",
                description="Subscribes to changes for a user.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=[
                    "driveId",
                    "includeCorpusRemovals",
                    "includeItemsFromAllDrives",
                    "includeLabels",
                    "includePermissionsForView",
                    "includeRemoved",
                    "includeTeamDriveItems",
                    "pageSize",
                    "pageToken",
                    "restrictToMyDrive",
                    "spaces",
                    "supportsAllDrives",
                    "supportsTeamDrives",
                    "teamDriveId",
                ],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.channels.stop",
                method="POST",
                google_path="/drive/v3/channels/stop",
                description="Stops watching resources through this channel.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.comments.delete",
                method="DELETE",
                google_path="/drive/v3/files/{fileId}/comments/{commentId}",
                description="Deletes a comment.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.comments.update",
                method="PATCH",
                google_path="/drive/v3/files/{fileId}/comments/{commentId}",
                description="Updates a comment with patch semantics.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.drives.delete",
                method="DELETE",
                google_path="/drive/v3/drives/{driveId}",
                description="Permanently deletes a shared drive.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["allowItemDeletion", "useDomainAdminAccess"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.drives.hide",
                method="POST",
                google_path="/drive/v3/drives/{driveId}/hide",
                description="Hides a shared drive from the default view.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.drives.unhide",
                method="POST",
                google_path="/drive/v3/drives/{driveId}/unhide",
                description="Restores a shared drive to the default view.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.drives.update",
                method="PATCH",
                google_path="/drive/v3/drives/{driveId}",
                description="Updates the metadata for a shared drive.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["useDomainAdminAccess"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.generate_cse_token",
                method="GET",
                google_path="/drive/v3/files/generateCseToken",
                description="Generates a CSE token for creating or updating CSE files.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["fileId", "parent"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.files.list_labels",
                method="GET",
                google_path="/drive/v3/files/{fileId}/listLabels",
                description="Lists the labels on a file.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["maxResults", "pageToken"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.files.modify_labels",
                method="POST",
                google_path="/drive/v3/files/{fileId}/modifyLabels",
                description="Modifies the set of labels applied to a file.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.files.watch",
                method="POST",
                google_path="/drive/v3/files/{fileId}/watch",
                description="Subscribes to changes to a file.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=[
                    "acknowledgeAbuse",
                    "includeLabels",
                    "includePermissionsForView",
                    "supportsAllDrives",
                    "supportsTeamDrives",
                ],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.operations.get",
                method="GET",
                google_path="/drive/v3/operations/{name}",
                description="Gets the latest state of a long-running operation.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.replies.create",
                method="POST",
                google_path="/drive/v3/files/{fileId}/comments/{commentId}/replies",
                description="Creates a reply to a comment.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.replies.delete",
                method="DELETE",
                google_path="/drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId}",
                description="Deletes a reply.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.replies.get",
                method="GET",
                google_path="/drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId}",
                description="Gets a reply by ID.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["includeDeleted"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.replies.list",
                method="GET",
                google_path="/drive/v3/files/{fileId}/comments/{commentId}/replies",
                description="Lists a comment's replies.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["includeDeleted", "pageSize", "pageToken"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.replies.update",
                method="PATCH",
                google_path="/drive/v3/files/{fileId}/comments/{commentId}/replies/{replyId}",
                description="Updates a reply with patch semantics.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.revisions.delete",
                method="DELETE",
                google_path="/drive/v3/files/{fileId}/revisions/{revisionId}",
                description="Permanently deletes a file version.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.revisions.update",
                method="PATCH",
                google_path="/drive/v3/files/{fileId}/revisions/{revisionId}",
                description="Updates a revision with patch semantics.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.teamdrives.create",
                method="POST",
                google_path="/drive/v3/teamdrives",
                description="Deprecated: Use drives.create instead.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["requestId"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.teamdrives.delete",
                method="DELETE",
                google_path="/drive/v3/teamdrives/{teamDriveId}",
                description="Deprecated: Use drives.delete instead.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.teamdrives.get",
                method="GET",
                google_path="/drive/v3/teamdrives/{teamDriveId}",
                description="Deprecated: Use drives.get instead.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["useDomainAdminAccess"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.teamdrives.list",
                method="GET",
                google_path="/drive/v3/teamdrives",
                description="Deprecated: Use drives.list instead.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["pageSize", "pageToken", "q", "useDomainAdminAccess"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.teamdrives.update",
                method="PATCH",
                google_path="/drive/v3/teamdrives/{teamDriveId}",
                description="Deprecated: Use drives.update instead.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                query_params=["useDomainAdminAccess"],
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Google Sheets API (sheets.googleapis.com) ──
            # All routes target https://sheets.googleapis.com, NOT
            # www.googleapis.com, so each carries base_url=...
            RouteDef(
                route_id="drive.sheets.spreadsheets.get",
                method="GET",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}",
                description="Get spreadsheet metadata (sheets, named ranges, properties)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "The ID of the spreadsheet to retrieve",
                        },
                        "fields": {
                            "type": "string",
                            "description": "Fields to include in the response (partial response)",
                        },
                    },
                    "required": ["spreadsheet_id"],
                },
                query_params=["fields"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.sheets.values.get",
                method="GET",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values/{range}",
                description="Read a single range of cell values from a spreadsheet",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "The ID of the spreadsheet",
                        },
                        "range": {
                            "type": "string",
                            "description": (
                                "A1 or R1C1 notation of the range (e.g., 'Sheet1!A1:C10')"
                            ),
                        },
                        "value_render_option": {
                            "type": "string",
                            "description": "FORMATTED_VALUE, UNFORMATTED_VALUE, or FORMULA",
                            "default": "FORMATTED_VALUE",
                        },
                        "date_time_render_option": {
                            "type": "string",
                            "description": "SERIAL_NUMBER or FORMATTED_STRING",
                        },
                        "major_dimension": {
                            "type": "string",
                            "description": "ROWS or COLUMNS",
                        },
                    },
                    "required": ["spreadsheet_id", "range"],
                },
                query_params=["value_render_option", "date_time_render_option", "major_dimension"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.sheets.values.batch_get",
                method="GET",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values:batchGet",
                description="Read multiple ranges of cell values in one request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "The ID of the spreadsheet",
                        },
                        "ranges": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A1/R1C1 ranges to retrieve (e.g., ['Sheet1!A1:B2'])",
                        },
                        "value_render_option": {
                            "type": "string",
                            "description": "FORMATTED_VALUE, UNFORMATTED_VALUE, or FORMULA",
                        },
                        "date_time_render_option": {"type": "string"},
                        "major_dimension": {"type": "string", "description": "ROWS or COLUMNS"},
                    },
                    "required": ["spreadsheet_id"],
                },
                query_params=[
                    "ranges",
                    "value_render_option",
                    "date_time_render_option",
                    "major_dimension",
                ],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.sheets.values.update",
                method="PUT",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values/{range}",
                description="Write values to a range of cells in a spreadsheet",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "range": {"type": "string", "description": "A1/R1C1 range to write"},
                        "values": {
                            "type": "array",
                            "items": {"type": "array", "items": {}},
                            "description": "2D array of values (e.g., [['A', 1], ['B', 2]])",
                        },
                        "value_input_option": {
                            "type": "string",
                            "description": "RAW or USER_ENTERED",
                            "default": "RAW",
                        },
                    },
                    "required": ["spreadsheet_id", "range", "values"],
                },
                query_params=["value_input_option"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.sheets.values.append",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values/{range}:append",
                description="Append values after the last row of data in a range",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "range": {
                            "type": "string",
                            "description": (
                                "A1 notation of the table to search (e.g., 'Sheet1!A1:B')"
                            ),
                        },
                        "values": {
                            "type": "array",
                            "items": {"type": "array", "items": {}},
                            "description": "2D array of values to append",
                        },
                        "value_input_option": {
                            "type": "string",
                            "default": "RAW",
                            "description": "RAW or USER_ENTERED",
                        },
                        "insert_data_option": {
                            "type": "string",
                            "default": "OVERWRITE",
                            "description": "OVERWRITE or INSERT_ROWS",
                        },
                    },
                    "required": ["spreadsheet_id", "range", "values"],
                },
                query_params=["value_input_option", "insert_data_option"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.sheets.values.clear",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values/{range}:clear",
                description="Clear values from a range of cells",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "range": {"type": "string", "description": "A1/R1C1 range to clear"},
                    },
                    "required": ["spreadsheet_id", "range"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.sheets.values.batch_update",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}/values:batchUpdate",
                description="Update multiple ranges of cell values in a single request",
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "value_input_option": {
                            "type": "string",
                            "default": "RAW",
                            "description": "RAW or USER_ENTERED",
                        },
                        "data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "range": {"type": "string"},
                                    "values": {
                                        "type": "array",
                                        "items": {"type": "array", "items": {}},
                                    },
                                },
                            },
                            "description": "One entry per range to write",
                        },
                    },
                    "required": ["spreadsheet_id", "data"],
                },
                query_params=["value_input_option"],
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.sheets.spreadsheets.create",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets",
                description="Create a new spreadsheet (optional title and sheets)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title of the new spreadsheet"},
                        "sheet_titles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Names of sheets to create within the spreadsheet",
                        },
                    },
                },
                default_policy={},
                enabled_by_default=False,
                body_transform="sheet_create",
            ),
            RouteDef(
                route_id="drive.sheets.spreadsheets.batch_update",
                method="POST",
                base_url="https://sheets.googleapis.com",
                google_path="/v4/spreadsheets/{spreadsheetId}:batchUpdate",
                description=(
                    "Apply one or more updates to a spreadsheet "
                    "(formatting, formulas, charts, etc.)"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string"},
                        "requests": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": (
                                "List of update request objects (see "
                                "Sheets API batchUpdate reference)"
                            ),
                        },
                    },
                    "required": ["spreadsheet_id", "requests"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Google Docs API (docs.googleapis.com) ──
            RouteDef(
                route_id="drive.docs.documents.get",
                method="GET",
                base_url="https://docs.googleapis.com",
                google_path="/v1/documents/{documentId}",
                description="Get the full content and structure of a Google Doc",
                input_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "suggestions_view_mode": {
                            "type": "string",
                            "description": (
                                "SUGGESTIONS_INLINE, PREVIEW_SUGGESTIONS_ACCEPTED, "
                                "or PREVIEW_WITHOUT_SUGGESTIONS"
                            ),
                        },
                    },
                    "required": ["document_id"],
                },
                query_params=["suggestions_view_mode"],
                default_policy={},
            ),
            RouteDef(
                route_id="drive.docs.documents.create",
                method="POST",
                base_url="https://docs.googleapis.com",
                google_path="/v1/documents",
                description="Create a new Google Doc with an optional title",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title for the new document"},
                    },
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.docs.documents.batch_update",
                method="POST",
                base_url="https://docs.googleapis.com",
                google_path="/v1/documents/{documentId}:batchUpdate",
                description=(
                    "Apply one or more updates to a Google Doc (insert text, delete, style, etc.)"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "requests": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": (
                                "Update requests (InsertTextRequest, "
                                "DeleteContentRangeRequest, etc.)"
                            ),
                        },
                        "write_control": {
                            "type": "object",
                            "description": (
                                "Optional concurrency control "
                                "(required_revision_id / target_revision_id)"
                            ),
                        },
                    },
                    "required": ["document_id", "requests"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
            # ── Google Slides API (slides.googleapis.com) ──
            RouteDef(
                route_id="drive.slides.presentations.get",
                method="GET",
                base_url="https://slides.googleapis.com",
                google_path="/v1/presentations/{presentationId}",
                description="Get the full content and structure of a Google Slides presentation",
                input_schema={
                    "type": "object",
                    "properties": {
                        "presentation_id": {"type": "string"},
                    },
                    "required": ["presentation_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.slides.presentations.pages.get",
                method="GET",
                base_url="https://slides.googleapis.com",
                google_path="/v1/presentations/{presentationId}/pages/{pageObjectId}",
                description="Get a specific page (slide) from a presentation",
                input_schema={
                    "type": "object",
                    "properties": {
                        "presentation_id": {"type": "string"},
                        "page_object_id": {"type": "string"},
                    },
                    "required": ["presentation_id", "page_object_id"],
                },
                default_policy={},
            ),
            RouteDef(
                route_id="drive.slides.presentations.create",
                method="POST",
                base_url="https://slides.googleapis.com",
                google_path="/v1/presentations",
                description="Create a new Google Slides presentation with an optional title",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Title for the new presentation",
                        },
                    },
                },
                default_policy={},
                enabled_by_default=False,
            ),
            RouteDef(
                route_id="drive.slides.presentations.batch_update",
                method="POST",
                base_url="https://slides.googleapis.com",
                google_path="/v1/presentations/{presentationId}:batchUpdate",
                description=(
                    "Apply updates to a presentation (add slides, insert text, update shapes, etc.)"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "presentation_id": {"type": "string"},
                        "requests": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": (
                                "Update requests (CreateSlideRequest, InsertTextRequest, etc.)"
                            ),
                        },
                    },
                    "required": ["presentation_id", "requests"],
                },
                default_policy={},
                enabled_by_default=False,
            ),
        ]


Module = DriveModule
