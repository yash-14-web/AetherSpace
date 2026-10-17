# AetherSpace Documentation & Knowledge Base

Welcome to the comprehensive, authoritative documentation for **AetherSpace**, a high-performance team collaboration and agile workspace platform built with Python, Django, PostgreSQL, and modern real-time WebSockets.

---

## Intended Audience

This documentation serves:
* **Project Owner & Product Managers**: System scope, feature taxonomy, release readiness, and capability registers.
* **Full-Stack Developers**: Architecture, request pipelines, services, database models, and coding standards.
* **QA & Test Engineers**: Automated test suites, manual verification matrices, and edge-case protocols.
* **DevOps & Infrastructure Engineers**: Render deployment, Supabase cloud configurations, and secret handling.
* **Future AI Coding Agents**: Authoritative architectural boundaries, gating policies, and verification records.

---

## Quick Navigation

```
docs/
├── 00_DOCUMENTATION_INDEX.md               <-- You are here
├── 01_PRODUCT_OVERVIEW.md                  Product vision, user personas, capabilities, and roadmap
├── 02_SYSTEM_ARCHITECTURE.md               High-level architecture, request flow, and runtime stack
├── 03_DATABASE_SCHEMA.md                   Complete data models, fields, indexes, and ER diagram
├── 04_AUTHENTICATION_AND_RBAC.md           Custom auth, Contributor ID (#####C), roles, and permissions
├── 05_MODULES/                             Deep-dive technical documentation for each application module
│   ├── 00_MODULE_INDEX.md                  Module directory, status register, and dependencies
│   ├── 01_WORKSPACES_AND_MEMBERS.md        Multi-tenancy, memberships, invitations, and access requests
│   ├── 02_DASHBOARDS.md                    Master Dashboard, Workspace Dashboard, and Admin Dashboard
│   ├── 03_TASK_MANAGEMENT.md               6-digit tasks (######), sprints, subtasks, and code reviews
│   ├── 04_BUG_MANAGEMENT.md                B-prefix bug triage (B-######), severities, and task links
│   ├── 05_CHAT_AND_MESSAGING.md            Real-time channels, 1-on-1 DMs, reactions, and attachments
│   ├── 06_MEET_HUB.md                      Standup conferencing, Jitsi media, 1-on-1 calling (GATED)
│   ├── 07_CALENDAR_AND_EVENTS.md           Work sessions, milestones, agendas, and cross-entity links
│   ├── 08_FILES_AND_ATTACHMENTS.md         Supabase cloud storage, folders, versioning, and external links
│   ├── 09_NOTIFICATIONS.md                 Cross-module event alerts, badges, and email audit logs
│   ├── 10_TIME_TRACKING.md                 Live running timers, manual entries, and sprint analytics
│   ├── 11_PROFILE_AND_PEOPLE.md            User directory, hover cards, status messages, and avatars
│   ├── 12_ADMINISTRATION.md                System console, user approvals, audit logs, and backups
│   └── 13_SETTINGS_AND_THEMES.md           Obsidian Dark & Clean Light modes, preferences, and security
├── 06_API_AND_WEBSOCKETS.md                HTTP views, JSON endpoints, and Django Channels consumers
├── 07_SECURITY_AND_PRIVACY.md              RBAC, CSRF, XSS, SSRF, SQLi defenses, and secret management
├── 08_LOCAL_DEVELOPMENT_SETUP.md           Windows & cross-platform step-by-step developer setup
├── 09_DEPLOYMENT_RENDER_AND_SUPABASE.md    Production Render web services & Supabase PostgreSQL configuration
├── 10_TESTING_AND_QA.md                    Automated test suites, manual verification, and QA checklists
├── 11_TROUBLESHOOTING.md                   Diagnoses and resolutions for common runtime failures
├── 12_RELEASE_HISTORY_AND_PHASES.md        Phase-by-phase implementation log and engineering milestones
├── 13_ENVIRONMENT_VARIABLES.md             Authoritative inventory of configuration settings
├── 14_GLOSSARY.md                          Platform terminology and domain definitions
├── 15_DOCUMENTATION_AUDIT.md               Verification audit, test execution records, and gap registers
├── diagrams/                               Mermaid architecture, data, and sequence source files (.mmd)
└── decisions/                              Architecture Decision Records (ADRs) & Release Policy
```

---

## Key System Facts & Authoritative Tech Stack

* **Backend Framework**: Python 3.12+ / 3.13 / Django 4.2 LTS / Django Channels 4
* **ASGI Server**: Daphne 4.x (HTTP + WebSockets)
* **Authoritative Database**: PostgreSQL 15+ hosted on Supabase Cloud (`DATABASE_URL`)
* **File Storage**: Supabase Cloud Object Storage (`aetherspace-storage` bucket)
* **Real-Time Conferencing**: Hybrid WebRTC via Jitsi Meet External API (`meet.jit.si` / `8x8.vc` JaaS)
* **Frontend Architecture**: Django Server-Side Templates + Tailwind CSS + Alpine.js
* **Identity Model**: Custom `accounts.User` with UUID primary keys and 5-digit Contributor IDs (`#####C`)
* **Release Gate**: Meet Hub is currently **Gated under Coming Soon** (`ModuleStatus.STATUS_COMING_SOON`) pending owner live two-user manual verification.

---

## Getting Started Fast

1. **New Developers**: Read [08_LOCAL_DEVELOPMENT_SETUP.md](file:///c:/Data%20Science%20and%20Gen%20Ai%20projects/AetherSpace/docs/08_LOCAL_DEVELOPMENT_SETUP.md) to launch the project locally.
2. **Architecture Review**: Read [02_SYSTEM_ARCHITECTURE.md](file:///c:/Data%20Science%20and%20Gen%20Ai%20projects/AetherSpace/docs/02_SYSTEM_ARCHITECTURE.md) and [decisions/ARCHITECTURE_DECISIONS.md](file:///c:/Data%20Science%20and%20Gen%20Ai%20projects/AetherSpace/docs/decisions/ARCHITECTURE_DECISIONS.md).
3. **Database & Models**: Read [03_DATABASE_SCHEMA.md](file:///c:/Data%20Science%20and%20Gen%20Ai%20projects/AetherSpace/docs/03_DATABASE_SCHEMA.md).
4. **Security & Permissions**: Read [04_AUTHENTICATION_AND_RBAC.md](file:///c:/Data%20Science%20and%20Gen%20Ai%20projects/AetherSpace/docs/04_AUTHENTICATION_AND_RBAC.md).
5. **Testing & QA**: Read [10_TESTING_AND_QA.md](file:///c:/Data%20Science%20and%20Gen%20Ai%20projects/AetherSpace/docs/10_TESTING_AND_QA.md).
6. **Release Policy**: Read [decisions/RELEASE_AND_VERIFICATION_POLICY.md](file:///c:/Data%20Science%20and%20Gen%20Ai%20projects/AetherSpace/docs/decisions/RELEASE_AND_VERIFICATION_POLICY.md).
