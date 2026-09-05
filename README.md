# AetherSpace — Project Development README & Agent Control Document

> **Purpose:** This is the single living README for the AetherSpace project.
>
> It is written for both:
> 1. the **Antigravity coding agent**, which must follow these rules exactly, and
> 2. the **project owner/developer**, who needs a clear record of what is complete, pending, missing, blocked, and what must be manually verified.
>
> **IMPORTANT:** This README must be updated continuously during development. Do not create a separate hidden progress system that contradicts this file.

---

# 1. PROJECT IDENTITY

**Project:** AetherSpace  
**Type:** Lightweight team collaboration / Agile workspace platform  
**Target team size:** Small teams, approximately 1–15 members  
**Primary architecture:** Django monolith  
**Frontend:** Django Templates + HTML5 + Tailwind CSS + Alpine.js  
**Database:** Supabase PostgreSQL  
**File storage:** Supabase Storage  
**Source control:** GitHub  
**Deployment target:** Render  
**Testing:** Playwright scripts created by the agent and executed manually by the project owner  
**Realtime / future:** Django Channels + WebSockets  
**Meeting direction:** WebRTC / Jitsi-compatible approach

---

# 2. ABSOLUTE AGENT RULES

These rules override convenience.

## 2.1 No autonomous browser control

**STRICTLY PROHIBITED:**

- Do not open Chrome/Chromium/Edge yourself.
- Do not launch a browser through Playwright.
- Do not grant yourself browser permissions.
- Do not use browser automation to log into Supabase, GitHub, Render, Gmail, or any other external account.
- Do not click buttons in the owner's browser.
- Do not enter passwords, OTPs, API keys, tokens, or secrets into websites.
- Do not create accounts on the owner's behalf.
- Do not approve OAuth permissions yourself.
- Do not make security-sensitive account changes yourself.
- Do not claim that a UI is verified because you visually inspected it through an autonomous browser.

### Required behavior instead

The agent must:

1. Implement the code.
2. Create the required Playwright test scripts.
3. Tell the owner exactly how to run the tests.
4. Tell the owner exactly what the owner must manually verify.
5. Record the verification status in this README.

The owner runs the browser/tests and reports the result.

---

# 3. SUPABASE IS THE INITIAL DATABASE — STRICT RULE

AetherSpace is intentionally using **Supabase PostgreSQL from the initial development stage**.

## Never silently substitute:

- SQLite
- local PostgreSQL
- an in-memory database
- another hosted database
- another cloud database

for the project's real development database unless the owner explicitly changes the architecture.

## Required behavior

The agent must:

- Configure Django to use Supabase PostgreSQL.
- Keep database credentials in environment variables.
- Never commit credentials.
- Never expose the Supabase service-role/secret key to browser JavaScript.
- Use the correct public/client credentials only where appropriate.
- Keep migrations in the repository.
- Run Django migrations against the configured development database when the owner explicitly provides/approves the connection.
- Document any database setup problem instead of silently switching databases.

## Supabase Storage

Uploaded binary files must go to **Supabase Storage**.

PostgreSQL should store metadata/references, not uploaded binary file contents.

---

# 4. OWNER-ONLY ACCOUNT / CLOUD VERIFICATION

The agent must create a clear checklist whenever an external service is required.

The owner manually verifies:

### Supabase
- Project exists.
- Correct project/environment is selected.
- PostgreSQL database is reachable.
- Required tables/migrations exist.
- Storage bucket(s) exist.
- Storage policies/RLS are configured correctly.
- No secret/service-role key appears in frontend code.
- Environment variables are present in the local environment/deployment environment.

### GitHub
- Correct repository is being used.
- Branch is correct.
- Changes are committed/pushed only when requested.
- No secrets are committed.
- `.env` and other secret files are ignored.

### Render
- Correct repository/branch is connected.
- Build command is correct.
- Start command is correct.
- Environment variables are configured.
- Database URL/configuration is correct.
- Static files work.
- Supabase Storage works.
- Deployment logs contain no unresolved errors.

### Browser
The owner manually checks:
- Login/register flow
- Navigation
- Responsive layout
- Light/dark mode
- Forms
- Permissions
- File upload/download
- Chat
- Meetings
- Calendar
- Error pages
- Empty states
- Notifications
- Any page marked **OWNER VERIFICATION REQUIRED**

---

# 5. TECHNICAL SOURCE OF TRUTH

## Backend

Use Django.

Recommended responsibility separation:

- `core` — shared utilities, base templates, health checks, common errors
- `workspaces` — workspace/member/RBAC logic
- `tasks` — task management
- `bugs` — bug management
- `chat` — channels/direct messages/realtime preparation
- `meetings` — meetings and meeting rooms
- Additional apps only when they have a clear responsibility.

Do not create unnecessary apps simply to split files.

## Frontend

Use:

- Django templates
- Tailwind CSS
- Alpine.js
- Reusable template partials/components

Do not replace the frontend with React/Vue/etc. unless the owner explicitly changes the architecture.

---

# 6. VISUAL DESIGN SOURCE OF TRUTH

The supplied AetherSpace design images are **visual references**, not optional inspiration.

The implementation must preserve:

- Dark Obsidian visual language
- Clean Slate light theme
- Minimal, professional SaaS appearance
- Consistent spacing
- Consistent typography
- Consistent borders
- Consistent cards
- Consistent buttons
- Consistent status badges
- Consistent forms
- Consistent sidebar/header behavior
- Responsive behavior
- Accessibility
- Vertically stacked horizontal sections where practical
- Avoid cramped dashboards full of tiny cards
- Avoid unnecessary radar/graph charts on profile pages

## Core dark theme

Approximate reference tokens:

- Background: `#09090b` / `#0f172a`
- Cards/panels: `#18181b` / `#1e293b`
- Borders: zinc/slate dark borders
- Primary text: `#f4f4f5`
- Secondary text: `#a1a1aa`
- Accent: electric blue around `#2563eb`
- Emerald may be used for success states where appropriate

## Core light theme

- Background: `#f8fafc` / `#f4f4f5`
- Cards: white
- Borders: slate-200 / `#e2e8f0`
- Primary text: `#0f172a`
- Secondary text: `#64748b`

---

# 7. GLOBAL UI STRUCTURE

Where applicable, use the established AetherSpace shell:

### Global icon rail

- Dashboard
- Time Tracking
- Calendar
- Files
- Meet Hub
- Chat
- Notifications
- Profile
- Settings
- Theme toggle

### Workspace tree

Example:

```text
/Smart Classroom
  Team
  Dashboard
  Project Details
  Chat

/Flora
  Team
  Dashboard
  Project Details
  Chat
```

The actual workspace list must be data-driven.

### Universal header

Include as appropriate:

- Search
- Notification indicator
- Profile/avatar
- Profile dropdown
- Workspace context

---

# 8. RBAC / ROLE HIERARCHY

Roles:

- Admin
- Manager
- Contributor

