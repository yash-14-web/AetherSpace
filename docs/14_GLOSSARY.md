# AetherSpace Glossary & Terminology Register

This glossary defines domain terms, acronyms, and identifiers used across the AetherSpace platform.

---

## 1. Identifiers & Entity Formats

* **Contributor ID (`#####C`)**: A unique 6-character identifier consisting of exactly 5 numeric digits followed by an uppercase `C` (e.g. `26457C`, `91823C`). Generated cryptographically upon registration; serves as the permanent human identity for logins, mentions, and audit logs.
* **Task Code (`######`)**: A unique 6-digit numeric identifier (e.g. `619347`) assigned to every agile task. Enforces blueprint ID rules with collision handling.
* **Bug Code (`B-######`)**: A unique defect identifier prefixed with `B-` followed by 6 numeric digits (e.g. `B-882316`).
* **Code Review Code (`CR-######`)**: A Pull Request review request identifier tied to a parent task (e.g. `CR-619347`).
* **Meeting Code (`meet-xxxx-xxxx`)**: A human-friendly meeting room identifier (e.g. `meet-k7xp-2m9q`).

---

## 2. Multi-Tenancy & Access Control

* **Workspace**: The fundamental multi-tenant isolation unit in AetherSpace. All tasks, bugs, channels, meetings, files, and time tracking logs are strictly scoped to a Workspace.
* **Workspace Membership**: An association between a `User` and a `Workspace` specifying their role (`ADMIN`, `MANAGER`, `CONTRIBUTOR`) and functional title (e.g. "Lead Backend Engineer").
* **Seat Limit**: The maximum allowable active member seats in a workspace (defaults to 15 members).
* **Storage Quota**: The total storage capacity allocated to a workspace for binary assets in Supabase Storage (defaults to 50 MB).
* **Global Access Request**: A formal in-app petition submitted by a Contributor requesting temporary elevated permissions (e.g. `task.delete`, `file.purge`) with an urgency level and requested duration.
* **Temporary Access Grant**: A time-bounded permission record issued by an Administrator granting single-action privilege elevation without permanent role modification.

---

## 3. Real-Time Collaboration & Conferencing

* **CallSession**: An authoritative server-side state machine record managing 1-on-1 and in-chat call lifecycles through states: `RINGING`, `ACCEPTED`, `CONNECTED`, `DECLINED`, `MISSED`, `CANCELLED`, `ENDED`, `FAILED`.
* **GlobalCallConsumer**: A Django Channels WebSocket consumer mounted at `ws/calls/global/` across all authenticated pages to deliver real-time incoming ringtones and modal alerts.
* **Jitsi Meet External API**: A JavaScript interface (`external_api.js`) used to embed and control Jitsi video conferencing iframes inside AetherSpace.
* **JaaS (8x8 Jitsi as a Service)**: 8x8's enterprise cloud conferencing platform that utilizes RS256-signed JWTs to unlock unlimited meeting durations and automatic moderator claiming.
* **ModuleStatus**: A database-backed feature gating model in `core` allowing Administrators to toggle module availability between `AVAILABLE`, `MAINTENANCE`, and `COMING_SOON`.
* **Operational Gating**: A strict server-side policy where features under active development (e.g. Meet Hub) are restricted from normal workspace contributors until two-user manual verification succeeds.

---

## 4. Agile Engineering & Dashboards

* **Master Dashboard**: A consolidated, cross-workspace dashboard providing managers and multi-team contributors with high-level visibility over all assigned tasks, open defects, and sprint cadences.
* **Workspace Tactical Dashboard**: The daily operational cockpit for a single workspace, featuring active sprint burndowns, quick task cards, critical defect lists, and today's schedule.
* **Admin Dashboard**: The platform governance console available strictly to platform Administrators (`/admin-panel/`) for user approvals, audit log analysis, and system backups.
* **AuditLog**: An immutable, append-only security log recording administrative actions, membership modifications, and login events across the platform with zero sensitive secrets.
* **TimeEntry**: A work tracking record capturing elapsed sprint labor via live stopwatch timers or manual entries attributed to specific 6-digit tasks.
* **StoredFile**: A metadata record in PostgreSQL pointing to raw binary assets stored securely in Supabase Cloud Object Storage or external cloud URLs.
