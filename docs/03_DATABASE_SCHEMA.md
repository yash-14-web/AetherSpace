# AetherSpace Database Schema

Use UUID primary keys for internal relational identity where practical,
while maintaining human-facing Task/Bug IDs required by the product.

## Core

### User

-   id
-   email
-   password hash / Django auth fields
-   full_name
-   avatar
-   timezone
-   is_active
-   is_staff
-   is_superuser
-   created_at
-   updated_at

### UserProfile

-   user
-   bio
-   phone
-   headline
-   preferences

## Workspaces

### Workspace

-   id
-   name
-   slug
-   description
-   owner
-   status
-   created_at
-   updated_at

### WorkspaceMembership

-   id
-   workspace
-   user
-   role: ADMIN \| MANAGER \| CONTRIBUTOR
-   status
-   joined_at

Unique constraint: - workspace + user

## Tasks

### Task

-   id
-   task_code: six-digit human-facing identifier
-   workspace
-   title
-   description
-   status
-   priority
-   assignee
-   reporter
-   due_date
-   created_at
-   updated_at

Index: - workspace + status - workspace + priority - assignee + status -
task_code

### TaskActivity

-   task
-   actor
-   action
-   metadata
-   created_at

## Bugs

### Bug

-   id
-   bug_code: B-###### human-facing identifier
-   workspace
-   title
-   description
-   severity
-   status
-   environment
-   reporter
-   assignee
-   expected_result
-   actual_result
-   created_at
-   updated_at

### BugActivity

-   bug
-   actor
-   action
-   metadata
-   created_at

## Chat

### Channel

-   id
-   workspace
-   name
-   description
-   is_private
-   created_by
-   created_at

### ChannelMembership

-   channel
-   user
-   joined_at

### Message

-   id
-   channel nullable
-   sender
-   recipient nullable for DM
-   content
-   created_at
-   edited_at

### MessageAttachment

-   message
-   file

## Meetings

### Meeting

-   id
-   workspace
-   title
-   meeting_code
-   created_by
-   scheduled_start
-   scheduled_end
-   meeting_type
-   status
-   external_room_url

### MeetingParticipant

-   meeting
-   user
-   joined_at
-   left_at

## Calendar

### CalendarEvent

-   id
-   workspace
-   title
-   description
-   start_at
-   end_at
-   created_by
-   event_type
-   linked_task nullable
-   linked_bug nullable
-   linked_meeting nullable

## Files

### StoredFile

-   id
-   workspace
-   uploaded_by
-   original_name
-   storage_path
-   mime_type
-   size_bytes
-   checksum if practical
-   created_at

### Folder

-   id
-   workspace
-   parent nullable
-   name

## Notifications

### Notification

-   id
-   recipient
-   category
-   title
-   body
-   link
-   is_read
-   created_at

## Audit

### AuditLog

-   id
-   actor
-   workspace nullable
-   action
-   object_type
-   object_id
-   metadata
-   created_at

Index: - actor + created_at - workspace + created_at - action +
created_at

## Alerts

### SystemAlert

-   id
-   severity
-   category
-   message
-   source
-   status
-   created_at
-   resolved_at

Use application alerts, not expensive infrastructure monitoring.

## Storage Accounting

Track metadata and usage summaries in the application.

Do not repeatedly calculate the entire storage bucket for every page
request.
