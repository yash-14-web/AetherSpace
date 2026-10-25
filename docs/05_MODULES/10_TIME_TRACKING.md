# Module 10: Time Tracking & Sprint Labor

## 1. Purpose
Provides real-time work stopwatches, glowing circular SVG timer cockpit, start/end time duration calculation, manual effort logging, category attribution, defect/bug linking, labor tracking against 6-digit tasks (`######`) and defects (`B-######`), and sprint labor accumulation analytics.

## 2. Implementation Status
* **Status**: **Implemented, Redesigned, Usability Refined, Defect-Resolved & 100% E2E Verified**
* **Evidence**:
  - Models: `timetracking/models.py` (9 work categories, linked defect parsing via `linked_bug_code`, entry source distinction `TIMER` vs `MANUAL`, clean description, billable detection, category badge color mapping)
  - Views: `timetracking/views.py` (`workspace_timesheet` with batch pre-fetched `WorkspaceMembership` to avoid N+1 queries, day-by-day navigation offset, available tasks/defects; `manual_time_entry`; `edit_time_entry`; `api_timer_start` with defect parsing and `Bug Fix` category tagging; `api_timer_status`; `api_timer_pause`; `api_timer_resume`; `api_timer_stop`; `export_timesheet_csv`)
  - Forms: `timetracking/forms.py` (`ManualTimeEntryForm` with 9 explicit categories, workspace-scoped defect code validation, auto-calculated duration from start/end times and overnight rollover handling)
  - Template: `templates/timetracking/timesheet.html` (in-flow non-overlapping task/defect selector with quick search, glowing circular timer, dedicated "Detailed Day View" banner with Prev/Next day navigation, `#timesheet-section` anchoring, safe `.rich-text-content` with unwrapped multi-line lists, teleported contributor hover cards)
  - CSS: `static/css/src/input.css` & `static/css/dist/styles.css` (explicit `list-style-type: disc !important` and `decimal !important`, display `list-item`, and margin/padding indentation for `.rich-text-content`, `.aether-chat-editor`, `.chat-bubble`, `.aether-message-content`)
  - Unit Tests: `timetracking/tests.py` (24 tests passing, 100% OK)
  - E2E Tests: `tests/e2e/timetracking_redesign.spec.ts` (11 Playwright tests passing, 100% OK)
  - Visual Verification Artifacts: `defect1_active_timer_task_selector_inflow.png`, `defect2_work_item_and_entry_source.png`, `defect3_view_day_banner_and_nav.png`, `defect4_rich_text_lists_preview.png`

## 3. Main User Workflows
1. **Live Circular Stopwatch Timer & Options Menu**:
   - Contributor selects task or works under General Workspace Activity.
   - Live glowing SVG circular timer ring with monospace `00:00:00` display and `HOURS : MINS : SECS` label.
   - States: Ready (`idle`), `Running` (with pulsing indicator), and `Paused`.
   - Controls: Start, Pause, Resume, Stop, and Switch Task.
   - Active Timer Header Three-Dot Options Dropdown:
     - `Log Time Manually`: opens the manual entry modal.
     - `Select / Switch Task`: activates the inline task selector dropdown.
     - `Clear Task Selection`: resets selection to General Workspace Activity.
     - `Stop Active Timer`: stops the current running/paused timer.
   - Vertical dead space beneath timer card removed for compact, balanced layout.
   - State persists across page reloads via server-backed session timers.
2. **Log Time Manually Modal**:
   - Elevated dark modal with date picker, start time (e.g. `09:00 AM`), and end time (e.g. `11:30 AM`).
   - Dynamic real-time duration computation (e.g. `2h 30m`).
   - Work Item dropdown segmented by:
     - General Workspace Activity
     - Active Tasks (`#TASK-CODE — Title`)
     - Defects / Bugs (`B-###### — Title`) strictly scoped to current workspace.
   - 9 Work Type Categories:
     - `🔵 Task / Development`
     - `🔴 Bug Fix`
     - `🌐 Documentation`
     - `👥 Meeting`
     - `🔬 Research`
     - `🟡 Code Review`
     - `🟣 Design`
     - `⚡ API Integration`
     - `⚪ Other`
   - Work Description editor with full markdown formatting toolbar:
     - `H` (Heading)
     - `B` (Bold)
     - `I` (Italic)
     - `🔗` (Link)
     - `≡` (Bulleted List)
     - `1.` (Numbered List)
     - `<>` (Inline Code)
     - `</>` (Code Block)
   - Cursor-preserving and placeholder-selection logic when inserting markdown formatting.
   - Live `x/1000` character counter.
   - Live Markdown Preview toggle rendering sanitized HTML.
   - `[ ] Mark as billable (if applicable)` checkbox.
