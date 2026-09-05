# AetherSpace --- Antigravity Master Instructions

## Mission

Build AetherSpace, a high-performance team collaboration and agile
workspace platform for teams of approximately 5--15 members.

You are acting as a Senior Full-Stack Django Developer, UI/UX Engineer,
Database Architect, QA Engineer, and pragmatic DevOps engineer.

The implementation MUST follow the product blueprint in this repository.
Do not invent a different product direction unless explicitly instructed
by the project owner.

## Core Stack

-   Backend: Python + Django
-   Frontend: Django templates + HTML5 + Tailwind CSS + Alpine.js
-   Database: PostgreSQL hosted by Supabase
-   File storage: Supabase Storage
-   Authentication: Django authentication unless the implementation
    explicitly requires Supabase Auth; keep one authoritative user
    identity model
-   Meetings: WebRTC/Jitsi-compatible integration
-   Version control: Git + GitHub
-   Deployment target: free-tier friendly

## Product Principle

AetherSpace should feel like a polished lightweight alternative to a
combination of Jira, Slack, Notion/Drive, and Meet for small teams.

Prioritize: 1. Clean UX 2. Fast page loads 3. Simple navigation 4.
Strong workspace isolation 5. RBAC 6. Maintainable Django architecture
7. Free-tier sustainability 8. Accessibility 9. Responsive design 10.
Security

Avoid unnecessary enterprise infrastructure.

## Mandatory Rules

1.  Read every file in `docs/` before implementing a major module.
2.  Do not replace Django templates with React unless explicitly
    requested.
3.  Do not introduce a paid service when a free/local alternative
    exists.
4.  Do not store uploaded binary files inside PostgreSQL.
5.  Store file metadata in PostgreSQL and files in Supabase Storage.
6.  Never expose Supabase service-role/secret credentials to browser
    JavaScript.
7.  Use environment variables for all secrets.
8.  Enforce workspace-level permissions server-side. Never rely only on
    hidden UI elements.
9.  Use Django forms/model validation for all important input.
10. Use CSRF protection for state-changing requests.
11. Use pagination for potentially large lists.
12. Use indexes for common filters and foreign keys.
13. Use transactions for multi-table operations that must be atomic.
14. Avoid N+1 queries; use `select_related` and `prefetch_related`.
15. Do not create fake functionality just to make a page look complete.
16. If a feature cannot be implemented with the current free-tier
    architecture, document the limitation instead of silently
    substituting behavior.
17. Preserve the existing design system across every page.
18. Do not create dense side-by-side dashboard grids for ordinary
    application pages; prefer vertically stacked sections/cards as
    specified by the blueprint.
19. Every page must have loading, empty, validation/error, and
    permission-denied states where applicable.
20. Keep URLs, model names, template names, and app responsibilities
    consistent.

## Required Django Apps

Create modular apps:

-   `core`
-   `workspaces`
-   `tasks`
-   `bugs`
-   `chat`
-   `meetings`

Additional apps may be created only when there is a clear
responsibility, such as `notifications`, `files`, `calendar`, or
`accounts`.

## Product Hierarchy

A user can belong to multiple workspaces.

Workspace roles:

-   Admin
-   Manager
-   Contributor

Managers can work across multiple workspaces and therefore have a Master
Dashboard.

The platform has:

-   Master Dashboard
-   Workspace Dashboard
-   Admin Dashboard

## ID Rules

Tasks use a six-digit numeric ID:

`619347`

Bugs use:

`B-882316`

IDs must be generated safely and must not collide.

Do not use a naive random-number-only implementation without collision
handling.

## Theme

Support Light and Dark modes.

Dark: - Background: `#09090b` / `#0f172a` - Cards: `#18181b` /
`#1e293b` - Primary text: `#f4f4f5` - Secondary text: `#a1a1aa` -
Accent: `#2563eb`

Light: - Background: `#f8fafc` / `#f4f4f5` - Cards: `#ffffff` - Borders:
`#e2e8f0` - Primary text: `#0f172a` - Secondary text: `#64748b`

Use Tailwind dark-mode classes consistently.

## Navigation

Global rail: - Dashboard - Time Tracking - Calendar - Files - Meet Hub -
Chat - Notifications - Profile - Settings - Theme Toggle

Workspace tree: - Workspace - Team - Dashboard - Project Details - Chat

Universal header: - Search - Notifications - User profile/dropdown

## Definition of Done

A feature is complete only when:

-   Model/schema is implemented
-   Migration is created
-   URL is registered
-   View/service logic is implemented
-   Template is implemented
-   Forms/validation are implemented
-   Permission checks are implemented
-   Empty/loading/error states exist
-   Mobile layout is considered
-   Tests cover critical behavior
-   No obvious N+1 queries exist
-   No secrets are committed
-   Documentation is updated
-   Git diff is clean and understandable

## Implementation Behavior

Work in small, verifiable increments.

Before changing a shared component, inspect all pages using it.

After each major module: 1. Run migrations. 2. Run tests. 3. Run Django
checks. 4. Inspect relevant pages. 5. Fix regressions. 6. Update
documentation.

Do not stop after generating UI mockups. Build the actual working Django
application.

## Final Goal

The final project must be a coherent, runnable AetherSpace application
matching the supplied blueprint rather than a collection of disconnected
demo pages.
