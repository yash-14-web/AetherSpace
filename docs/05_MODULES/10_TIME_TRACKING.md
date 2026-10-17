# Module 10: Time Tracking & Sprint Labor

## 1. Purpose
Provides real-time work stopwatches, manual time logging, labor attribution against 6-digit tasks (`######`), and sprint labor accumulation analytics.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `timetracking/models.py`, `timetracking/views.py`, `timetracking/tests.py`.

## 3. Main User Workflows
1. **Live Stopwatch Timer**: Contributor clicks "Start Timer" on a task card or in the Time Tracking navigation rail:
   - System creates a `TimeEntry` with `is_running = True`, `status = RUNNING`.
   - Running stopwatch ticks live in the header using Alpine.js.
2. **Pausing & Resuming**: Contributor can pause timer (`pause()`) during standups or breaks, preserving `accumulated_seconds` without finalizing. Resuming starts a new running interval.
3. **Stopping & Finalizing**: Clicking "Stop Timer" finalizes elapsed duration (`duration_seconds`), computes human-readable hours/minutes, and sets `status = COMPLETED`.
4. **Manual Time Logging**: Contributors can log work retroactively by specifying date, task code, duration (hours/minutes), and an activity description.
5. **Sprint Labor Breakdown**: Managers inspect total accumulated hours per task, sprint, and contributor.

## 4. User Roles & Permissions
* **Workspace Admin & Manager**: Can inspect time logs for all members across sprints and export timesheet data.
* **Workspace Contributor**: Can start/stop timers, create manual entries, and edit/delete their own time records.

## 5. Pages & Templates
* `templates/timetracking/timetracking_dashboard.html`: Main time tracking cockpit with live timer banner, weekly summary chart, and recent entries table.
* `templates/timetracking/manual_entry_modal.html`: Manual work log modal.
* `templates/components/header.html`: Active running stopwatch widget.

## 6. URLs, Views, Services & Models
* **URLs**: `timetracking/urls.py` (`time_dashboard`, `start_timer`, `pause_timer`, `resume_timer`, `stop_timer`, `manual_entry`).
* **Views**: `timetracking/views.py` (`time_dashboard_view`, `timer_action_api`, `manual_entry_view`).
* **Models**: `TimeEntry`.

## 7. Business Rules & Invariants
* Single Running Timer Rule: Starting a new timer automatically pauses or completes any previously active running timer for that user.
* Accurate Pause Invariant: Pausing freezes `accumulated_seconds`; resuming sets `last_resumed_at = timezone.now()` to ensure paused intervals are never billed as active work.
* Workspace Isolation: Time entries are strictly scoped to `workspace`.

## 8. Database Relationships
* `TimeEntry` belongs to `workspaces.Workspace` (CASCADE).
* `TimeEntry` belongs to `accounts.User` (CASCADE).
* `TimeEntry` optionally references `tasks.Task` (SET_NULL, related_name='time_entries').

## 9. API & WebSocket Interactions
* `POST /timetracking/w/<slug>/api/timer/<action>/`: Handles `start`, `pause`, `resume`, `stop` via JSON fetch.
* `current_duration_seconds` dynamically calculated on server or client without rounding drift.

## 10. Notifications & Integrations
* Aggregates total logged hours into parent `tasks.Task` properties (`total_logged_seconds`, `total_logged_hours_display`).

## 11. Error States & Edge Cases
* Logging time against non-existent task code -> `ValidationError: "Task code not found in this workspace."`
* Stopping an already completed timer -> Safe no-op returning current duration.

## 12. Tests & Verification Evidence
* `timetracking/tests.py`: Unit tests for live timer start/pause/resume/stop lifecycle, accumulated seconds accuracy, and manual entry logging.

## 13. Known Limitations
* Automatic idle-time detection (detecting when user walks away from keyboard) is not enabled; relies on manual pause/stop.

## 14. Future Work
* Timesheet CSV and payroll export capabilities for contractors and freelancers.