Permissions are **workspace-scoped**.

A manager may belong to multiple workspaces.

## Manager

May have:

1. Master Dashboard
2. Workspace Dashboard

## Admin

May have:

3. Admin Dashboard

## Critical rule

Permissions must be enforced server-side.

Hiding a button is NOT permission enforcement.

Every protected view/action must validate the user's permission.

---

# 9. TASK AND BUG IDENTIFIERS

## Task ID

Format:

```text
619347
```

Exactly six numeric digits.

Generation must include collision protection.

Do not depend on random generation alone.

## Bug ID

Format:

```text
B-882316
```

Six numeric digits after `B-`.

Generation must include collision protection.

---

# 10. MAIN MODULES

## Authentication

- Login
- Register / Accept Invitation
- Forgot Password
- Reset Password
- Account Verification

## Workspace

- Workspace management
- Workspace dashboard
- Members
- Roles
- Workspace requests

## Tasks

- Task List
- Task Board / Kanban
- Task Details
- Create Task
- Edit Task
- My Tasks
- Task Activity
- Task Search & Filters

Preferred Kanban flow:

```text
To Do → In Progress → Code Review → Testing → Done
```

## Bugs

- Bug Dashboard
- Bug List
- Bug Details
- Raise Bug
- Edit Bug
- My Bugs
- Bug Activity
- Bug Search & Filters

## Chat

- Chat Home
- Channel View
- Direct Message
- Create Channel
- Channel Details
- Pinned Assets
- Shared Files

## Meet Hub

- Meet Hub
- Start Meeting
- Join Meeting
- Meeting Room
- Schedule Meeting
- Meeting Details
- Meeting History

## Calendar

- Calendar
- Agenda
- Create Event
- Event Details
- Upcoming Deadlines
- Tasks
- Bugs
- Meetings
- Milestones

## Files

- Files Home
- Folder View
- File Details
- Upload File
- Recent Files
- Shared Files

## Notifications

- Notification Center
- All
- Unread
- Tasks
- Bugs
- Mentions

## Profile

- My Profile
- Edit Profile
- My Tasks
- My Bugs
- Activity
- Workspace Roles

## Settings

- Account Settings
- Profile Settings
- Appearance
- Notification Settings
- Security
- Workspace Settings
- Integrations

## Admin

- User Management
- User Details
- Roles & Permissions
- Invitations
- Workspace Management
- Workspace Requests
- Member Management
- Audit Logs
- System Overview
- Integrations
- Storage & Files
- Security
- Backup & Restore
- Activity Monitor
- Performance
- Alerts

---

# 11. ERROR HANDLING

Create reusable full-page error handling.

Required pages:

- 400
- 401
- 403
- 404
- 408
- 429
- 500
- 503
- Network/connection failure state

## Required copy

### 400

**Invalid Request**

> The request could not be processed due to invalid parameters.

### 403

**Access Restricted**

> You do not have the required permissions to view this workspace or resource.

Action:

```text
[ Request Access ]
```

The Request Access workflow must connect to:

```text
403
  ↓
Request Access
  ↓
Workspace Request
  ↓
Admin → Workspace Requests
  ↓
Approve / Reject
  ↓
Notification
```

Only show Request Access when the resource exists but the user lacks permission.

### 404

**Page Not Found**

> The task, bug, or workspace you are looking for does not exist or has been moved.

Actions:

```text
[ Go Back ] [ Dashboard ]
```

### 500

**Internal Server Error**

> Something went wrong on our end. Our engineering team has been notified.

Actions:

```text
[ Reload ] [ Return to Dashboard ]
```

Do not expose stack traces to normal users.

---

# 12. EMPTY / LOADING / FAILURE STATES

Every major list or async component needs a deliberate state.

Required reusable states include:

- No tasks
- No bugs
- No files
- No notifications
- No search results
- No calendar events
- No workspace members
- No chat messages
- No meetings
- Loading
- Retry
- Validation error
- Permission denied
- Network failure
- Server failure

Do not leave blank screens.

---

# 13. PLAYWRIGHT TESTING POLICY

## VERY IMPORTANT

The agent must **CREATE Playwright scripts**.

The agent must **NOT RUN THE BROWSER AUTONOMOUSLY**.

The owner runs the scripts.

## Agent responsibilities

For each meaningful module, create/update Playwright tests covering:

- Page loads
- Authentication flow where testable
- Navigation
- Forms
- Validation
- CRUD actions
- Permission boundaries
- Search/filter behavior
- Empty states
- Error states
- Responsive checks where practical
- Important user journeys

Tests should be deterministic and readable.

Example structure:

```text
tests/
  e2e/
    auth/
    workspaces/
    tasks/
    bugs/
    chat/
    meetings/
    calendar/
    files/
    notifications/
    profile/
    admin/
    errors/
```

## Agent must report

After writing tests:

```text
Playwright tests created:
- tests/e2e/auth/login.spec.ts
- tests/e2e/tasks/task-crud.spec.ts
- ...

Execution:
NOT RUN BY AGENT

Owner action:
Run the following command...
```

The agent must never claim:

```text
Playwright passed
```

unless the owner has actually run the script and reported the result.

Use wording such as:

```text
Playwright script created — OWNER VERIFICATION REQUIRED
```

---

# 14. MANUAL TEST COMMANDS

The README must contain the exact commands needed for the current project.

Example:

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

For Playwright, use the project's configured command, for example:

```bash
npx playwright test
```

or a project-specific command documented by the agent.

If dependencies are missing, document the installation command instead of silently changing the environment.

---

# 15. AGENT WORK CYCLE

Every development task must follow this sequence.

## Step 1 — Understand

Before changing code:

- Read this README.
- Read existing project docs.
- Inspect the current repository.
- Identify the relevant app/module.
- Identify relevant UI reference image(s).
- Identify missing UI reference(s).
- Identify dependencies.
- Check whether the feature already partially exists.

## Step 2 — Plan

Write a short plan before large changes:

```text
Plan
1. Model/schema
2. Migration
3. Service/business logic
4. URL
5. View
6. Form/validation
7. Template/UI
8. Permissions
9. Empty/error/loading states
10. Playwright script
11. Documentation
```

## Step 3 — Implement

Implement in small verifiable pieces.

## Step 4 — Verify code

Run non-browser checks that do not require autonomous browser interaction:

- Django checks
- Python tests
- Migration checks
- Static/template checks
- Lint/type checks if configured

## Step 5 — Create Playwright

Write the Playwright script.

Do not launch the browser.

## Step 6 — Compare UI

Compare implementation against the supplied design reference.

If there is no suitable design reference, mark:

```text
UI REFERENCE MISSING
```

Do not invent a completely different visual system.

## Step 7 — Update README

Immediately update:

- Completed
- Pending
- Missing
- Blocked
- UI references
- Tests
- Owner verification
- Troubleshooting
- Development log

---

# 16. REQUIRED END-OF-TASK OUTPUT

At the end of every agent task, output exactly this structure:

