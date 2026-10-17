# Module 11: Profile & People Directory

## 1. Purpose
Provides the team member directory, Contributor ID displays (`#####C`), live availability presence (Available, In Meeting, Offline), custom status messages, and hover card previews.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `accounts/models.py`, `accounts/views.py`, `workspaces/views.py`, `accounts/tests.py`.

## 3. Main User Workflows
1. **People Directory**: Team members inspect `/workspaces/w/<slug>/team/` to view active colleagues, functional roles (e.g. Frontend Engineer), role domain tags, and reporting relationships.
2. **Hover Card Previews**: Hovering over any avatar or Contributor ID badge opens an Alpine.js popover displaying the member's photo, Contributor ID, local timezone time, bio, and direct message trigger.
3. **Presence & Availability Status**:
   - Status choices: `available` (🟢), `in_meeting` (🟡), `offline` (⚪).
   - Setting a status message (e.g. "Focus time until 3pm") with an optional expiration timestamp.
   - Cache heartbeat: `cache.get(f'user_last_seen_{user.id}')` determines true online/offline presence.
4. **Profile Customization**: Users update full name, headline, bio, phone, avatar (Supabase upload or preset), and profile banner.

## 4. User Roles & Permissions
* **Workspace Admin**: Can reassign member reporting structures and update functional roles in the workspace directory.
* **All Users**: Can view member directory within their workspaces and update their own personal profile.

## 5. Pages & Templates
* `templates/accounts/profile_detail.html`: Full personal profile view.
* `templates/accounts/profile_edit.html`: Profile and avatar editing screen.
* `templates/workspaces/workspace_members.html`: Team member directory with functional hierarchy.
* `templates/components/user_hover_card.html`: Reusable hover card component.

## 6. URLs, Views, Services & Models
* **URLs**: `accounts/urls.py` (`profile_detail`, `profile_edit`, `user_status_update`).
* **Views**: `accounts/views.py` (`profile_detail_view`, `profile_edit_view`, `update_presence_api`).
* **Models**: `accounts.User`, `accounts.UserProfile`, `workspaces.WorkspaceMembership`.

## 7. Business Rules & Invariants
* Contributor ID Preservation: The Contributor ID (`#####C`) is immutable once generated to maintain permanent identity integrity.
* Presence Expiration: If a custom status has a `status_expires_at` timestamp in the past, `availability_status` automatically reverts to `available`.
* Online Heartbeat Threshold: In production, users without a cache heartbeat within the last 5 minutes resolve to `offline`.

## 8. Database Relationships
* `User` has one `UserProfile` (CASCADE).
* `User` has many `WorkspaceMembership` (CASCADE).

## 9. API & WebSocket Interactions
* `POST /auth/api/presence/status/`: Asynchronous status update API.
* Presence changes broadcast to connected team channels via Channels group relays.

## 10. Notifications & Integrations
* Integrated with Chat, Meetings, Tasks, and Calendar as the standard identity badge.

## 11. Error States & Edge Cases
* Viewing profile of user in another workspace -> Blocked by `@workspace_member_required` to maintain workspace privacy.
* Uploading avatar larger than 5 MB -> Validation error: "Avatar image must be under 5 MB."

## 12. Tests & Verification Evidence
* `accounts/tests.py`: Unit tests for Contributor ID generation, full name display, profile presence logic, and preference serialization.

## 13. Known Limitations
* Live typing presence is currently scoped to individual Chat channels rather than platform-wide.

## 14. Future Work
* Native Slack-style do-not-disturb (DND) schedules with automated notification silencing.
