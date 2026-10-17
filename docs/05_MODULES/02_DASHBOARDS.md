# Module 02: Dashboards (Master, Workspace, Admin)

## 1. Purpose
Provides high-altitude executive visibility and operational focus across three tiers:
1. **Master Dashboard**: Cross-workspace overview for managers and multi-team contributors.
2. **Workspace Dashboard**: Tactical cockpit for a single workspace (active sprint, burndown, assigned tasks, defects, meetings).
3. **Admin Dashboard**: System health, approval queues, storage metrics, and compliance logs.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `workspaces/views.py` (`master_dashboard_view`, `workspace_dashboard_view`), `admin_panel/views.py`.

## 3. Main User Workflows
1. **Master Dashboard (`/workspaces/dashboard/`)**:
   - Aggregates tasks, open bugs, and upcoming meetings across *all* workspaces the user belongs to.
   - Displays workspace quick-switcher cards with member count, storage usage, and active sprint progress.
2. **Workspace Dashboard (`/workspaces/w/<slug>/`)**:
   - Displays Active Sprint banner, progress percentage, and burndown metrics.
   - Lists "My Assigned Tasks" (TODO, In Progress, Code Review) with direct stopwatch triggers.
   - Lists "Critical Bugs" (Sev 1 / Sev 2) requiring immediate triage.
   - Shows "Today's Agenda & Meetings" and recent team channel activity.
3. **Admin Dashboard (`/admin-panel/`)**:
   - Executive statistics: total users, pending approvals, total workspaces, active call sessions, storage utilized.
   - Real-time audit log stream.

## 4. User Roles & Permissions
* **Platform Admin**: Full access to Admin Dashboard, Master Dashboard, and any workspace they join.
* **Workspace Manager**: Enjoys cross-workspace synthesis on the Master Dashboard and management controls on the Workspace Dashboard.
* **Contributor**: Sees personalized task lists, time logs, and schedule items scoped to their active memberships.

## 5. Pages & Templates
* `templates/workspaces/master_dashboard.html`: Cross-workspace cockpit.
* `templates/workspaces/workspace_dashboard.html`: Single workspace cockpit.
* `templates/admin_panel/dashboard.html`: Platform administrative console.

## 6. URLs, Views, Services & Models
* **URLs**: `/workspaces/dashboard/` -> `workspaces:master_dashboard`, `/workspaces/w/<slug>/` -> `workspaces:workspace_dashboard`, `/admin-panel/` -> `admin_panel:dashboard`.
* **Views**: `master_dashboard_view`, `workspace_dashboard_view` in `workspaces/views.py`.
* **Models Utilized**: `Workspace`, `Task`, `Bug`, `Meeting`, `TimeEntry`, `StoredFile`, `AuditLog`.

## 7. Business Rules & Invariants
* Master Dashboard strictly filters by `request.user`'s active `WorkspaceMembership` records; non-memberships are excluded.
* Metrics are computed via database aggregations (`Count`, `Sum`) to avoid N+1 query overhead.
* Blueprint Rule 18: Ordinary dashboard pages use vertically stacked section cards rather than cramped side-by-side grids.

## 8. Database Relationships
* Combines queries across `workspaces.Workspace`, `tasks.Task`, `bugs.Bug`, and `meetings.Meeting`.

## 9. API & WebSocket Interactions
* Real-time clock and live time tracking updates via Alpine.js timers.
* Incoming call modals operate universally across all dashboard pages via `GlobalCallConsumer`.

## 10. Notifications & Integrations
* Displays active unread notification badges in the universal header.

## 11. Error States & Edge Cases
* User with 0 workspaces -> Master Dashboard presents friendly empty state with "Create Workspace" or "Waiting for Invitation" prompt.
* Workspace with 0 active sprints -> Displays "No Active Sprint — Plan Sprint" card for managers.

## 12. Tests & Verification Evidence
* `workspaces/tests.py`: Master dashboard and workspace dashboard unit tests.
* `tests/e2e/test_workspace_dashboard_and_calendar.spec.ts`: E2E test suite.

## 13. Known Limitations
* Sprint burndown chart is currently rendered via clean SVG/CSS progress indicators rather than external JavaScript charting libraries.

## 14. Future Work
* Exportable sprint velocity and burndown reports in PDF/CSV format.