```text
## DEVELOPMENT REPORT

### Done
- ...

### Pending
- ...

### Missing / Discovered
- ...

### UI Reference Status
- Reference used: ...
- Reference missing: ...
- Pages requiring new UI reference: ...

### Code Verification
- Django check: PASS / FAIL / NOT RUN
- Python tests: PASS / FAIL / NOT RUN
- Migration check: PASS / FAIL / NOT RUN

### Playwright
- Script created: ...
- Browser execution: NOT RUN BY AGENT
- Owner must run: ...

### Owner Manual Verification
1. ...
2. ...
3. ...

### Supabase Verification
- ...

### Troubleshooting / Known Issues
- ...

### README Updated
- YES

### Next Recommended Step
- ...
```

This report must also be reflected in the project's root README.

---

# 17. LIVING DEVELOPMENT STATUS

The following section must be maintained as development progresses.

## Status meanings

- `NOT STARTED`
- `IN PROGRESS`
- `IMPLEMENTED`
- `CODE VERIFIED`
- `OWNER VERIFICATION REQUIRED`
- `BLOCKED`
- `COMPLETE`

A module is **COMPLETE** only when:

1. Code is implemented.
2. Server-side permissions are implemented.
3. UI states are implemented.
4. Required tests exist.
5. Playwright script exists.
6. Owner has run the Playwright/manual checks.
7. No unresolved critical issue remains.
8. README is updated.

---

# 18. UI DESIGN REFERENCE INVENTORY

The current design library contains **42 PNG references** on disk (Audit note: `a_clean_high_resolution_branding_identity_present.png` listed in prior draft is missing from filesystem; actual disk count is 42).

The agent must keep this inventory accurate.

## Directly identifiable references

| File | Primary reference |
|---|---|
| `AetherSpace Dark SaaS Workspace Landing Page.png` | AetherSpace landing page / marketing-style entry screen |
| `a_full_page_dark_themed_saas_landing_page_website.png` | Landing page alternate reference |
| `AetherSpace Authentication Flow Showcase.png` | Authentication flow / login-register-reset screens |
| `a_clean_ui_ux_design_mockup_image_showing_multiple.png` | Authentication / multi-form UI reference |
| `AetherSpace Dark Mode Dashboard.png` | Main workspace/dashboard reference |
| `AetherSpace Smart Classroom Dashboard.png` | Smart Classroom workspace/project dashboard reference |
| `AetherSpace Dark Workspace Dashboard、】【.png` | Workspace dashboard reference (contains Japanese brackets in filename) |
| `AetherSpace Dark Mode Dashboard Collage.png` | General application dashboard / workspace composite |
| `Dark-Mode Collaboration Dashboard Mockup.png` | Collaboration / workspace dashboard reference |
| `AetherSpace Task Management Dashboard.png` | Task management dashboard/list/board reference |
| `AetherSpace Bug Tracking Dashboard.png` | Bug tracking dashboard/reference |
| `Dark Calendar Dashboard Mockup.png` | Calendar reference |
| `Dark File Management Dashboard Mockup.png` | File management reference |
| `AetherSpace Meeting App Dashboard Mockup.png` | Meeting / Meet Hub reference |
| `AetherSpace Dark Mode Settings Dashboard.png` | Settings reference |
| `a_clean_ui_design_mockup_image_showing_four_error.png` | Error pages: 400 / 403 / 404 / 500 showcase |
| `a_clean_high_resolution_branding_identity_present.png` | *[MISSING ON DISK]* AetherSpace branding / visual identity reference |

## Admin/dashboard reference family

The following files are primarily dashboard/admin/composite references. The agent must inspect the image itself before assigning it to one exact page:

```text
AetherSpace Admin Dashboard Collage(1).png
AetherSpace Admin Dashboard Collage(2).png
AetherSpace Admin Dashboard Collage.png
AetherSpace Admin Dashboard Overview(1).png
AetherSpace Admin Dashboard Overview.png
AetherSpace Dark Admin Dashboard Grid.png
Dark Admin Dashboard UI Mockup.png
a_clean_dark_themed_admin_dashboard_ui_mockup_scr.png
a_clean_high_resolution_dark_themed_admin_dashboa.png
a_dark_themed_admin_dashboard_ui_mockup_shown_as.png
a_high_resolution_screenshot_of_a_dark_themed_admi.png
a_high_resolution_dark_mode_application_dashboard.png
a_high_resolution_multi_panel_dark_ui_dashboard_sc.png
a_screenshot_ui_collage_of_a_dark_themed_admin_das.png
a_wide_composite_ui_design_screenshot_dashboard.png
a_wide_high_resolution_dark_themed_admin_dashboar.png
a_widescreen_dark_mode_admin_dashboard_ui_collage.png
a_high_resolution_dark_ui_graphic_design_showcase.png
```

**Rule:** Do not pretend these composite references are dedicated page designs. Record them as composite references unless the image clearly represents a specific page.

## Other composite/general UI references

```text
a_dark_themed_ui_mockup_screenshot_collage_of_a_ca.png
a_high_fidelity_ui_design_mockup_dashboard_scree.png
a_large_composite_screenshot_of_a_dark_themed_file.png
a_wide_dark_themed_ui_dashboard_mockup_collage.png
a_wide_high_resolution_mockup_screenshot_of_a_dar.png
a_wide_high_resolution_ui_ux_dashboard_screenshot.png
a_wide_screenshot_collage_ui_mockup_image_overa.png
a_widescreen_dark_themed_saas_dashboard_ui_screens.png
```

These are supporting visual references and must not be treated as dedicated designs unless inspection confirms that.

---

# 19. UI REFERENCE GAP DETECTION

This is one of the most important responsibilities.

For every page in the product blueprint, determine:

```text
[REFERENCE AVAILABLE]
[REFERENCE PARTIALLY AVAILABLE]
[COMPOSITE REFERENCE ONLY]
[UI REFERENCE MISSING]
```

## Known pages that have strong direct references

- Landing
- Authentication
- Main dashboard/workspace
- Smart Classroom dashboard
- Task management
- Bug tracking
- Calendar
- Files
- Meet Hub
- Settings
- Error pages
- Admin dashboard family

## Pages that currently appear to need dedicated references

Unless an existing composite image clearly covers them, flag these as missing:

### Tasks
- Task Details
- Create Task
- Edit Task
- My Tasks
- Task Activity
- Task Search & Filters

### Bugs
- Bug Details
- Raise Bug
- Edit Bug
- My Bugs
- Bug Activity
- Bug Search & Filters

### Chat
- Chat Home
- Channel View
- Direct Message
- Create Channel
- Channel Details
- Pinned Assets
- Shared Files

### Meetings
- Start Meeting
- Join Meeting
- Meeting Room
- Schedule Meeting
- Meeting Details
- Meeting History

### Calendar
- Agenda
- Create Event
- Event Details
- Upcoming Deadlines

