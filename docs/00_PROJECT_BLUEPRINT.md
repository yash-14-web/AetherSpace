# AetherSpace Project Blueprint

## Product

AetherSpace is a small-team collaboration and agile workspace platform.

Target team size: 5--15 members.

Primary goal: centralize tasks, bugs, communication, files, meetings,
calendar activity, notifications, and workspace administration in one
clean interface.

## Main User Types

### Platform Admin

Controls the entire AetherSpace installation.

### Workspace Admin

Controls a particular workspace and its members/settings.

### Manager

Can be responsible for one or more workspaces and needs the Master
Dashboard.

### Contributor

Works on assigned tasks, bugs, files, chats, meetings, and calendar
items.

## Dashboard Model

### Master Dashboard

For managers working across multiple workspaces.

Show: - Total workspaces - Active tasks - Open bugs - Upcoming
meetings - Upcoming deadlines - Recent activity - Workspace health
summaries - My assigned work

### Workspace Dashboard

Scoped to one workspace.

Show: - Workspace summary - Active sprint/project status - Task
summary - Bug summary - Team members - Upcoming deadlines - Recent
activity - Quick actions

### Admin Dashboard

Platform-wide administration.

Show: - Users - Workspaces - Roles - System/application health - Storage
usage - Security status - Alerts - Recent administrative activity

Do not expose another workspace's private data to a normal workspace
member.

## Page Inventory

### Public/Auth

-   Landing
-   Login
-   Register / Accept Invitation
-   Forgot Password
-   Reset Password
-   Account Verification

### Dashboards

-   Master Dashboard
-   Workspace Dashboard
-   Admin Dashboard

### Workspace

-   Workspace Management
-   Team
-   Member Details
-   Project Details
-   Workspace Activity
-   Workspace Settings
-   Invite Members
-   Workspace Switcher

### Tasks

-   Task List
-   Task Board/Kanban
-   Task Details
-   Create Task
-   Edit Task
-   My Tasks
-   Task Activity
-   Task Search/Filters

### Bugs

-   Bug Dashboard
-   Bug List
-   Bug Details
-   Raise Bug
-   Edit Bug
-   My Bugs
-   Bug Activity
-   Bug Search/Filters

### Chat

-   Chat Home
-   Channel View
-   Direct Message
-   Create Channel
-   Channel Details
-   Pinned Assets
-   Shared Files

### Meetings

-   Meet Hub
-   Start Meeting
-   Join Meeting
-   Meeting Room
-   Schedule Meeting
-   Meeting Details
-   Meeting History

### Calendar

-   Calendar
-   Agenda
-   Create Event
-   Event Details
-   Upcoming Deadlines

Calendar items can reference: - Tasks - Bugs - Meetings - Milestones

### Files

-   Files Home
-   Folder View
-   File Details
-   Upload File
-   Recent Files
-   Shared Files

### Notifications

-   Notification Center
-   All
-   Unread
-   Tasks
-   Bugs
-   Mentions

### Profile

-   My Profile
-   Edit Profile
-   My Tasks
-   My Bugs
-   Activity
-   Workspace Roles

### Admin

-   User Management
-   User Details
-   Roles & Permissions
-   Invitations
-   Workspace Management
-   Workspace Requests
-   Member Management
-   Audit Logs
-   System Overview
-   Integrations
-   Storage & Files
-   Security
-   Backup & Restore
-   Activity Monitor
-   Performance
-   Alerts

### Settings

-   Account Settings
-   Profile Settings
-   Appearance
-   Notification Settings
-   Security
-   Workspace Settings
-   Integrations

### Error

-   400
-   403
-   404
-   500
