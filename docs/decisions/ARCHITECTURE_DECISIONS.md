# AetherSpace Architecture Decision Records (ADR)

This document records the foundational architectural decisions made for the AetherSpace platform, their rationale, trade-offs, and verification evidence in the repository.

---

## ADR 01: Django Monolith with Server-Side Rendering (SSR) & Alpine.js

* **Status**: Accepted
* **Date**: Phase 1
* **Context**: AetherSpace is targeted at small agile teams (5–15 members) seeking a responsive, lightweight collaboration platform combining Jira, Slack, Notion, and Google Meet workflows. A decoupled Single Page Application (SPA) architecture with React/Vue requires double development velocity, separate state synchronization, API serialization overhead, and complex authentication flows.
* **Decision**: Implement AetherSpace as a unified Django monolith using Django Templates, Tailwind CSS, and Alpine.js for interactive micro-interactions. Avoid client-side frameworks like React unless explicitly requested by the project owner.
* **Consequences**:
  - Extremely fast initial page loads and unified session authentication.
  - No separate frontend build step or node runtime needed in production.
  - Alpine.js provides reactive modals, tab switching, and WebSocket listeners directly within HTML templates.
* **Evidence in Code**: `templates/`, `aetherspace/settings.py`, `templates/base.html`.

---

## ADR 02: PostgreSQL on Supabase Cloud as Authoritative Database

* **Status**: Accepted
* **Date**: Phase 1
* **Context**: Need a production-grade relational database from inception that supports ACID transactions, foreign key integrity, row-level indexes, and strict multi-tenant workspace isolation.
* **Decision**: Connect Django directly to Supabase PostgreSQL via `DATABASE_URL` using `psycopg2-binary` and `dj-database-url`. Prohibit silent fallbacks to SQLite in production and development.
* **Consequences**:
  - Relational integrity and constraints enforced at database level.
  - Connection pooling configured via `CONN_MAX_AGE` (0 for transaction pooler compatibility).
* **Evidence in Code**: `aetherspace/settings.py` (`DATABASE_URL`), `render.yaml`.

---

## ADR 03: Supabase Cloud Object Storage for Binary Files

* **Status**: Accepted
* **Date**: Phase 1
* **Context**: Render web services run on ephemeral filesystems where uploaded files are deleted upon dyno restarts. Storing binary assets directly inside PostgreSQL creates database bloat and degrades query performance.
* **Decision**: Store only file metadata (name, MIME type, size, checksum, uploader) in PostgreSQL (`StoredFile`, `MessageAttachment`, `TaskAttachment`). Store the actual binary payloads in Supabase Storage (`aetherspace-storage` bucket) via authenticated server-side REST calls.
* **Consequences**:
  - Database remains lean and fast.
  - Render restarts do not affect user uploads.
  - Secret service keys are never exposed to browser JavaScript.
* **Evidence in Code**: `files/models.py`, `chat/models.py`, `core/supabase_storage.py`.

---

## ADR 04: Authoritative Contributor ID (#####C) & Custom User Model

* **Status**: Accepted
* **Date**: Phase 1
* **Context**: AetherSpace requires human-friendly, collision-safe member identification across multi-workspace agile operations, alongside strict separation between system approval status and functional workspace roles.
* **Decision**: Implement a custom `User` model inheriting from `AbstractUser` with a UUID primary key, a unique 5-digit Contributor ID formatted as `#####C` (e.g. `26457C`), and an independent `approval_status` field (Pending, Approved, Rejected, Suspended).
* **Consequences**:
  - Users log in using their Contributor ID or Email.
  - Self-registered users default to `PENDING` until approved by a platform Administrator.
* **Evidence in Code**: `accounts/models.py` (`User`, `generate_unique_contributor_id()`), `accounts/views.py`.

---

## ADR 05: Workspace-Scoped Multi-Tenancy with Server-Side Isolation