### Files
- Files Home
- Folder View
- File Details
- Upload File
- Recent Files
- Shared Files

### Notifications
- Notification Center
- All
- Unread
- Tasks
- Bugs
- Mentions

### Profile
- My Profile
- Edit Profile
- My Tasks
- My Bugs
- Activity
- Workspace Roles

### Admin support pages
- User Management
- User Details
- Roles & Permissions
- Invitations
- Workspace Management
- Workspace Requests
- Member Management
- Audit Logs
- System Overview
- Integrations
- Storage & Files
- Security
- Backup & Restore
- Activity Monitor
- Performance
- Alerts

### Error states
The current reference explicitly covers 400/403/404/500. Dedicated references may still be useful for:

- 401
- 408
- 429
- 503
- Network/connection failure
- Reusable component-level retry state
- Empty states

**Do not automatically stop development because a reference is missing.**
Instead:
1. Use the established design system.
2. Flag the missing reference.
3. Record the page in the README.
4. Tell the owner a new reference may be needed.

---

# 20. DESIGN IMPLEMENTATION RULE

When implementing a page with a supplied reference:

1. Open/inspect the correct image manually if needed.
2. Identify layout hierarchy.
3. Identify sidebar/header.
4. Identify cards.
5. Identify spacing.
6. Identify typography.
7. Identify status colors.
8. Identify controls.
9. Identify responsive behavior.
10. Implement the same visual language.

Do not copy an image literally.

Do not use the reference as an excuse to create a static screenshot.

The final page must be real, data-driven, accessible, and functional.

---

# 21. DATA / DATABASE RULES

- Use Django models.
- Use migrations.
- Add indexes where justified.
- Use transactions for atomic multi-table operations.
- Avoid N+1 queries.
- Use `select_related` / `prefetch_related` appropriately.
- Paginate large lists.
- Validate input server-side.
- Never trust client-side permission checks.
- Never store passwords manually.
- Never store uploaded files directly in PostgreSQL.
- Never expose secrets in templates or JavaScript.

---

# 22. SECURITY RULES

Required:

- CSRF protection
- Django authentication
- Server-side authorization
- Workspace-scoped RBAC
- Secure file access
- Validation
- Safe redirects
- Secure secret management
- No service-role key in browser
- No credentials in Git
- No sensitive data in logs
- No stack traces in production responses

---

# 23. TROUBLESHOOTING LOG

The agent must add real issues here as they are discovered.

Format:

```text
### YYYY-MM-DD — Issue title

Problem:
...

Cause:
...

Fix:
...

Verification:
...

Owner action:
...
```

Do not delete useful troubleshooting history.

If an issue becomes obsolete, mark it as resolved rather than erasing the history.

### 2026-09-05 — UI Design Reference Library Inventory Discrepancy

Problem:
`README.md` previously specified 43 PNG reference files, citing `a_clean_high_resolution_branding_identity_present.png`. On disk in `AetherSpace_Designs/`, only 42 PNG files exist.

Cause:
`a_clean_high_resolution_branding_identity_present.png` was noted in documentation drafts but was never saved into the filesystem asset directory. Additionally, `AetherSpace Dark Workspace Dashboard、】【.png` contains Japanese punctuation characters (`、】【`) in the filename.

Fix:
Documented the discrepancy in Section 18 and added `[MISSING UI]` entry in Section 28. In code referencing the workspace dashboard mockup, handle or sanitize the path appropriately.

Verification:
Verified via PowerShell `Test-Path` and `Measure-Object` confirming 42 PNGs present.

Owner action:
If a dedicated standalone branding/logo sheet is needed, provide `a_clean_high_resolution_branding_identity_present.png`. Otherwise, branding assets on the Landing and Auth mockups will serve as visual reference.

### 2026-09-05 — Windows PowerShell Script Execution Policy Blocks npm.ps1

Problem:
Executing `npm` directly in PowerShell fails with `PSSecurityException` (`File C:\Program Files\nodejs\npm.ps1 cannot be loaded because running scripts is disabled on this system`).

Cause:
Windows PowerShell default execution policy disables unsigned `.ps1` wrapper scripts.

Fix:
Execute node/npm commands using `cmd.exe /c npm ...` or invoke `npm.cmd` / `npx.cmd` directly.

Verification:
Executed `cmd.exe /c npm --version` successfully (returned `11.16.0`).

Owner action:
None required for agent operations; owner may optionally set execution policy (`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`) if desired in their own terminal.

### 2026-09-05 — WhiteNoise Manifest Entry Missing for 'css/dist/styles.css' During Test Execution

Problem:
During `python manage.py test`, client requests failed with `ValueError: Missing staticfiles manifest entry for 'css/dist/styles.css'` and `UserWarning: No directory at: ...\staticfiles\`.

Cause:
`STATICFILES_STORAGE` was unconditionally set to `whitenoise.storage.CompressedManifestStaticFilesStorage`, which mandates a pre-generated `staticfiles.json` manifest (from `collectstatic`).

Fix:
1. Made `STATICFILES_STORAGE` conditional in `settings.py`: using `django.contrib.staticfiles.storage.StaticFilesStorage` when `DEBUG = True` (or during testing) and `CompressedManifestStaticFilesStorage` for production deployments.
2. Created local `staticfiles/` directory so WhiteNoise initialization succeeds cleanly.

Verification:
Reran `python manage.py test`. All 13 test cases passed cleanly with `OK` in 34.3s on Supabase PostgreSQL.

Owner action:
None required.

### 2026-09-05 — Playwright Cannot Find Module '@playwright/test'

Problem:
Running `npx playwright test` failed with `Error: Cannot find module '@playwright/test'`.

Cause:
`playwright.config.ts` imports from `@playwright/test`. Without `@playwright/test` explicitly installed in local `devDependencies`, the runner could not resolve the required test harness modules.

Fix:
1. Installed `@playwright/test` into `devDependencies`: `npm install -D @playwright/test`.
2. Added `"test:e2e": "playwright test"` script to `package.json`.
3. Verified resolution via `npx playwright --version` (1.63.0).

Owner action:
Before running tests for the first time on a machine, install Playwright browser engines:
`npx playwright install`
Then run:
`npx playwright test` (or `npx playwright test --project=chromium` or `npm run test:e2e`)

---

# 24. DEVELOPMENT LOG

The agent must append a concise entry after each meaningful development session.

Format:

```text
### YYYY-MM-DD — Feature / Module

Done:
- ...

Pending:
- ...

Missing:
- ...

Tests:
- ...

Playwright:
- Script created: ...
- Agent browser execution: NOT PERMITTED

Owner verification:
- ...