3. **Today's Timeline & Weekly Overview**:
   - Dynamic 9:00–17:00 timeline axis plotting color-coded session pills throughout the day.
   - "View Day" functional header link filtering timesheet to `?date_range=today`.
   - 7-day bar chart showing daily hours logged across the current week, highlighting today in solid AetherSpace blue.
4. **Timesheet History Table**:
   - Columns:
     - Date & Time
     - Work Item (Task `#######`, Defect `B-######`, or General Workspace Effort)
     - Category badge (colored dot and background)
     - Entry Source pill (`⏱️ Timer Entry` vs `📝 Manual Entry`)
     - Project & Sprint
     - Description (Safe rich-text rendered via `core/templatetags/rich_text.py`)
     - Duration
     - Contributor (Reusable `people_hover_card.html` with teleported card, profile picture, contributor ID, roles, and status)
     - Actions (Edit / Delete)
   - Filter pills: `Today`, `This Week`, `This Month`, `All Time`.
   - Multi-dimensional filters: Project dropdown, Task dropdown, Member dropdown (for Admins/Managers), and free-text search.
5. **Editing Time Entries**:
   - Secure server-side authorization check (`edit_time_entry`): author or Admin/Manager can edit task, defect code, category, description, start/end time, and duration.
6. **CSV Export**:
   - Exports Date, Contributor Name, Contributor ID, Project, Sprint, Task / Work Item, Defect Code, Category, Entry Source, Description, Duration (HH:MM), Duration (Hours), Billable.

## 4. User Roles & Permissions
* **Workspace Admin & Manager**: Inspect team aggregate metrics (`Workspace Team` card), filter by any member, edit any entry, and export timesheet CSV.
* **Workspace Contributor**: Start/pause/stop live timers, create manual time entries, and edit/delete their own time records.

## 5. Pages & Templates
* `templates/timetracking/timesheet.html`: Comprehensive dashboard cockpit matching the approved mockups.
* `templates/components/people_hover_card.html`: Teleported contributor profile hover card.
* `templates/components/header.html`: Active global header timer indicator.

## 6. URLs, Views, Services & Models
* **URLs**: `timetracking/urls.py`:
  - `w/<slug>/`: `workspace_timesheet`
  - `w/<slug>/manual/`: `manual_time_entry`
  - `w/<slug>/edit/<uuid>/`: `edit_time_entry`
  - `w/<slug>/delete/<uuid>/`: `delete_time_entry`
  - `w/<slug>/timer/<action>/`: `api_timer_*`
  - `w/<slug>/export/`: `export_timesheet_csv`

## 7. Business Rules & Invariants
* Single Running Timer Rule: Starting a new timer automatically manages existing active timer sessions for the user.
* Accurate Pause Invariant: Pausing preserves `accumulated_seconds` without active drift.
* Strict Workspace Isolation: Time entries and associated defects are strictly scoped by workspace foreign key.
* Non-invasive Encoded Metadata: Tags like `[Category]`, `[Bug: B-######]`, and `[Billable]` encode inside the description field, preserving zero remote database schema disruptions.
* Safe Rich Text Sanitization: Bleach-based whitelist sanitizes user descriptions to prevent XSS attacks while allowing headings, bold, italics, code, and lists.
* Zero Table Clipping: Contributor hover cards use `<template x-teleport="body">` with floating fixed coordinates to guarantee cards are never clipped by table boundaries.
* Zero N+1 Queries: `WorkspaceMembership` is batch pre-fetched for all log page authors in `workspace_timesheet`.

## 8. Tests & Verification Evidence
* `timetracking/tests.py`: 24 Django unit tests covering timer lifecycle, start/end time manual duration calculation, defect association, 9 categories validation, entry source distinction (`⏱️ Timer Entry` vs `📝 Manual Entry`), safe rich text rendering, membership pre-fetching, authorized editing, unauthorized edit protection, View Day banner filtering, and bullet/numbered list rich text rendering (100% OK, 24/24 passing).
* `tests/e2e/timetracking_redesign.spec.ts`: 11 automated Playwright browser tests verifying dashboard rendering, three-dot options menu, functional navigation links, modal duration calculations, bug defect selection, 9 categories, markdown toolbar with preview, source pills, hover cards, timer persistence, mobile responsiveness, dark/light modes, active timer in-flow task selector without overlap, View Day banner and day navigation, and timesheet rich-text list styling (100% OK, 11/11 passing).
* `tests/e2e/chat/chat_rich_text_lists.spec.ts`: 2 Playwright browser tests verifying composer bullet and numbered lists, continuation on Enter, nested indent/outdent with Tab/Shift+Tab, and post-reload persistence (100% OK, 2/2 passing).

