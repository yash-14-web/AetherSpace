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
* `templates/tasks/code_review_detail.html`: PR review detail screen.

## 6. URLs, Views, Services & Models
* **URLs**: `tasks/urls.py` (`task_list`, `task_detail`, `task_create`, `task_edit`, `task_status_update`, `code_review_submit`).
* **Views**: `tasks/views.py` (`task_list_view`, `task_detail_view`, `task_create_view`, `code_review_view`).
* **Models**: `Sprint`, `Task`, `Subtask`, `TaskActivity`, `TaskComment`, `TaskAttachment`, `CodeReviewRequest`.

## 7. Business Rules & Invariants
* Blueprint ID Rule: Task IDs must be exactly 6 numeric digits (e.g. `619347`). Naive random generation without collision handling is prohibited; `tasks.services.generate_unique_task_code()` checks database existence in a retry loop.
* Overdue tasks dynamically computed if `due_date < timezone.now().date()` and `status != DONE`.
* Task comments support both `USER` comments and `SYSTEM` event entries (`TASK_CREATED`, `BUG_ATTACHED`, `CODE_REVIEW_REQUESTED`).

## 8. Database Relationships
* `Task` belongs to `Workspace` (CASCADE).
* `Task` optionally belongs to `Sprint` (SET_NULL).
* `Task` has many `Subtask` (CASCADE).
* `Task` has many `TaskComment`, `TaskActivity`, `CodeReviewRequest` (CASCADE).
* `Task` has many linked `Bug` (SET_NULL).

## 9. API & WebSocket Interactions
* `POST /tasks/w/<slug>/<task_code>/status/`: Asynchronous status transition API.
* `POST /tasks/w/<slug>/<task_code>/subtask/toggle/`: Checkbox toggle API for subtasks.

## 10. Notifications & Integrations
* Dispatches `TASK_ASSIGNED`, `TASK_STATUS_CHANGED`, and `TASK_DUE_SOON` notifications.
* Integrated with `timetracking.TimeEntry` to record labor directly against `task_code`.

## 11. Error States & Edge Cases
* Submitting duplicate task code -> System regenerates until unique.
* Modifying task without membership -> `403 Forbidden`.
* Attempting to delete task without Admin role -> `403 Forbidden` with access request prompt.

## 12. Tests & Verification Evidence
* `tasks/tests.py`: Unit tests for task code generation, status transitions, subtask checklists, and code review requests.

## 13. Known Limitations
* Live drag-and-drop Kanban reordering is rendered server-side with Alpine.js optimistic updates.

## 14. Future Work
* Native GitHub webhook synchronization to auto-transition tasks when PRs are merged.