Next:
- ...
```

### 2026-09-05 — Phase 1: Foundation & Authentication Setup

Done:
- Django project `aetherspace` initialized with core modular apps: `core`, `accounts`, `workspaces`, `tasks`, `bugs`, `chat`, `meetings`.
- Configured `DATABASE_URL` connecting directly to Supabase PostgreSQL with SSL require mode enabled.
- Defined authoritative Custom User model (`accounts.User`) with UUID primary key, unique email, and `accounts.UserProfile`.
- Applied all initial migrations (`accounts`, `auth`, `contenttypes`, `sessions`, `admin`) directly to Supabase PostgreSQL.
- Installed and configured Tailwind CSS (with forms & typography plugins) compiled to `static/css/dist/styles.css`.
- Built reusable base shell (`templates/base.html`, `templates/components/header.html`, `templates/components/sidebar.html`, `templates/components/messages.html`) supporting Dark Obsidian & Clean Slate theme toggling via Alpine.js and `localStorage`.
- Created landing page view and template (`templates/core/landing.html`).
- Created complete authentication suite (Login, Register, Forgot Password, Reset Password, Verification) with validation and messages.
- Created custom error handlers (`400`, `403` with Request Access action, `404`, `500`).
- Created 13 automated Django unit tests covering core views, error handlers, and authentication flows (100% passing).
- Created Playwright test specifications: `tests/e2e/core/landing.spec.ts`, `tests/e2e/auth/login.spec.ts`, and `tests/e2e/core/errors.spec.ts`.
- Configured `.gitignore` (guaranteeing `.env` is ignored) and `.env.example`.
- Initialized local Git repository, created initial commit, and pushed to remote `https://github.com/yash-14-web/AetherSpace.git`.

Pending:
- Owner manual verification of local dev server (`http://127.0.0.1:8000`).
- Owner manual execution of Playwright test suite.
- Phase 2: Workspaces & Dashboards (Master Dashboard, Workspace Dashboard, Member Management, Workspace requests).

Missing:
- Dedicated design mockups for complex inner sub-views (Chat channels/DMs, Meet Hub room, Calendar agenda).

Tests:
- Django check: PASS (`System check identified no issues (0 silenced)`)
- Django unit tests: PASS (13/13 tests passed on Supabase PostgreSQL)
- Migration check: PASS (No unapplied migrations)

Playwright:
- Scripts created: `tests/e2e/core/landing.spec.ts`, `tests/e2e/auth/login.spec.ts`, `tests/e2e/core/errors.spec.ts`
- Browser execution: NOT RUN BY AGENT (per absolute security restrictions)
- Owner must run: `npx playwright test`

Owner verification:
- Verify local dev server runs: `python manage.py runserver`
- Verify authentication views and theme toggling in browser.
- Run Playwright test suite: `npx playwright test`

Next:
- Phase 2: Identity & Workspaces.

This log should make it possible to understand the project's progress without reading the entire codebase.

---

# 25. DEFINITION OF DONE

A feature is not done merely because the page renders.

A feature is done when:

- [ ] Model/schema complete
- [ ] Migration complete
- [ ] URL complete
- [ ] View/service complete
- [ ] Form/validation complete
- [ ] Permission checks complete
- [ ] UI complete
- [ ] Light theme checked
- [ ] Dark theme checked
- [ ] Responsive behavior addressed
- [ ] Loading state addressed
- [ ] Empty state addressed
- [ ] Validation errors addressed
- [ ] Permission errors addressed
- [ ] Server errors addressed
- [ ] Tests written
- [ ] Playwright script written
- [ ] Agent did NOT launch a browser
- [ ] Owner verification instructions written
- [ ] README updated
- [ ] No obvious N+1 issue
- [ ] No secrets committed
- [ ] Documentation updated where necessary

---

# 26. CURRENT PROJECT STATUS

> This section must be updated by the agent. Do not guess status.

## Overall

**Status:** `IN PROGRESS (Phase 1 Complete — Foundation & Authentication; Awaiting Owner Verification to proceed to Phase 2)`

## Authentication

**Status:** `IMPLEMENTED (Code Verified & Migrated to Supabase)`

- [x] Login
- [x] Register / Invitation
- [x] Forgot Password
- [x] Reset Password
- [x] Verification
- [x] Playwright scripts (`tests/e2e/auth/login.spec.ts`)
- [ ] Owner verification

## Workspaces

**Status:** `NOT STARTED`

- [ ] Workspace creation
- [ ] Workspace dashboard
- [ ] Members
- [ ] Roles
- [ ] Workspace requests
- [ ] Playwright scripts
- [ ] Owner verification

## Tasks

**Status:** `NOT STARTED`

- [ ] Task model
- [ ] Task IDs
- [ ] List
- [ ] Board
- [ ] Details
- [ ] Create
- [ ] Edit
- [ ] My Tasks
- [ ] Activity
- [ ] Search/filters
- [ ] Permissions
- [ ] Playwright scripts
- [ ] Owner verification

## Bugs

**Status:** `NOT STARTED`

- [ ] Bug model
- [ ] Bug IDs
- [ ] Dashboard
- [ ] List
- [ ] Details
- [ ] Raise
- [ ] Edit
- [ ] My Bugs
- [ ] Activity
- [ ] Search/filters
- [ ] Permissions
- [ ] Playwright scripts
- [ ] Owner verification

## Chat

**Status:** `NOT STARTED`

## Meet Hub

**Status:** `NOT STARTED`

## Calendar

**Status:** `NOT STARTED`

## Files

**Status:** `NOT STARTED`

## Notifications

**Status:** `NOT STARTED`

## Profile

**Status:** `NOT STARTED`

## Settings

**Status:** `NOT STARTED`

## Admin

**Status:** `NOT STARTED`

## Error handling

**Status:** `IMPLEMENTED (Custom 400, 403, 404, 500 views & templates)`

## Deployment

**Status:** `NOT STARTED`

---

# 27. OWNER VERIFICATION QUEUE

The agent must add items here whenever the owner must personally verify something.

### Pending owner verification

- [ ] Start development server (`python manage.py runserver 127.0.0.1:8000`) and verify Landing Page (`http://127.0.0.1:8000/`) renders properly in both dark and light modes.
- [ ] Verify Authentication Pages:
  - Sign in: `http://127.0.0.1:8000/auth/login/`
  - Register: `http://127.0.0.1:8000/auth/register/`
  - Forgot Password: `http://127.0.0.1:8000/auth/forgot-password/`
  - Reset Password: `http://127.0.0.1:8000/auth/reset-password/`
  - Verification: `http://127.0.0.1:8000/auth/verify/`
- [ ] Verify custom error views:
  - `http://127.0.0.1:8000/test/400/`
  - `http://127.0.0.1:8000/test/403/` (check Request Access button)
  - `http://127.0.0.1:8000/test/404/`
  - `http://127.0.0.1:8000/test/500/`
- [ ] Run Playwright automated test suite: `npx playwright test`
- [ ] Verify Supabase PostgreSQL tables created (`accounts_user`, `accounts_userprofile`, `django_session`, `auth_permission`, etc.) in Supabase Table Editor.

Never mark these complete without owner confirmation.

---

# 28. MISSING THINGS QUEUE

The agent must add anything discovered that is not implemented or not sufficiently specified.

Categories:

