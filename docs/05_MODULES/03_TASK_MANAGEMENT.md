# Module 03: Task Management & Agile Sprints

## 1. Purpose
Provides agile backlog management, sprint execution, 6-digit task tracking (`######`), subtask checklists, and GitHub Pull Request code reviews (`CR-######`) for team initiatives.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `tasks/models.py`, `tasks/views.py`, `tasks/services.py`, `tasks/tests.py`.

## 3. Main User Workflows
1. **Task Creation**: Contributor or Manager creates a task. System auto-generates a unique 6-digit numeric ID (`task_code`, e.g. `619347`) with duplicate collision handling.
2. **Backlog to Sprint**: Manager assigns tasks to an active or planned `Sprint` with estimated hours.
3. **Task Execution & Kanban**: Tasks transition through the agile lifecycle:
   - `TODO` -> `IN_PROGRESS` -> `CODE_REVIEW` -> `TESTING` -> `DONE`.
4. **Subtasks & Checklist**: Contributors break complex tasks into ordered checklist items (`Subtask`) with completion progress percentages.
5. **Code Review Submission**: Developer submits PR review request (`CR-######`) with GitHub PR URL. Reviewer inspects and transitions status (`REQUESTED` -> `IN_REVIEW` -> `APPROVED` / `CHANGES_REQUESTED` -> `MERGED`).
6. **Defect Linking**: QA links existing defects (`B-######`) directly to the task or creates new linked bugs.

## 4. User Roles & Permissions
* **Workspace Admin & Manager**: Full control over all tasks, sprint planning, task reassignment, and deletion.
* **Workspace Contributor**: Can create tasks, edit tasks assigned to or reported by them, update subtasks, transition status, and log work hours. Task deletion requires a `GlobalAccessRequest` grant.

## 5. Pages & Templates
* `templates/tasks/task_list.html`: Sprint board and searchable task backlog.
* `templates/tasks/task_detail.html`: Full task view with subtasks, comments, activity stream, and linked bugs.
* `templates/tasks/task_form.html`: Create/edit task form.
* `templates/tasks/code_review_list.html`: Workspace-wide dedicated Code Review dashboard with status tabs and reviewer filtering.
* `templates/tasks/code_review_request_form.html`: Dedicated modal and standalone review request creation.
* `templates/tasks/code_review_detail.html`: Full 3-tab Code Review workspace screen (Overview, Comments & Decision, Activity & History).

## 6. URLs, Views, Services & Models
* **URLs**: `tasks/urls.py`:
  - `task_list`, `task_detail`, `task_create`, `task_edit`, `task_status_update`.
  - `code_review_list`, `code_review_request_workspace`, `code_review_detail`, `code_review_start`, `code_review_comment_add`, `code_review_decision`.
* **Views**: `tasks/views.py`:
  - `task_list_view`, `task_detail_view`, `task_create_view`.
  - `code_review_list_view`, `code_review_request_workspace_view`, `code_review_detail_view`, `code_review_start_view`, `code_review_comment_add_view`, `code_review_decision_view`.
* **Services**: `tasks/services.py`:
  - `create_code_review_request`, `update_code_review_status`, `submit_code_review_decision`.
* **Models**: `Sprint`, `Task`, `Subtask`, `TaskActivity`, `TaskComment`, `TaskAttachment`, `CodeReviewRequest`.

## 7. Business Rules & Invariants
* Blueprint ID Rule: Task IDs must be exactly 6 numeric digits (e.g. `619347`). Naive random generation without collision handling is prohibited; `tasks.services.generate_unique_task_code()` checks database existence in a retry loop.
* Code Review IDs: Generated using safe prefix `CR-######` (`generate_unique_review_code`).
* Overdue tasks dynamically computed if `due_date < timezone.now().date()` and `status != DONE`.
* Task comments support both `USER` comments and `SYSTEM` event entries (`TASK_CREATED`, `BUG_ATTACHED`, `CODE_REVIEW_REQUESTED`, `CODE_REVIEW_STATUS_CHANGED`).
* **Code Review Decision Governance (Phase 3)**:
  - Allowed decisions: `APPROVED`, `CHANGES_REQUESTED`, `REJECTED`.
  - Permissions: Only the assigned reviewer or a workspace Admin/Manager can record a formal decision.
  - Required Message: Non-empty rationale / feedback (minimum 3 characters) must accompany every decision.
  - Linked Task Invariant: A review approval does NOT automatically mark the linked task `DONE`; the author remains responsible for task completion.
  - Activity & History: Records a system audit event on the review, posts a decision comment to the review stream, and appends a `TaskActivity` entry to the parent task containing the review code, status, reviewer name, feedback, and action URL.
  - Notifications: Automatically dispatches in-app notification to the requester with direct deep-link to the review detail page (self-notifications suppressed).

