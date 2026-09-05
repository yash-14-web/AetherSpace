# AetherSpace — Design Reference

## Purpose
This file explains what each AetherSpace design image represents and tells Antigravity how to use the image when implementing the corresponding page.

**Implementation rule:** Before building a page, find its matching image in the design folder. Treat the approved image as the primary visual reference for layout, spacing, typography, navigation, cards, controls, hierarchy, theme, and responsive intent. Do not invent a substantially different UI when a reference exists.

---

## Core Pages

### 01 — AetherSpace Dark SaaS Workspace Landing Page
**Image:** `AetherSpace Dark SaaS Workspace Landing Page.png`  
**Page:** Landing Page  
**Purpose:** Public-facing introduction to AetherSpace before authentication.  
**Users:** Visitors / prospective users.  
**Implementation:** Recreate the approved branding, hero, navigation, typography, CTA hierarchy, spacing, and overall visual identity.

### 02 — AetherSpace Master Dashboard
**Page:** Master Dashboard  
**Users:** Managers.  
**Purpose:** Cross-workspace overview for managers involved in one or more projects.  
**Implementation:** Use the reference for global navigation, workspace/project overview, stacked cards, metrics, activity, and actions.

### 03 — AetherSpace Workspace Dashboard
**Page:** Workspace Dashboard  
**Users:** Authorized workspace members.  
**Purpose:** Project/workspace-scoped daily overview.  
**Implementation:** Recreate workspace context, project information, tasks, bugs, activity, team information, and workspace navigation.

### 04 — AetherSpace Admin Dashboard
**Page:** Admin Dashboard  
**Users:** Platform administrators.  
**Purpose:** System-level administration and health overview.  
**Implementation:** Follow the reference for administrative statistics, health/status information, actions, and navigation.

---

# Authentication

### 05 — AetherSpace Login
**Page:** Login  
**Purpose:** Authenticate an existing user.  
**Users:** Registered users.

### 06 — AetherSpace Register Accept Invitation
**Page:** Register / Accept Invitation  
**Purpose:** Allow an invited member to create/activate an account.  
**Users:** Invited team members.

### 07 — AetherSpace Forgot Password
**Page:** Forgot Password  
**Purpose:** Start password recovery.

### 08 — AetherSpace Reset Password
**Page:** Reset Password  
**Purpose:** Set a new password after recovery.

### 09 — AetherSpace Account Verification
**Page:** Account Verification  
**Purpose:** Confirm an account/email when required.

For all authentication pages, preserve the approved AetherSpace branding, form hierarchy, spacing, feedback states, and dual-theme system.

---

# Workspace Management

### 10 — AetherSpace Workspace Management
**Page:** Workspace Management  
**Purpose:** Create, view, configure, and manage workspaces.  
**Users:** Authorized managers/admins.

---

# Task Management

### 11 — AetherSpace Task List
**Page:** Task List  
**Purpose:** Structured task list.  
**Key rule:** Tasks use standardized 6-digit IDs such as `619347`.

### 12 — AetherSpace Task Board Kanban
**Page:** Task Board / Kanban  
**Purpose:** Visual task workflow management.

### 13 — AetherSpace Task Details
**Page:** Task Details  
**Purpose:** Complete task view including ID, title, priority, status, assignee, description, dates, attachments, and activity.

### 14 — AetherSpace Create Task
**Page:** Create Task  
**Purpose:** Create a new task.

### 15 — AetherSpace Edit Task
**Page:** Edit Task  
**Purpose:** Update an existing task.

### 16 — AetherSpace My Tasks
**Page:** My Tasks  
**Purpose:** Tasks assigned to the current user.

### 17 — AetherSpace Task Activity
**Page:** Task Activity  
**Purpose:** Chronological text-based task history.  
**Rule:** Do not introduce radar/graph charts.

### 18 — AetherSpace Task Search Filters
**Page:** Task Search & Filters  
**Purpose:** Search and filter tasks efficiently.

---

# Bug Management

### 19 — AetherSpace Bug Dashboard
**Page:** Bug Dashboard  
**Purpose:** Overview of bugs, severity, status, and activity.

### 20 — AetherSpace Bug List
**Page:** Bug List  
**Purpose:** Structured bug list.  
**Key rule:** Bugs use IDs such as `B-882316`.

### 21 — AetherSpace Bug Details
**Page:** Bug Details  
**Purpose:** Complete bug information, severity, environment, reproduction information, attachments, and activity.

### 22 — AetherSpace Raise Bug
**Page:** Raise Bug  
**Purpose:** Create a bug report.  
**Requirements:** Auto-generated 6-digit bug key, rich Markdown reproduction steps, Dev/Staging/Prod environment selector, and attachment upload.

### 23 — AetherSpace Edit Bug
**Page:** Edit Bug  
**Purpose:** Update an existing bug.

### 24 — AetherSpace My Bugs
**Page:** My Bugs  
**Purpose:** Bugs relevant to the current user.

### 25 — AetherSpace Bug Activity
**Page:** Bug Activity  
**Purpose:** Chronological text-based bug history.