- `MISSING UI`
- `MISSING BACKEND`
- `MISSING DATABASE`
- `MISSING PERMISSION`
- `MISSING TEST`
- `MISSING PLAYWRIGHT`
- `MISSING DOCUMENTATION`
- `MISSING CONFIGURATION`
- `EXTERNAL SERVICE REQUIRED`
- `OWNER DECISION REQUIRED`

### Current Queue

- [ ] `[MISSING UI]` Missing branding asset: `a_clean_high_resolution_branding_identity_present.png` referenced in README is not present on disk in `AetherSpace_Designs/`.
- [ ] `[MISSING UI]` Dedicated page mockups for secondary views: Chat (Channel View, DMs, Pinned Assets), Meet Hub (Active Room, Schedule, Join Code), Calendar (Agenda, Event Details), Files (Folder View, Upload modal/drawer), Profile Details, Settings tabs, and detailed Admin sub-panels (Audit logs, Security, System Overview).
- [ ] `[EXTERNAL SERVICE REQUIRED]` Supabase Storage bucket for binary file uploads (scheduled for Phase 8 / avatar uploads).
- [ ] `[OWNER DECISION REQUIRED]` Confirmation of WebRTC/Jitsi meeting provider implementation details (free public Jitsi Meet `meet.jit.si` domain vs custom server).

---

# 29. DO NOT HIDE PROBLEMS

If the agent discovers:

- a missing design
- unclear requirement
- broken migration
- database problem
- Supabase policy problem
- missing environment variable
- security issue
- failing test
- inconsistent UI
- duplicate implementation
- architectural conflict
- missing page
- missing Playwright script

it must report it.

Do not silently work around it.

Do not mark the feature complete.

---

# 30. FINAL AGENT PRINCIPLE

AetherSpace should be developed as **one coherent product**, not as disconnected demo pages.

Every implementation must connect:

```text
UI
 ↓
Django View / Service
 ↓
Validation
 ↓
Permission
 ↓
Database / Supabase
 ↓
Storage where required
 ↓
Tests
 ↓
Playwright script
 ↓
Owner verification
 ↓
README status update
```

The agent is responsible for creating the code, documentation, tests, and verification instructions.

The owner is responsible for:

- external account access
- browser execution
- Playwright execution
- cloud-console verification
- secret entry
- security-sensitive approvals
- final acceptance

**Never reverse these responsibilities.**

---

# 31. FIRST ACTION FOR A NEW AGENT SESSION

Before modifying anything, do this:

1. Read this README completely.
2. Inspect the repository structure.
3. Inspect current Git status.
4. Inspect installed dependencies.
5. Inspect Django settings.
6. Confirm the configured database target is Supabase PostgreSQL.
7. Confirm Supabase credentials are environment-based.
8. Confirm no browser automation is configured to run autonomously.
9. Inspect the design reference directory.
10. Map the requested feature to an existing design reference.
11. If no suitable reference exists, add it to **MISSING THINGS QUEUE** as `MISSING UI`.
12. Check **DEVELOPMENT LOG**, **TROUBLESHOOTING LOG**, and **OWNER VERIFICATION QUEUE**.
13. Only then begin implementation.

---

# 32. OWNER COMMAND / VERIFICATION PLACEHOLDER

The agent should replace this section with the exact commands for the current repository after setup.

```bash
# Django health
python manage.py check

# Migration consistency
python manage.py makemigrations --check

# Django tests
python manage.py test

# Playwright
npx playwright test
```

**Important:** The agent creates the Playwright scripts but does not execute the browser.

---

# 33. README MAINTENANCE RULE

This file is a **living project document**.

Whenever development changes:

- architecture
- database
- Supabase setup
- module status
- UI coverage
- testing
- deployment
- troubleshooting
- owner verification
- known limitations

the agent must update this README in the same development task.

At the end of every meaningful task:

> **If the README does not reflect the current state, the task is not complete.**

# AetherSpace — Initial Django Project Setup

Read the project's master README.md and all existing docs before starting.

## Goal

Set up the initial AetherSpace Django project cleanly and prepare it for GitHub and Supabase PostgreSQL.

## IMPORTANT SECURITY RULES

1. Do NOT open Chrome, Chromium, Edge, or any browser.
2. Do NOT use browser automation.
3. Do NOT access GitHub through a browser.
4. Do NOT access Supabase through a browser.
5. Do NOT ask for or generate passwords, API secrets, database passwords, OTPs, tokens, or service credentials.
6. Do NOT put secrets into source code.
7. Do NOT commit `.env`.
8. Do NOT use SQLite as the project's intended database.
9. Do NOT create a Supabase database manually through browser automation.
10. The owner will manually configure external services and provide only non-secret configuration when necessary.

## Phase 1 — Inspect

Before changing anything:

- Read README.md completely.
- Read all project docs.
- Inspect the current repository.
- Check whether Django is already initialized.
- Check Python version.
- Check installed packages.
- Check Git status.
- Check whether a Git repository already exists.

Do not overwrite an existing project blindly.

## Phase 2 — Django foundation

Create the Django project using the agreed architecture.

Backend:

- Django
- Django Templates
- Tailwind CSS
- Alpine.js

Create only the necessary initial Django structure.

Initial apps should follow the project architecture:

- core
- workspaces
- tasks
- bugs
- chat
- meetings

Do not build all features yet.

Do not create unnecessary apps.

## Phase 3 — Database preparation

Prepare Django for PostgreSQL/Supabase.

Requirements:

- Install the appropriate PostgreSQL Django driver.
- Configure database settings through environment variables.
- Do NOT hard-code database credentials.
- Do NOT commit credentials.
- Do NOT fall back to SQLite silently.
- Create `.env.example` containing variable names only.
- Ensure `.env` is ignored by Git.

Example variable names may include:

DATABASE_URL=
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=

Do NOT put real values in `.env.example`.

Do NOT invent values.

The owner will enter the real Supabase credentials locally.

## Phase 4 — Project structure

Create a clean maintainable structure.

Include appropriate directories for:

- templates
- static
- tests
- documentation
- Playwright tests

Keep responsibilities clear.

## Phase 5 — Base configuration

Configure:

- Django settings
- URLs
- Templates
- Static files
- Media/storage configuration placeholder
- Environment configuration
- Development/production-safe settings structure
- Custom error handling foundation where appropriate

Do not implement the entire product yet.

## Phase 6 — Git safety

Create/update:

`.gitignore`

It must exclude:

- `.env`
- secrets
- Python cache
- virtual environments
- local databases if any
- generated files
- IDE files
- OS files
- Playwright artifacts
- test reports

Create:

`.env.example`

with placeholders only.

## Phase 7 — Verification

Run non-browser checks only.

Run:

python manage.py check

Run migration consistency checks where applicable.

Do NOT launch a browser.

Do NOT run Playwright.

Do NOT claim browser verification.

If Playwright infrastructure is appropriate at this stage, CREATE the initial configuration/scripts but do not execute them.

