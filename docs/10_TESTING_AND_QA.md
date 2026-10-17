# AetherSpace Testing, QA & Verification Architecture

This document inventories the automated test suites, testing conventions, and manual quality assurance procedures enforced across AetherSpace.

---

## 1. Testing Philosophy & Verification Principle

1. **Automated Unit & Integration Tests**: Validate business logic, relational integrity, state machines, and permission boundaries in simulated, deterministic test environments.
2. **Security Regression Tests**: Assert defenses against XSS, SQL injection, open-redirects, IDOR, and credential exposure.
3. **End-to-End Browser Tests**: Playwright scripts simulate realistic multi-step user workflows.
4. **Manual Verification Requirement**: Automated tests **cannot** verify physical hardware (cameras, microphones, speakers) or external cloud media bridges. Features involving physical media must undergo documented two-device manual verification before general release.

---

## 2. Automated Test Inventory

### 2.1 Modular Application Backend Tests
Every core Django app maintains a dedicated `tests.py` or test directory:

| Test File | Primary Coverage | Execution Command |
|---|---|---|
| `accounts/tests.py` | Contributor ID generation, authentication, user approval lifecycle. | `python manage.py test accounts` |
| `workspaces/tests.py` | Workspace multi-tenancy, member roles, seat limits, access requests. | `python manage.py test workspaces` |
| `tasks/tests.py` | 6-digit tasks, sprints, subtasks, activity logging, code reviews. | `python manage.py test tasks` |
| `bugs/tests.py` | B-prefix defect triage, severity levels, task linkages, workspace scoping. | `python manage.py test bugs` |
| `chat/tests.py` | Channels, canonical DM pairing, reactions, pinned assets. | `python manage.py test chat` |
| `meetings/tests.py` | Meeting lifecycle, host permissions, attendance tracking, 1-on-1 calls. | `python manage.py test meetings` |
| `calendars/tests.py` | Calendar events, recurring scheduling, milestones, RSVP states. | `python manage.py test calendars` |
| `files/tests.py` | Folders, versioning, storage quotas, file shares, trash recovery. | `python manage.py test files` |
| `timetracking/tests.py`| Live running stopwatches, accumulated pause intervals, manual logs. | `python manage.py test timetracking` |
| `notifications/tests.py`| Event notification dispatch, category filtering, email delivery logs. | `python manage.py test notifications` |
| `admin_panel/tests.py` | Admin authorization, user approvals, audit log immutability, backups. | `python manage.py test admin_panel` |
| `user_settings/tests.py`| Appearance themes, password modification, user preferences. | `python manage.py test user_settings` |

### 2.2 Security & Forensic Test Suites (`tests/`)
AetherSpace maintains comprehensive regression test suites in the root `tests/` directory:

| Test Suite | Vulnerability & Compliance Focus |
|---|---|
| `tests/test_audit_fixes.py` | Validates fixes from forensic audits (RBAC, parameter validation). |
| `tests/test_bad_tag_filter_and_xss_security.py` | Asserts HTML tag stripping, script neutralization, and template auto-escaping. |
| `tests/test_batch8_codeql_security.py` | Defense against CodeQL security findings (resource injection, path traversal). |
| `tests/test_batch9_codeql_security.py` | Defense against CodeQL security findings (session fixation, CSRF). |
| `tests/test_markdown_pipeline.py` | Sanitization of user-submitted Markdown inputs via bleach. |
| `tests/test_meeting_webrtc_signaling.py` | WebSocket handshake, authentication, and signaling in `meetings`. |
| `tests/test_phase18_audit.py` | Cross-module contract and regression test suite. |
| `tests/test_phase18_gap_audit.py` | Comprehensive edge-case and gap verification suite. |
| `tests/test_redirect_security.py` | Open-redirect protection on login, logout, and notification links. |
| `tests/test_stack_trace_exposure_security.py` | Production error handler validation (ensures 500 pages omit debug traces). |
| `tests/test_supabase_database_security_lockdown.py`| Verifies zero client-side exposure of Supabase service-role keys. |
| `tests/test_url_sanitization_security.py` | Strict validation of external URLs (`javascript:` scheme blocking). |

### 2.3 Playwright End-to-End Suites (`tests/e2e/`)
Configured in `playwright.config.ts` running across Chromium, Firefox, WebKit, and Mobile Chrome:
- `tests/e2e/auth/`: Registration, approval redirect, Contributor ID login.
- `tests/e2e/workspaces/`: Workspace creation, member invitation, seat checks.
- `tests/e2e/tasks/`: Sprint planning, Kanban drag-and-drop, subtask toggle.
- `tests/e2e/chat/`: Real-time message stream, emoji reaction popover.
- `tests/e2e/meetings/`: Room entrance, Jitsi IFrame mount, audio echo detection.
- `tests/e2e/owner_qa_verification.spec.ts`: Complete owner acceptance workflow.
- `tests/e2e/phase19_launch_readiness.spec.ts`: Pre-release verification spec.

---

## 3. How to Run the Automated Suites

```powershell
# 1. Run all backend tests
python manage.py test

# 2. Run all security regression tests
python manage.py test tests

# 3. Run specific test case with verbose output
python manage.py test meetings.tests.MeetingModelTests -v 2

# 4. Run Playwright E2E tests (requires Node.js)
npx playwright test
```

---

## 4. Manual QA Verification Procedures

### Two-User Meeting Verification Matrix (Hardware Required)
Conducted across two separate physical machines or mobile devices:

| Step | Action Performed | Expected Behavior | Result |
|:---:|---|---|:---:|
| 1 | User A calls User B via Direct Message audio button. | User A sees outgoing modal; User B hears ringtone on any page. | Pending Owner Verification |
| 2 | User B clicks "Accept & Join". | Ringtone halts; both browsers redirect to meeting room. | Pending Owner Verification |
| 3 | User A speaks into microphone. | User B hears clean audio without acoustic feedback. | Pending Owner Verification |
| 4 | User B toggles video on. | User A sees User B's video stream rendered in Jitsi frame. | Pending Owner Verification |
| 5 | User A clicks "Share Screen". | Browser prompts for window/screen; User B sees shared display. | Pending Owner Verification |
| 6 | User A opens a second tab of the same room. | System detects duplicate tab and warns of audio echo. | Verified in Code |
| 7 | User A (Host) clicks "End Meeting for All". | User B is disconnected; meeting room updates to `ENDED`. | Verified in Code |
