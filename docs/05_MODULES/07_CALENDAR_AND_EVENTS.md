# Module 07: Calendar & Events

## 1. Purpose
Provides time-based operational coordination, standalone calendar events, team milestones, work sessions, formatted agendas, and cross-entity scheduling linked directly to Tasks, Bugs, and Meetings.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `calendars/models.py`, `calendars/views.py`, `calendars/tests.py`.

## 3. Main User Workflows
1. **Event Creation**: User schedules an event:
   - Event Types: `MEETING`, `MILESTONE`, `TASK_DEADLINE`, `WORK_SESSION`, `GENERAL`.
   - Category: `WORKSPACE` (team-wide) or `PERSONAL` (private to user).
   - Timing: Start date/time, end date/time, or `is_all_day = True`.
   - Recurrence: `NONE`, `DAILY`, `WEEKLY`, `MONTHLY`.
2. **Cross-Entity Linking**: Organizers optionally attach:
   - Linked Task (`tasks.Task`): Shows task code and due date.
   - Linked Bug (`bugs.Bug`): Shows defect code and severity.
   - Linked Meeting (`meetings.Meeting`): Provides direct "Join Call" launch button.
3. **Agenda & Resources**: Formatted agenda text and structured reference links (`[{'title': '...', 'url': '...'}]`).
4. **Attendee Management**: Invite team members (`CalendarEventAttendee`); invitees RSVP as `ACCEPTED`, `DECLINED`, or `TENTATIVE`.

## 4. User Roles & Permissions
* **Workspace Admin & Manager**: Can create workspace-wide events, milestones, and edit any event.
* **Workspace Contributor**: Can create personal events and workspace work sessions, invite peers, and RSVP to invitations.

## 5. Pages & Templates
* `templates/calendars/calendar_month.html`: Full month calendar grid with day cells, event badges, and filter toggles.
* `templates/calendars/calendar_week.html`: Time-blocked weekly schedule view.
* `templates/calendars/calendar_day.html`: Granular daily agenda schedule.
* `templates/calendars/event_detail.html`: Event cockpit with agenda, attendee list, linked task/bug cards, and attachments.
* `templates/calendars/event_form.html`: Event creation/editing modal and form.

## 6. URLs, Views, Services & Models
* **URLs**: `calendars/urls.py` (`calendar_month`, `calendar_week`, `calendar_day`, `event_detail`, `event_create`, `event_rsvp`).
* **Views**: `calendars/views.py` (`calendar_month_view`, `event_detail_view`, `event_rsvp_api`).
* **Models**: `CalendarEvent`, `CalendarEventAttendee`, `CalendarEventAttachment`.

## 7. Business Rules & Invariants
* End Time Validation: `clean()` ensures `end_at >= start_at`.
* Live Now Indicator: `is_live_now` property evaluates `start_at <= timezone.now() <= end_at`.
* Workspace Isolation: Events, tasks, and bugs linked together must belong to the same workspace.

## 8. Database Relationships
* `CalendarEvent` belongs to `Workspace` (CASCADE).
* `CalendarEvent` optionally links to `tasks.Task`, `bugs.Bug`, `meetings.Meeting` (SET_NULL).
* `CalendarEvent` has many `CalendarEventAttendee` (CASCADE).
* `CalendarEvent` has many `CalendarEventAttachment` (CASCADE).

## 9. API & WebSocket Interactions
* `POST /calendar/w/<slug>/events/<id>/rsvp/`: Fast asynchronous RSVP API.

## 10. Notifications & Integrations
* Dispatches `MEETING_INVITE` / event notification to newly added attendees.
* Synchronizes with Dashboard "Today's Schedule" widget.

## 11. Error States & Edge Cases
* End time before start time -> Form validation error: "End time cannot precede start time."
* Deleting linked task -> Event retains its record; `linked_task` is set to NULL.

## 12. Tests & Verification Evidence
* `calendars/tests.py`: Unit tests for event lifecycle, attendee RSVP transitions, and cross-entity linkages.

## 13. Known Limitations
* External iCal / Google Calendar two-way synchronization is not currently connected.

## 14. Future Work
* Exportable `.ics` calendar subscription feeds.