### 26 — AetherSpace Bug Search Filters
**Page:** Bug Search & Filters  
**Purpose:** Search and filter bugs.

---

# Chat

### 27 — AetherSpace Chat Home
**Page:** Chat Home  
**Purpose:** Main team communication view.

### 28 — AetherSpace Channel View
**Page:** Channel View  
**Purpose:** Group communication such as `#smart-classroom-dev`.

### 29 — AetherSpace Direct Message
**Page:** Direct Message  
**Purpose:** One-to-one communication, with audio/video actions where supported.

### 30 — AetherSpace Create Channel
**Page:** Create Channel  
**Purpose:** Create a team channel.

### 31 — AetherSpace Channel Details
**Page:** Channel Details  
**Purpose:** Channel information, members, and settings.

### 32 — AetherSpace Pinned Assets
**Page:** Pinned Assets  
**Purpose:** Quick access to pinned messages/assets/documents.

### 33 — AetherSpace Shared Files
**Page:** Shared Files  
**Purpose:** Files shared through chat.

---

# Meet Hub

### 34 — AetherSpace Meet Hub
**Page:** Meet Hub  
**Purpose:** Central meeting launcher and management view.

### 35 — AetherSpace Start Meeting
**Page:** Start Meeting  
**Purpose:** Start an instant meeting.

### 36 — AetherSpace Join Meeting
**Page:** Join Meeting  
**Purpose:** Join using a code such as `meet-xxxx-xxxx`.

### 37 — AetherSpace Meeting Room
**Page:** Meeting Room  
**Purpose:** Active audio/video meeting interface.  
**Implementation:** Preserve the reference UI while integrating WebRTC/Jitsi behavior.

### 38 — AetherSpace Schedule Meeting
**Page:** Schedule Meeting  
**Purpose:** Schedule a future meeting and connect it to Calendar.

### 39 — AetherSpace Meeting Details
**Page:** Meeting Details  
**Purpose:** Meeting information, participants, time, and workspace context.

### 40 — AetherSpace Meeting History
**Page:** Meeting History  
**Purpose:** Chronological previous-meeting record.

---

# Calendar

### 41 — AetherSpace Calendar
**Page:** Calendar  
**Purpose:** Central schedule.  
**Must connect:** Tasks + Bugs + Meetings + Milestones.

### 42 — AetherSpace Agenda
**Page:** Agenda  
**Purpose:** Chronological schedule view.

### 43 — AetherSpace Create Event
**Page:** Create Event  
**Purpose:** Create a calendar event.

### 44 — AetherSpace Event Details
**Page:** Event Details  
**Purpose:** Complete event information and linked objects.

### 45 — AetherSpace Upcoming Deadlines
**Page:** Upcoming Deadlines  
**Purpose:** Approaching task, bug, and milestone deadlines.

---

# Files

### 46 — AetherSpace Files Home
**Page:** Files Home  
**Purpose:** Main file-management view.

### 47 — AetherSpace Folder View
**Page:** Folder View  
**Purpose:** Files inside a selected folder.

### 48 — AetherSpace File Details
**Page:** File Details  
**Purpose:** File metadata and actions.

### 49 — AetherSpace Upload File
**Page:** Upload File  
**Purpose:** Upload workspace files with validation, progress, success, and error states.

### 50 — AetherSpace Recent Files
**Page:** Recent Files  
**Purpose:** Recently accessed/uploaded files.

### 51 — AetherSpace Shared Files
**Page:** Shared Files  
**Purpose:** Files shared with the current user/workspace.

---

# Notifications & Profile

### 52 — AetherSpace Notification Center
**Page:** Notification Center  
**Purpose:** Central notifications.  
**Tabs:** All, Unread, Tasks, Bugs, Mentions.  
**Action:** One-click mark as read.

### 53 — AetherSpace My Profile
**Page:** My Profile  
**Purpose:** Professional profile overview with contact details, roles, assigned tasks, and chronological activity.

### 54 — AetherSpace Edit Profile
**Page:** Edit Profile  
**Purpose:** Update personal profile information.

### 55 — AetherSpace Profile My Tasks
**Page:** My Tasks from Profile  
**Purpose:** Assigned tasks from the profile context.

### 56 — AetherSpace Profile My Bugs
**Page:** My Bugs from Profile  
**Purpose:** Relevant bugs from the profile context.

### 57 — AetherSpace Profile Activity
**Page:** Activity  
**Purpose:** Chronological personal activity.  
**Rule:** Text-based; no radar/graph charts.

### 58 — AetherSpace Workspace Roles
**Page:** Workspace Roles  
**Purpose:** Show the user's roles across accessible workspaces.

---

# Admin Panel

### 59 — AetherSpace User Management
**Page:** User Management  
**Purpose:** Manage platform users.

### 60 — AetherSpace User Details
**Page:** User Details  
**Purpose:** Detailed administrative user information.

### 61 — AetherSpace Roles Permissions
**Page:** Roles & Permissions  
**Purpose:** Manage and inspect RBAC: Admin, Manager, Contributor.

### 62 — AetherSpace Invitations
**Page:** Invitations  
**Purpose:** Manage invitations.

