# AetherSpace Troubleshooting & Operations Runbook

This runbook catalogs known runtime symptoms, diagnostic procedures, and verified step-by-step remediations for AetherSpace.

---

## 1. Database & Persistence Issues

### 1.1 Symptom: `django.db.utils.OperationalError: could not connect to server`
* **Likely Causes**:
  1. Supabase PostgreSQL instance paused or sleeping.
  2. Transaction pooler (PgBouncer) connection exhaustion.
  3. `DATABASE_URL` contains unescaped special characters in password.
* **Diagnosis**:
  Run diagnostic script:
  ```powershell
  python manage.py check --database default
  ```
* **Step-by-Step Resolution**:
  1. Log into the Supabase Dashboard and verify project is active (click "Resume project" if paused).
  2. If using port `5432`, consider switching to the transaction pooler port `6543`.
  3. Ensure URL encoding for special characters in database passwords (e.g. `@` becomes `%40`).
  4. Ensure `?sslmode=require` is appended to `DATABASE_URL`.

### 1.2 Symptom: `psycopg2.errors.UndefinedTable: relation ... does not exist`
* **Likely Causes**: Unapplied database migrations.
* **Resolution**:
  ```powershell
  python manage.py showmigrations
  python manage.py migrate
  ```

---

## 2. Real-Time WebSockets & Channels Issues

### 2.1 Symptom: In-Chat Messages Require Page Reload / Ringtone Does Not Play
* **Likely Causes**: Server is running under standard synchronous `runserver` rather than Daphne ASGI.
* **Diagnosis**: Inspect browser developer console for WebSocket errors:
  `WebSocket connection to 'ws://.../ws/chat/...' failed: Error during WebSocket handshake`.
* **Step-by-Step Resolution**:
  1. Stop the standard dev server (`Ctrl+C`).
  2. Launch Daphne:
     ```powershell
     daphne -b 127.0.0.1 -p 8000 aetherspace.asgi:application
     ```
  3. Verify `ProtocolTypeRouter` in `aetherspace/asgi.py` routes `"websocket"` to `AuthMiddlewareStack`.

### 2.2 Symptom: WebSocket Disconnects with Code `4003`
* **Likely Causes**: The connecting user does not belong to the target workspace or channel.
* **Resolution**: Ensure the user has an active `WorkspaceMembership` and `ChannelMembership` for that channel.

---

## 3. Meet Hub & Conferencing Issues

### 3.1 Symptom: Audio Call from Chat Disappears After ~1 Second
* **Likely Causes**:
  1. Form submit event race bypassed JavaScript CustomEvent.
  2. Stale orphaned `CallSession` in DB blocked new calls with validation error.
* **Diagnosis**: Check browser console for `Call error: You already have an active call in progress.`
* **Resolution**:
  1. Verified fix in Phase 3.1: Call buttons use `type="button"` and dispatch `aetherspace:initiate_call`.
  2. Service auto-prunes stale sessions via `reconcile_and_prune_stale_calls()`.
  3. If testing locally, reset any stuck active calls in database shell:
     ```powershell
     python manage.py shell -c "from meetings.models import CallSession; CallSession.objects.filter(status__in=['RINGING', 'ACCEPTED', 'CONNECTED']).update(status='ENDED')"
     ```

### 3.2 Symptom: "5-Minute Disconnection Warning" in Meeting Room
* **Likely Causes**: Public `meet.jit.si` domain enforces a strict 5-minute timeout on anonymous iframe embeds.
* **Resolution**:
  1. This is an external infrastructure constraint of 8x8's public domain.
  2. Production fix: Complete migration to JaaS (`8x8.vc`) with RS256 signed JWTs or self-hosted Docker Jitsi Meet.

### 3.3 Symptom: "Log in as Moderator" Prompt Upon Room Entrance
* **Likely Causes**: 8x8 requires authentication for newly generated anonymous rooms to claim host privileges.
* **Resolution**:
  1. For testing, click "Wait for host" or log in with free 8x8 credentials.
  2. Planned fix: When JaaS is implemented, configure moderator claims in the JWT (e.g. `context.user.moderator: true` [Needs verification against active provider schema]).

### 3.4 Symptom: Sudden Acoustic Feedback / Audio Echo During Call
* **Likely Causes**: Multiple tabs open to the same meeting room on the same machine accessing the audio hardware.
* **Resolution**:
  1. Close duplicate browser tabs or windows.
  2. AetherSpace includes a built-in `BroadcastChannel` that detects another active tab and displays an amber warning banner. Note that the warning is advisory and does not hard-abort Jitsi initialization; users must manually close the duplicate tab to prevent audio feedback.
  3. When conducting two-user tests, ensure testers use separate rooms or wear headphones.

---

## 4. User Access & Approval Issues

### 4.1 Symptom: Registered User Cannot Log In ("Pending Approval")
* **Likely Causes**: Account approval workflow is operating normally; newly registered users default to `PENDING`.
* **Resolution**:
  1. Log in with an Administrator account.
  2. Navigate to `/admin-panel/approvals/`.
  3. Locate the user by Contributor ID (`#####C`) and click **Approve**.

### 4.2 Symptom: `403 Forbidden` on Workspace Resource
* **Likely Causes**: User lacks an active `WorkspaceMembership` in that specific workspace.
* **Resolution**:
  1. Workspace Admin navigates to `/workspaces/w/<slug>/team/` and invites the user.
  2. Alternatively, the user submits a `WorkspaceAccessRequest` directly from the 403 page.

---

## 5. File Storage & Quotas

### 5.1 Symptom: `ValidationError: Workspace storage quota exceeded`
* **Likely Causes**: Active file uploads have reached the workspace quota limit (default 50 MB).
* **Resolution**:
  1. Workspace Admin navigates to `/workspaces/w/<slug>/settings/` and increases `storage_quota_mb`.
  2. Team members move unused assets to Trash and purge them.
  3. Team members link external resources (Figma, Notion, Google Drive), which consume 0 bytes.

---

## 6. Render Deployment Issues

### 6.1 Symptom: Cold Start Delay (30–50 Seconds)
* **Likely Causes**: Render free-tier instances sleep after 15 minutes of inactivity.
* **Resolution**: Normal free-tier behavior. Subsequent requests are served immediately.

### 6.2 Symptom: Static Files Return 404 or Unstyled HTML
* **Likely Causes**: `collectstatic` was not run during deployment.
* **Resolution**:
  Ensure Render's `buildCommand` in `render.yaml` includes:
  `python manage.py collectstatic --noinput`