## 8. Database Relationships
* `Task` belongs to `Workspace` (CASCADE).
* `Task` optionally belongs to `Sprint` (SET_NULL).
* `Task` has many `Subtask` (CASCADE).
* `Task` has many `TaskComment`, `TaskActivity`, `CodeReviewRequest` (CASCADE).
* `Task` has many linked `Bug` (SET_NULL).
* `CodeReviewRequest` links to `Task` (CASCADE), `requester` User (CASCADE), optional `reviewer` User (SET_NULL).

## 9. API & WebSocket Interactions
* `POST /tasks/w/<slug>/<task_code>/status/`: Asynchronous status transition API.
* `POST /tasks/w/<slug>/<task_code>/subtask/toggle/`: Checkbox toggle API for subtasks.
* `POST /tasks/w/<slug>/reviews/<review_code>/start/`: Review start lifecycle transition.
* `POST /tasks/w/<slug>/reviews/<review_code>/decision/`: Formal review decision submission endpoint.

## 10. Notifications & Integrations
* Dispatches `TASK_ASSIGNED`, `TASK_STATUS_CHANGED`, and `TASK_DUE_SOON` notifications.
* Dispatches `CODE_REVIEW_DECISION` notifications (`NotificationCategory.SYSTEM`, `NotificationType.INFO`) to review requester with deep link to review details.
* Integrated with `timetracking.TimeEntry` to record labor directly against `task_code`.

## 11. Error States & Edge Cases
* Submitting duplicate task code -> System regenerates until unique.
* Modifying task without membership -> `403 Forbidden`.
* Attempting to delete task without Admin role -> `403 Forbidden` with access request prompt.
* Submitting review decision without permission -> `PermissionDenied` (403 Forbidden).
* Submitting empty or short review message -> `ValidationError` (400 Bad Request with flash error).
* Submitting review decision on already finalized review -> `ValidationError` (status remains unchanged).

## 12. Tests & Verification Evidence
* `tasks/tests.py`: Unit tests for task code generation, status transitions, subtask checklists, and threaded comments / reactions (`TaskThreadedCommentsAndReactionsTests`).
* `tasks/test_code_reviews_phase1.py`: Unit tests for Code Review models, workspace listings, and request forms.
* `tasks/test_code_reviews_phase2.py`: Unit tests for Code Review 3-tab detail view and start lifecycle transitions.
* `tasks/test_code_reviews_phase3.py`: Comprehensive test suite (12 tests) for Code Review decisions, permissions, validations, linked task activity persistence, and notifications.
* **Comments & Threaded Discussions (T24 Refinement)**:
  - Live `@mention` autocomplete powered by Alpine.js and workspace membership directory with keyboard navigation (`ArrowUp`/`ArrowDown`/`Enter`/`Tab`/`Escape`), avatars, roles, and Contributor ID badges (`#####C`).
  - Canonical mention interpolation `@[Name](CID)` matching `render_rich_text` parser and notification dispatcher.
  - Interactive three-dot overflow menus on both system event banners and user comments with clipboard link copy, contextual event filtering, and permission-gated Edit/Delete.
  - Zero-overlap timeline layout utilizing flexbox `gap-3.5` preventing CSS margin inversion across sorting and filtering toggles.

## 13. Known Limitations
* Live drag-and-drop Kanban reordering is rendered server-side with Alpine.js optimistic updates.

## 14. Future Work
* Native GitHub webhook synchronization to auto-transition tasks when PRs are merged.

