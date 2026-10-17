# Module 04: Bug Management & Defect Triage

## 1. Purpose
Provides defect tracking, severity triage, reproduction steps documentation, environment logging, and bi-directional linkage with agile tasks.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `bugs/models.py`, `bugs/views.py`, `bugs/services.py`, `bugs/tests.py`.

## 3. Main User Workflows
1. **Defect Raising**: Contributor or QA engineer clicks "Raise Bug".
2. **Identification & Severity**: System assigns collision-safe ID with `B-` prefix and 6 digits (e.g. `B-882316`). Reporter specifies:
   - Severity: `SEV1 - Blocker`, `SEV2 - Major`, `SEV3 - Moderate`, `SEV4 - Minor`.
   - Environment: `PRODUCTION`, `STAGING`, `DEVELOPMENT`, `QA`.
   - Subsystem Module: Selects from `workspaces.WorkspaceModule`.
   - Repro Steps, Expected Result, Actual Result, Browser/Device details.
3. **Task Linkage**: Reporter optionally binds the bug to a parent story/task (`tasks.Task`).
4. **Triage & Resolution**: Engineers triage defect:
   - `OPEN` -> `IN_PROGRESS` -> `RESOLVED` -> `CLOSED`.
5. **Activity & Comments**: Every status change, assignment update, and comment is logged to `BugActivity` and `BugComment`.

## 4. User Roles & Permissions
* **Workspace Admin & Manager**: Can reassign, reprioritize, close, or delete any bug in the workspace.
* **Workspace Contributor**: Can raise bugs, comment, attach files, and resolve bugs assigned to them. Deletion requires an access grant.

## 5. Pages & Templates
* `templates/bugs/bug_list.html`: Searchable and filterable defect register with Sev 1/2 highlight banners.
* `templates/bugs/bug_detail.html`: Defect cockpit with repro steps, linked task card, comments, and attachments.
* `templates/bugs/bug_form.html`: Defect intake form.

## 6. URLs, Views, Services & Models
* **URLs**: `bugs/urls.py` (`bug_list`, `bug_detail`, `bug_create`, `bug_edit`, `bug_status_update`).
* **Views**: `bugs/views.py` (`bug_list_view`, `bug_detail_view`, `bug_create_view`).
* **Models**: `Bug`, `BugActivity`, `BugComment`, `BugAttachment`.

## 7. Business Rules & Invariants
* Blueprint ID Rule: Bug IDs must start with `B-` followed by 6 numeric digits (e.g. `B-882316`). Implemented in `bugs.services.generate_unique_bug_code()`.
* Workspace Integrity: Model `clean()` strictly validates that `module` and `linked_task` belong to the exact same workspace as the bug.
* Severity Badging: Sev 1 (Blocker) bugs trigger red attention styling across dashboard cards.

## 8. Database Relationships
* `Bug` belongs to `Workspace` (CASCADE).
* `Bug` optionally references `tasks.Task` (SET_NULL, related_name='bugs').
* `Bug` optionally references `workspaces.WorkspaceModule` (SET_NULL, related_name='bugs').
* `Bug` has many `BugComment`, `BugActivity`, `BugAttachment` (CASCADE).

## 9. API & WebSocket Interactions
* `POST /bugs/w/<slug>/<bug_code>/status/`: Asynchronous status transition API.
* File upload integration streams screenshots directly to Supabase Cloud Storage.

## 10. Notifications & Integrations
* Dispatches `BUG_REPORTED`, `BUG_ASSIGNED`, and `BUG_STATUS_CHANGED` notifications.
* Defect resolution posts automatic system comments back to linked `tasks.Task`.

## 11. Error States & Edge Cases
* Submitting bug with module from another workspace -> `ValidationError: "Selected module does not belong to this workspace."`
* Accessing non-existent bug code -> `404 Not Found`.

## 12. Tests & Verification Evidence
* `bugs/tests.py`: Comprehensive test suite verifying B-prefix generation, status transitions, workspace cross-entity validation, and activity logging.

## 13. Known Limitations
* Automated stack-trace parsing from external error trackers is not currently connected.

## 14. Future Work
* Sentry / crash-report webhook ingestion to automatically generate draft defect records.