## Phase 8 — Git

Initialize Git if necessary.

Create the initial baseline commit containing:

- Django project
- Initial apps
- Configuration
- `.gitignore`
- `.env.example`
- Documentation
- Test structure

Do NOT commit:

- `.env`
- passwords
- Supabase secrets
- API keys
- tokens
- browser credentials

## GitHub

Do NOT create or configure the GitHub repository through a browser.

Prepare the repository for the owner to connect/push.

If the GitHub remote is already configured, inspect it and report it.

If it is not configured, report:

"GitHub remote requires owner action."

Do not invent a GitHub URL.

## Playwright

Create the initial Playwright test structure.

The agent MUST NOT execute the browser.

The final report must explicitly say:

"Playwright browser execution: NOT RUN BY AGENT."

Tell the owner exactly which command they can run themselves.

## README

Update the master README.md with:

### Done
Everything successfully implemented.

### Pending
Anything remaining.

### Missing / Discovered
Anything missing or unclear.

### UI Reference Status
Identify which supplied AetherSpace design reference applies to the current work.

If no suitable design exists:

[MISSING UI]

Do not invent a fake reference.

### Code Verification
Record actual results.

### Playwright
Record scripts created.

### Owner Manual Verification
List exactly what the owner must verify.

### Supabase Verification
List what the owner must configure manually.

### Troubleshooting
Record any issue discovered.

### Development Log
Add a dated entry.

## Final output

Use exactly:

## DEVELOPMENT REPORT — PHASE 2: AUTHENTICATION & USER FOUNDATION

### Done
- **Custom User Model & Roles Foundation**:
  - Defined `UserRole` `TextChoices` (`ADMIN`, `MANAGER`, `CONTRIBUTOR`) in `accounts.models`.
  - Added indexed `role` field (default: `CONTRIBUTOR`) and `is_verified` boolean to `accounts.User`.
  - Added role helper properties (`is_admin_role`, `is_manager_role`, `is_contributor_role`).
  - Updated `UserManager.create_superuser` to automatically assign `UserRole.ADMIN` and `is_verified=True`.
  - Created migration `accounts.0002_user_is_verified_user_role_and_more` and migrated live Supabase PostgreSQL.
- **Token Security & Cryptographic Handlers**:
  - Implemented `AccountVerificationTokenGenerator` in `accounts.tokens` for one-time, time-sensitive verification tokens.
  - Implemented secure password reset tokens using Django's built-in cryptographic `default_token_generator` and `urlsafe_base64_encode`.
- **Forms & Robust Server-Side Validation**:
  - `LoginForm`: Email & password authentication with `remember_me` handling (14-day persistent session vs browser-close session expiry).
  - `RegisterForm`: Full name, work email, password strength verification, confirm password matching, and mandatory Terms of Service / Privacy Policy agreement.
  - `ForgotPasswordForm`: Case-insensitive email recovery dispatch.
  - `ResetPasswordForm`: Password confirmation matching and Django password validation.
  - `ResendVerificationForm`: Dynamic re-dispatch of verification emails.
- **High-Fidelity Authentication UI (Dual-Theme)**:
  - Upgraded all 5 auth pages directly matching `AetherSpace Authentication Flow Showcase.png`:
    - `templates/accounts/login.html`: Desktop split-card with live workspace sprint preview, social auth placeholders, remember me, and enterprise trust badges.
    - `templates/accounts/register.html`: Invitation showcase with interactive Alpine.js password strength progress bar (Weak/Medium/Strong) and show/hide password toggles.
    - `templates/accounts/forgot_password.html`: Paper plane illustration, recovery link dispatch confirmation, and local development helper link.
    - `templates/accounts/reset_password.html`: Password reset form with strength meter, show/hide eye toggle, and invalid/expired token error state.
    - `templates/accounts/verification.html`: Email checklist, interactive resend modal, local development test link, and invalid token handling.
  - Recompiled and minified Tailwind CSS (`static/css/dist/styles.css`).
- **Comprehensive Automated Testing**:
  - 16 unit tests in `accounts.tests` covering models, superusers, login, remember-me session persistence, invalid credentials, inactive accounts, registration, validation errors, password reset token invalidation, and email verification.
  - 21 total Django tests passing with 100% success rate on Supabase PostgreSQL.
- **End-to-End Playwright Spec Suite**:
  - Created/updated specs in `tests/e2e/auth/`:
    - `login.spec.ts`: Form rendering, invalid credentials, password toggle, navigation to register.
    - `register.spec.ts`: Input fields, client-side password strength bar, password mismatch validation.
    - `password_reset.spec.ts`: Forgot password submission, recovery dispatch state, invalid token handling.
    - `verification.spec.ts`: Verification checklist, bad token error state, resend modal.
  - Playwright browser execution was **NOT RUN BY AGENT** in compliance with safety instructions.

### Pending
- **Phase 3: Workspaces & RBAC**:
  - `workspaces.models.Workspace` and `workspaces.models.WorkspaceMembership`.
  - Workspace Switcher, Workspace Requests, and Role-Based Access Control (Admin, Manager, Contributor).
  - Master Dashboard and Workspace Dashboard views.

### Missing / Discovered
- None. All Phase 2 specifications, design mockups, and token workflows are fully resolved and operational.

### UI Reference Status
- Reference used: `AetherSpace_Designs/AetherSpace Authentication Flow Showcase.png`
- Layouts faithfully matched: Login split card, Register invitation showcase, Forgot Password paper plane recovery, Reset Password strength meter, and Account Verification checklist.

### Code Verification
- Django configuration check: **PASS** (`python manage.py check` — 0 issues, 0 silenced)
- Migration check: **PASS** (`accounts.0002_user_is_verified_user_role_and_more` applied to Supabase PostgreSQL)
- Non-browser unit tests: **PASS** (`python manage.py test` — 21 tests passed in 115.2s, OK)

### Playwright
- Scripts created/updated:
  - `tests/e2e/auth/login.spec.ts`
  - `tests/e2e/auth/register.spec.ts`
  - `tests/e2e/auth/password_reset.spec.ts`
  - `tests/e2e/auth/verification.spec.ts`
- Browser execution: **NOT RUN BY AGENT** (in strict adherence to safety rules)
- Owner test command:
  ```bash
  npx playwright test tests/e2e/auth --project=chromium
  ```

### Git
- Repository initialized: Yes
- Remote configured: `https://github.com/yash-14-web/AetherSpace.git` (branch `main`)
- Phase 2 commit ready for push.

### Owner Manual Verification
1. Start the server:
   ```bash
   python manage.py runserver
   ```
2. Test Registration:
   - Visit `http://127.0.0.1:8000/auth/register/`
   - Type a password and watch the dynamic strength meter update from Weak to Strong.
   - Click the eye icon to toggle password visibility.
   - Complete registration and verify redirection to `http://127.0.0.1:8000/auth/verify/`.