### 63 — AetherSpace Admin Workspace Management
**Page:** Admin Workspace Management  
**Purpose:** Platform-level workspace administration.

### 64 — AetherSpace Workspace Requests
**Page:** Workspace Requests  
**Purpose:** Review access requests.  
**Important connection:** The 403 `Request Access` action creates a request that appears here.

### 65 — AetherSpace Member Management
**Page:** Member Management  
**Purpose:** Manage workspace membership, roles, status, and access.

### 66 — AetherSpace Audit Logs
**Page:** Audit Logs  
**Purpose:** Chronological administrative/security activity.

### 67 — AetherSpace System Overview
**Page:** System Overview  
**Purpose:** High-level application/database/storage/authentication health and usage.

### 68 — AetherSpace Integrations
**Page:** Integrations  
**Purpose:** Manage connected external services.

### 69 — AetherSpace Storage Files
**Page:** Storage & Files  
**Purpose:** Administrative storage usage and file management.

### 70 — AetherSpace Security
**Page:** Security  
**Purpose:** Platform security controls and visibility. Never expose secrets.

### 71 — AetherSpace Backup Restore
**Page:** Backup & Restore  
**Purpose:** Backup/recovery controls supported by the actual implementation and hosting plan. Never claim unsupported provider capabilities.

### 72 — AetherSpace Activity Monitor
**Page:** Activity Monitor  
**Purpose:** Monitor recent system activity.

### 73 — AetherSpace Performance
**Page:** Performance  
**Purpose:** Application performance indicators that are actually available.

### 74 — AetherSpace Alerts
**Page:** Alerts  
**Purpose:** Important actionable system/resource warnings, such as approaching limits or application problems. Do not fabricate provider monitoring data.

---

# Settings

### 75 — AetherSpace Account Settings
**Page:** Account Settings  
**Purpose:** General account configuration.

### 76 — AetherSpace Profile Settings
**Page:** Profile Settings  
**Purpose:** Profile-specific configuration.

### 77 — AetherSpace Appearance
**Page:** Appearance  
**Purpose:** Light/dark appearance preferences.

### 78 — AetherSpace Notification Settings
**Page:** Notification Settings  
**Purpose:** Notification preferences.

### 79 — AetherSpace Security Settings
**Page:** Security Settings  
**Purpose:** Personal account security. Keep separate from platform-admin Security.

### 80 — AetherSpace Workspace Settings
**Page:** Workspace Settings  
**Purpose:** Workspace-specific configuration.

### 81 — AetherSpace Integration Settings
**Page:** Integration Settings  
**Purpose:** User/workspace integration configuration.

---

# Error Pages

### 82 — AetherSpace 400 Bad Request
**Page:** 400 — Bad Request  
**Copy:** “Invalid Request — The request could not be processed due to invalid parameters.”  
**Purpose:** Invalid request/parameter handling.

### 83 — AetherSpace 403 Permission Denied
**Page:** 403 — Permission Denied  
**Copy:** “Access Restricted — You do not have the required permissions to view this workspace or resource.”  
**Primary action:** `Request Access` when applicable.  
**Connection:** Request → Admin → Workspace Requests.

### 84 — AetherSpace 404 Page Not Found
**Page:** 404 — Page Not Found  
**Copy:** “Page Not Found — The task, bug, or workspace you are looking for does not exist or has been moved.”  
**Actions:** `Return to Dashboard`, `Go Back`.

### 85 — AetherSpace 500 Server Error
**Page:** 500 — Server Error  
**Copy:** “Internal Server Error — Something went wrong on our end. Our engineering team has been notified.”  
**Actions:** `Reload Page`, `Return to Dashboard`.

---

# Global AetherSpace Design Rules

## Theme — Dark / Obsidian
- Background: `#09090b` / `#0f172a`
- Cards/panels: `#18181b` / `#1e293b`
- Borders: zinc/slate dark borders
- Primary text: `#f4f4f5`
- Secondary text: `#a1a1aa`
- Accent: electric blue `#2563eb` or emerald

## Theme — Light / Clean Slate
- Background: `#f8fafc` / `#f4f4f5`
- Cards/panels: `#ffffff`
- Borders: `#e2e8f0`
- Primary text: `#0f172a`
- Secondary text: `#64748b`

## Universal Layout
- Left global icon rail.
- Workspace tree for scoped navigation.
- Universal header with search, notifications, and active-user profile.
- Main content canvas uses vertically stacked horizontal cards.
- Avoid cramped side-by-side dashboard grids.
- Preserve responsive behavior.

## Brand
Use only the approved AetherSpace logo/visual identity assets supplied in the design package. Do not invent a replacement logo.

## Accessibility
- Maintain readable contrast in both themes.
- Provide visible focus states.
- Use semantic HTML.
- Do not rely on color alone for status/severity.
- Make interactive controls keyboard accessible.

## Implementation Principle
The images are **visual references**, not screenshots to embed into the application. Rebuild the UI with Django templates, Tailwind CSS, Alpine.js/HTMX where appropriate, and real application data/models.

When a reference image and functional requirements differ, preserve the required functionality while keeping the visual result as close as practical to the approved reference.
