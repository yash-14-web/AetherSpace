# Module 09: Notifications & Email Audit

## 1. Purpose
Provides real-time cross-module event alerts, unread badge counters, actionable navigation links, and outbound email delivery auditing.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `notifications/models.py`, `notifications/services.py`, `notifications/views.py`, `notifications/tests.py`.

## 3. Main User Workflows
1. **Event Trigger**: Actions across AetherSpace automatically generate notifications:
   - Task assigned or status changed.
   - Bug assigned or prioritized.
   - Chat mention (@user) or DM received.
   - Meeting scheduled or call ringing.
   - File shared or workspace invitation sent.
2. **Universal Header Alert**: User sees unread badge count in the universal top header. Clicking the bell opens the notifications drawer.
3. **Actionable Navigation**: User clicks a notification card; system marks it as read and redirects immediately to the relevant resource (`action_url`).
4. **Mark All Read / Filter**: Users can filter by category (Task, Bug, Mention, Meeting, File, System) or click "Mark All as Read".
5. **Email Delivery**: Critical events dispatch background emails, recording full delivery status in `EmailDeliveryLog`.

## 4. User Roles & Permissions
* **All Authenticated Users**: Can view, filter, and mark their own notifications as read.
* **Platform Admin**: Can inspect platform-wide `EmailDeliveryLog` records in the Admin Panel to diagnose failed delivery attempts.

## 5. Pages & Templates
* `templates/notifications/notification_list.html`: Full notifications center with category tabs.
* `templates/components/header.html`: Universal top bar notification popover dropdown.
* `templates/admin_panel/email_logs.html`: Admin email delivery audit table.

## 6. URLs, Views, Services & Models
* **URLs**: `notifications/urls.py` (`notification_list`, `mark_as_read`, `mark_all_read`).
* **Views**: `notifications/views.py` (`notification_list_view`, `mark_as_read_api`).
* **Services**: `notifications/services.py` (`create_notification()`, `dispatch_email_notification()`).
* **Models**: `Notification`, `EmailDeliveryLog`.

## 7. Business Rules & Invariants
* Self-Notification Suppression: Users never receive notifications for actions they perform themselves (e.g. assigning a task to oneself).
* Safe Action URLs: `action_url` values are strictly relative paths or verified domain routes to prevent open-redirect vulnerabilities.
* Email Delivery Auditing: `EmailDeliveryLog` records timestamps, event types, recipient emails, and delivery status (`SENT`, `FAILED`, `SUPPRESSED`) without logging sensitive passwords or tokens.

## 8. Database Relationships
* `Notification` belongs to recipient `accounts.User` (CASCADE).
* `Notification` optionally references actor `accounts.User` (SET_NULL) and `workspaces.Workspace` (CASCADE).

## 9. API & WebSocket Interactions
* `POST /notifications/api/<id>/read/`: Asynchronous mark-as-read API.
* `POST /notifications/api/mark-all-read/`: Batch update API.

## 10. Notifications & Integrations
* Listens to model signals and service methods across Tasks, Bugs, Meetings, Chat, and Files.

## 11. Error States & Edge Cases
* Marking someone else's notification as read -> `403 Forbidden`.
* Disconnected SMTP host -> Catches exception, sets `EmailDeliveryLog.status = FAILED`, and records sanitized error message without crashing the user's request.

## 12. Tests & Verification Evidence
* `notifications/tests.py`: Unit tests for notification creation, self-notification suppression, category filtering, and email audit logging.

## 13. Known Limitations
* Push notifications via browser Web Push API (Service Workers) are not currently enabled; notifications rely on in-app alerts and email.

## 14. Future Work
* Native Web Push API integration for desktop and mobile browsers.