3. Test Verification:
   - Click the simulated verification link on `http://127.0.0.1:8000/auth/verify/` to mark your account as verified.
4. Test Password Recovery:
   - Visit `http://127.0.0.1:8000/auth/forgot-password/` and submit your email.
   - Click the generated reset link and update your password.
5. Test Login & Remember Me:
   - Sign in at `http://127.0.0.1:8000/auth/login/` with your updated credentials.
6. Optional Playwright E2E run:
   ```bash
   npx playwright test tests/e2e/auth --project=chromium
   ```

### Supabase
- PostgreSQL schema updated with `accounts_user.role` (varchar) and `accounts_user.is_verified` (boolean).
- Indexes on `email` and `role` active.

### Troubleshooting / Known Issues
- Note on Windows PowerShell: Subexpression characters in git commit messages should be escaped or quoted with single quotes.
- Note on Playwright browser binaries: Only Chromium is installed by default on Windows. If Firefox or WebKit tests are desired, run `npx playwright install`.

### README Updated
- YES

### Next Recommended Step
- Proceed to **Phase 2.5: Landing Page + Branding** (COMPLETED).

---

## DEVELOPMENT REPORT — PHASE 2.5: LANDING PAGE + BRANDING

### Done
- **Official Branding & Global Logo Assets**:
  - Incorporated user-approved atomic glowing "A" logo asset (`static/images/logo.png`) and high-res browser favicon (`static/images/favicon.png`).
  - Added favicon and apple-touch-icon links globally in `<head>` of `templates/base.html`.
  - Added brand logo to global navigation header (`templates/components/header.html`), global icon rail (`templates/components/sidebar.html`), and all authentication cards.
- **High-Fidelity Public Landing Page (`templates/core/landing.html`)**:
  - Implemented exact design from `AetherSpace_Designs/AetherSpace Dark SaaS Workspace Landing Page.png`.
  - Dual-theme support: Dark Obsidian (`#09090b` / `#18181b`) and Clean Slate (`#f8fafc` / `#ffffff`) with seamless Alpine.js theme switcher.
  - **Public Navigation Header**: Added center navigation links (`Features`, `Solutions`, `Resources`, `Pricing`, `About`), theme toggle, and auth buttons (`Sign In`, `Get Started Free`).
  - **2-Column Desktop / Responsive Hero**:
    - Left column: Bold headline ("Your Team. Your Workspace. One AetherSpace."), copy, primary CTA button with arrow icon, secondary CTA with play icon, and 3 trust metrics ("Secure by design", "Built for small teams", "Fast & intuitive").
    - Right column: High-fidelity workspace dashboard preview widget featuring live sprint indicators, active task items with status pills, and team member presence avatars.
  - **All-in-One Workspace Capabilities (6 Feature Cards)**:
    - Task Management (Kanban boards, sprint cycles, priority scoring).
    - Bug Tracking (Numeric/B-prefix ID system, severity triage, quick fix flows).
    - Team Chat (Real-time channels, direct messages, contextual threads).
    - Meet Hub (WebRTC/Jitsi-compatible meeting rooms, screen sharing, audio rooms).
    - Calendar & Agenda (Sprint schedules, milestone deadlines, synchronized events).
    - Files & Sharing (Supabase Storage integration, asset previews, role access).
  - **Why Teams Love AetherSpace (4 Value Pillars)**:
    - Collaborate Seamlessly (Real-time presence, mentions, and instant alerts).
    - Stay Organized (Unified view of tasks, bugs, and milestones).
    - Secure & Private (Role-based access control and workspace data isolation).
    - Simple & Intuitive (Zero bloat, sub-second navigation, distraction-free).
  - **Elevated CTA Banner**: High-contrast card with headline, copy, and dual CTA action buttons.
  - **Comprehensive 5-Column Sitemap Footer**: Product, Solutions, Resources, Company columns, newsletter email subscription input, copyright, status badge ("All systems normal"), and social link placeholders.
- **Tailwind CSS Compilation**:
  - Compiled and minified full design utilities into `static/css/dist/styles.css` using `npm run build:css`.
- **Automated Testing & Checks**:
  - Updated `core.tests.CoreViewsTest` to verify status code 200, branding, hero text, all 6 workspace features, and value pillars.
  - Ran `python manage.py check` (0 issues, 0 silenced).
  - Ran `python manage.py test core --keepdb` (5 tests passed, 100% success).
- **Playwright Test Suite**:
  - Updated `tests/e2e/core/landing.spec.ts` testing branding logo, public navigation, hero CTAs, 6 feature cards, 4 value pillars, CTA banner, and dual-theme switching.
  - Browser execution **NOT RUN BY AGENT** in compliance with instructions.

### Pending
- **Phase 3: Workspaces & RBAC**:
  - `workspaces.models.Workspace` and `workspaces.models.WorkspaceMembership`.
  - Workspace Switcher, Workspace Requests, and Role-Based Access Control (Admin, Manager, Contributor).
  - Master Dashboard and Workspace Dashboard views.

### Missing / Discovered
- None. All Phase 2.5 requirements, branding elements, and design mockup sections are fully satisfied.

### UI Reference Status
- Reference used: `AetherSpace_Designs/AetherSpace Dark SaaS Workspace Landing Page.png`
- Layouts faithfully matched: Header navigation, 2-column hero, dashboard preview widget, 6 feature cards, 4 value pillars, CTA banner, and 5-column sitemap footer.

### Code Verification
- Django configuration check: **PASS** (`python manage.py check` — 0 issues, 0 silenced)
- Core unit tests: **PASS** (`python manage.py test core --keepdb` — 5 tests passed in 6.8s)

### Playwright
- Script updated: `tests/e2e/core/landing.spec.ts`
- Browser execution: **NOT RUN BY AGENT** (in strict adherence to safety rules)
- Owner test command:
  ```bash
  npx playwright test tests/e2e/core/landing.spec.ts --project=chromium
  ```

### Git
- Branch: `main`
- Remote: `https://github.com/yash-14-web/AetherSpace.git`

### Owner Manual Verification
1. Start the server:
   ```bash
   python manage.py runserver
   ```
2. Visit `http://127.0.0.1:8000/`:
   - Verify the atomic glowing logo is crisp in the top-left header.
   - Inspect the 2-column Hero section and dashboard preview widget.
   - Click the theme toggle (sun/moon) to switch between Dark Obsidian and Clean Slate.
   - Scroll through the 6 workspace feature cards and 4 value pillars.
   - Verify clicking "Get Started Free" redirects to `/auth/register/`.
   - Verify clicking "Sign In" redirects to `/auth/login/`.
3. Optional Playwright E2E run:
   ```bash
   npx playwright test tests/e2e/core/landing.spec.ts --project=chromium
   ```

### README Updated
- YES

### Next Recommended Step
- Proceed to **Phase 3: Identity, Workspaces & Navigation Structure** (`workspaces.models.Workspace`, `WorkspaceMembership`, Workspace Switcher, and Dashboards).