* **Status**: Accepted
* **Date**: Phase 1
* **Context**: Teams belong to isolated workspaces. Data leaks between workspaces represent a catastrophic security failure. UI-only hiding of resources is insufficient.
* **Decision**: Every entity (Task, Bug, Channel, Meeting, File, CalendarEvent, TimeEntry) is strictly foreign-keyed to `Workspace`. Access to all workspace views is guarded by the `@workspace_member_required` decorator, which resolves the workspace by slug and verifies active `WorkspaceMembership`.
* **Consequences**:
  - URL tampering or cross-workspace slug substitution returns `403 Forbidden` or `404 Not Found`.
  - Non-members are directed to an in-app `WorkspaceAccessRequest` flow rather than exposing workspace contents.
* **Evidence in Code**: `workspaces/decorators.py`, `workspaces/models.py`, `meetings/views.py`.

---

## ADR 06: Hybrid WebRTC Architecture via Jitsi Meet External API

* **Status**: Accepted (Hardened in Phase 3 / 3.1)
* **Date**: Phase 2 / Phase 3
* **Context**: Building and hosting a custom WebRTC SFU/MCU (Selective Forwarding Unit) media bridge on free-tier infrastructure causes severe bandwidth and CPU exhaustion for multi-party calls (>2 peers).
* **Decision**:
  - **AetherSpace Application Layer**: Manages authentication, workspace RBAC, `Meeting` records, attendance tracking, 1-on-1 `CallSession` state machines, ringtone synthesis, and Obsidian `#09090b` UI shell.
  - **Jitsi Meet Media Engine**: Manages audio, video, screen sharing, multi-party SFU routing, bandwidth adaptation, and device selection via the Jitsi IFrame API.
* **Consequences**:
  - Eliminates server CPU/bandwidth load for video conferencing.
  - Free-tier sustainable.
  - Unauthenticated embeds on public `meet.jit.si` enforce an 8x8 5-minute timeout; production migration pathway uses 8x8 JaaS (Jitsi as a Service) with RS256 JWTs or self-hosted Docker Jitsi Meet.
* **Evidence in Code**: `templates/meetings/meeting_room.html`, `meetings/views.py`, `meetings/consumers.py`.

---

## ADR 07: Unified Real-Time Signaling via Django Channels 4 & Daphne

* **Status**: Accepted
* **Date**: Phase 2
* **Context**: Real-time team messaging (Chat) and instant 1-on-1 calling (Meet Hub) require persistent bidirectional communication without expensive HTTP polling loops.
* **Decision**: Run Daphne as the primary ASGI application server. Route WebSocket connections via Django Channels 4 to `ChatConsumer`, `GlobalCallConsumer`, and `MeetingSignalingConsumer`.
* **Consequences**:
  - In-chat messaging delivers instantaneously.
  - `GlobalCallConsumer` delivers incoming call ringtones and modals across *any* page of the platform that the recipient currently has open.
  - In development without Redis, `InMemoryChannelLayer` is used; in production, `channels-redis` can be attached via `REDIS_URL`.
* **Evidence in Code**: `aetherspace/asgi.py`, `meetings/routing.py`, `chat/routing.py`, `meetings/consumers.py`.

---

## ADR 08: Operational Gating via ModuleStatus Feature Flags

* **Status**: Accepted
* **Date**: Phase 2 / Phase 3
* **Context**: Features undergoing active development, hardening, or pending manual verification must not be released to normal workspace contributors.
* **Decision**: Maintain a database-backed `ModuleStatus` model in `core` controlling module availability (`AVAILABLE`, `MAINTENANCE`, `COMING_SOON`). Enforce status server-side in views (e.g. `check_meetings_maintenance`) and render informative banners in UI navigation.
* **Consequences**:
  - Meet Hub is safely gated under `Coming Soon` until two-user live manual verification is completed by the project owner.
  - Platform Administrators can test gated modules without releasing them prematurely to contributors.
* **Evidence in Code**: `core/models.py` (`ModuleStatus`), `meetings/views.py` (`check_meetings_maintenance()`).
