# Module 01: Workspaces & Members

## 1. Purpose
Provides multi-tenant project isolation for agile teams of 5–15 members. All tasks, bugs, channels, meetings, files, and time tracking entries are strictly partitioned by Workspace.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `workspaces/models.py`, `workspaces/views.py`, `workspaces/decorators.py`, `workspaces/tests.py`.

## 3. Main User Workflows
1. **Workspace Creation**: Platform Admins and authorized managers create a workspace with a unique name, slug, description, max seats (default 15), and storage quota (default 50 MB).
2. **Member Invitation**: Workspace Admins invite users via email with an assigned role (`ADMIN`, `MANAGER`, `CONTRIBUTOR`). System generates a secure 64-char token expiring in 7 days (`WorkspaceInvitation`).
3. **Invitation Acceptance**: Invitee accepts via `/workspaces/invitations/<token>/accept/`, creating an active `WorkspaceMembership`.
4. **Access Request Flow**: When an unauthorized user attempts to visit a workspace, they encounter the custom 403 page and submit a `WorkspaceAccessRequest` with an optional note.
5. **Temporary Privilege Elevation**: Contributors submit `GlobalAccessRequest` for specific actions (`task.delete`, `file.upload`), and Admins grant time-bounded `TemporaryAccessGrant` records without permanent role elevation.

## 4. User Roles & Permissions
* **Workspace Admin**: Can edit workspace profile, manage seat allocations, revoke invitations, change member roles, and approve access requests.
* **Workspace Manager**: Can coordinate sprints, view member reporting structures, and assign tasks across members.
* **Workspace Contributor**: Can participate in daily operations within assigned workspaces; cannot modify workspace settings or seat allocations.

## 5. Pages & Templates
* `templates/workspaces/workspace_dashboard.html`: Main workspace cockpit.
* `templates/workspaces/workspace_members.html`: Team member directory with functional roles, reporting hierarchy, and invite modals.
* `templates/workspaces/workspace_settings.html`: Workspace settings, storage quota usage, seat configuration.
* `templates/workspaces/workspace_invitation_accept.html`: Acceptance screen for new members.
* `templates/core/403.html`: Access request modal and denied state.

## 6. URLs, Views, Services & Models
* **URLs**: `workspaces/urls.py` (`workspace_dashboard`, `workspace_members`, `workspace_settings`, `invite_member`, `accept_invitation`).
* **Views**: `workspaces/views.py` (`workspace_members_view`, `workspace_settings_view`, `request_access_view`).
* **Models**: `Workspace`, `WorkspaceMembership`, `WorkspaceInvitation`, `WorkspaceAccessRequest`, `WorkspaceModule`, `GlobalAccessRequest`, `TemporaryAccessGrant`.

## 7. Business Rules & Invariants
* Unique constraint on `(workspace, slug)` and `(workspace, user)` for memberships.
* `max_seats` enforces capacity limit (default 15); warnings display when `seats_assigned >= max_seats`.
* Storage quota defaults to 50 MB (`storage_quota_mb`); calculated dynamically in bytes.
* Workspace deletion uses `models.PROTECT` on the owner relationship to prevent orphaned workspaces.

## 8. Database Relationships
* `Workspace` has many `WorkspaceMembership` (CASCADE).
* `Workspace` has many `WorkspaceModule` (CASCADE).
* `Workspace` has many `Task`, `Bug`, `Meeting`, `Channel`, `StoredFile`, `TimeEntry`.

## 9. API & WebSocket Interactions
* `POST /workspaces/w/<slug>/api/request-access/`: Submits JSON access request.
* `POST /workspaces/w/<slug>/api/grant-access/`: Approves temporary access grant.

## 10. Notifications & Integrations
* Dispatches `WORKSPACE_INVITE` and `ROLE_UPDATED` notifications to recipients.
* Logs administrative membership changes to `admin_panel.AuditLog`.

## 11. Error States & Edge Cases
* Visiting invalid workspace slug -> `404 Not Found`.
* Visiting workspace without membership -> `403 Forbidden` + `WorkspaceAccessRequest` modal.
* Duplicate invite to existing member -> Form validation error: "User is already a member."

## 12. Tests & Verification Evidence
* `workspaces/tests.py`: 100% passing tests covering membership creation, RBAC checks, access requests, and seat calculations.

## 13. Known Limitations
* Multi-workspace aggregation requires switching context via the Master Dashboard.

## 14. Future Work
* Bulk CSV member invitation import.
