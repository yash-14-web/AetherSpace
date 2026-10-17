# AetherSpace Product Overview

## 1. Product Vision & Mission

**AetherSpace** is a unified team collaboration and agile execution workspace platform designed specifically for agile product engineering teams of **5 to 15 members**.

Small, fast-moving software teams frequently struggle with fragmented software stacks:
- **Jira** for tasks and sprints (heavyweight, complex configuration, high latency)
- **Slack** for real-time team communication (distracting context switching)
- **Google Drive / Notion** for shared design assets and files
- **Google Meet / Zoom** for standup calls and peer reviews

AetherSpace consolidates these mission-critical functions into a single, cohesive, lightning-fast platform built with clean ergonomics, obsidian dark aesthetics, and zero enterprise bloat.

---

## 2. Core Capabilities Matrix

| Module | Core Purpose | Implementation Status | Authoritative Repository Evidence |
|---|---|---|---|
| **Workspaces & Membership** | Multi-tenant isolation for distinct initiatives and teams; seat limits (15 default) and storage quotas. | **Implemented and Tested** | `workspaces/models.py`, `workspaces/views.py`, `workspaces/tests.py` |
| **Dashboards** | Multi-tiered operational views: Master Dashboard (cross-workspace), Workspace Dashboard, and Admin Dashboard. | **Implemented and Tested** | `workspaces/views.py`, `templates/workspaces/` |
| **Task Management** | Agile sprint planning, 6-digit task tracking (`######`), subtasks, activity logs, and PR code reviews (`CR-######`). | **Implemented and Tested** | `tasks/models.py`, `tasks/views.py`, `tasks/tests.py` |
| **Bug Tracking** | Defect triage with B-prefix IDs (`B-######`), severities (Sev 1–4), repro steps, and direct bi-directional task linkage. | **Implemented and Tested** | `bugs/models.py`, `bugs/views.py`, `bugs/tests.py` |
| **Chat & Messaging** | Persistent channels (`#general`, `#dev`), 1-on-1 direct messages, attachments, emoji reactions, and live WebSockets. | **Implemented and Tested** | `chat/models.py`, `chat/consumers.py`, `chat/views.py` |
| **Meet Hub** | Daily standup video rooms, in-chat calling, WebRTC media via Jitsi, and cross-page ringing modal. | **Implemented & Gated (Coming Soon)** | `meetings/models.py`, `meetings/consumers.py`, `meetings/views.py` |
| **Calendar & Events** | Team milestones, task deadlines, sprint cadences, work sessions, formatted agendas, and attendee tracking. | **Implemented and Tested** | `calendars/models.py`, `calendars/views.py`, `calendars/tests.py` |
| **Files & Storage** | Hierarchical folders, file versioning, direct user shares, external resource links, and Supabase cloud storage. | **Implemented and Tested** | `files/models.py`, `files/views.py`, `files/tests.py` |
| **Time Tracking** | Real-time live stopwatches, manual time logs against 6-digit tasks, and sprint labor accumulation analytics. | **Implemented and Tested** | `timetracking/models.py`, `timetracking/views.py`, `timetracking/tests.py` |
| **Notifications** | Real-time event notifications for assignments, mentions, and meetings, with email delivery audit logs. | **Implemented and Tested** | `notifications/models.py`, `notifications/services.py`, `notifications/tests.py` |
| **Profile & People** | Team member directory, Contributor ID display, availability statuses (Available, In Meeting, Offline), and hover cards. | **Implemented and Tested** | `accounts/models.py`, `accounts/views.py`, `templates/components/` |
| **Administration** | Platform user approvals, audit log compliance, security alerts, and full database JSON/CSV backup exports. | **Implemented and Tested** | `admin_panel/models.py`, `admin_panel/views.py`, `admin_panel/tests.py` |
| **Settings & Themes** | User preferences, theme switching (Obsidian Dark vs Clean Light), security settings, and password updates. | **Implemented and Tested** | `user_settings/views.py`, `user_settings/forms.py` |

---

## 3. User Roles & Permission Hierarchy

AetherSpace employs a strict two-tier permission model: **Platform Roles** and **Workspace Roles**.

### Platform Roles (Global System Scope)
* **Administrator (`ADMIN`)**: Platform governance, user registration approvals, audit log inspection, system alerts, backups, and feature gate controls (`ModuleStatus`).
* **Contributor (`CONTRIBUTOR`)**: Standard authenticated member capable of joining and collaborating within workspaces to which they are assigned.

### Workspace Roles (Workspace Scope)
* **Workspace Admin**: Can modify workspace settings, invite members, manage quotas, approve access requests, and archive the workspace.
* **Workspace Manager**: Can create sprints, reassign tasks and bugs, schedule team meetings, and coordinate cross-workspace deliverables.
* **Workspace Contributor**: Can view workspace content, work on assigned tasks, log time, report bugs, send chat messages, and join meetings.

---

## 4. Key User Journeys

### Journey 1: Team Member Registration & Onboarding
1. User navigates to `/auth/register/` and submits email, full name, and password.
2. System auto-generates a unique 5-digit Contributor ID (`#####C`, e.g. `26457C`).
3. User account is assigned `approval_status = PENDING`.
4. Platform Administrator receives alert in Admin Panel (`/admin-panel/approvals/`) and approves the user.
5. User logs in at `/auth/login/` with their Contributor ID and is admitted to their assigned workspaces.

### Journey 2: Agile Sprint & Task Execution
1. Manager creates a new Sprint (e.g. "Sprint 04 - Auth & Meet Hardening") in the Workspace.
2. Contributor creates Task `619347` assigned to the sprint.
3. Contributor starts live timer from the task card or Time Tracking rail; elapsed seconds accumulate.
4. Contributor opens a GitHub Pull Request and creates a Code Review Request (`CR-619347`).
5. Reviewer approves; Task transitions from `IN_PROGRESS` -> `CODE_REVIEW` -> `TESTING` -> `DONE`.

### Journey 3: Defect Discovery & Triage
1. QA Contributor identifies an issue during testing and clicks "Raise Bug".
2. System allocates a collision-safe ID: `B-882316` and tags severity (`SEV2 - Major`).
3. Contributor links `B-882316` directly to Task `619347`.
4. The defect appears in the linked task's connected bugs panel, keeping backlog context synchronized.

---

## 5. Technology Stack Summary

```
Frontend:           Django Templates (HTML5) + Tailwind CSS (v3) + Alpine.js (v3)
Backend:            Python 3.12+ / 3.13 + Django 4.2 LTS
Real-Time:          Django Channels 4.0 + Daphne 4.1 (ASGI)
Database:           PostgreSQL 15+ hosted on Supabase Cloud
Storage:            Supabase Cloud Object Storage (S3-compatible REST API)
Media Engine:       Jitsi Meet External API (meet.jit.si / 8x8.vc JaaS)
Production Host:    Render Cloud Web Service (Free Tier)
```

---

## 6. Known Limitations & Active Feature Gates

1. **Meet Hub Gate**: Meet Hub is guarded by `ModuleStatus` (`COMING_SOON`). It cannot be joined by normal contributors until the project owner concludes live two-user manual verification.
2. **Public Jitsi Timeout**: On `meet.jit.si`, unauthenticated iframe embeds enforce an 8x8 5-minute demo limit. Production migration to JaaS (`8x8.vc` with RS256 JWTs) or self-hosted Docker Jitsi Meet eliminates this restriction.
3. **Storage Quota**: Workspace storage quotas default to 50 MB per workspace to operate comfortably within Supabase free-tier limits (1 GB total). External links (Figma, GitHub, Notion) consume 0 quota bytes.
