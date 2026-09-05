# AetherSpace Security and RBAC

## Roles

### Platform Admin

Full platform control.

Can: - manage users - manage workspaces - manage roles - view audit
logs - view application alerts - view storage usage - configure platform
settings

### Workspace Admin

Full control within assigned workspace.

Can: - manage workspace members - manage workspace settings - manage
tasks and bugs - manage channels/files/meetings

### Manager

Can: - view assigned workspaces - create/manage tasks - manage project
activity - raise/manage bugs - use collaboration features

### Contributor

Can: - view permitted workspace content - work on assigned tasks - raise
bugs - chat - attend meetings - upload permitted files

## Authorization Rules

Permissions must be checked server-side.

Example:

``` python
if not membership:
    raise PermissionDenied
```

Never assume that because a user cannot see a button they cannot call
the endpoint.

## Workspace Isolation

Every workspace-scoped object must be checked against the current
workspace membership.

Never fetch an object by ID and return it without verifying workspace
access.

## RLS

If the application directly accesses Supabase from a client-side
context, use Row Level Security.

If Django is the only database access layer, still maintain strong
Django authorization and keep Supabase service credentials server-side.

## Secrets

Environment variables: - `DJANGO_SECRET_KEY` - `DATABASE_URL` -
`SUPABASE_URL` - `SUPABASE_ANON_KEY` - `SUPABASE_SERVICE_ROLE_KEY` only
if actually needed server-side - meeting provider credentials if
applicable

Never place secret values in templates, JavaScript bundles, Git,
screenshots, or documentation.

## File Security

Validate: - extension - MIME type - file size

Do not trust filename extension alone.

Generate safe storage paths.

Prevent users from downloading files from workspaces they cannot access.

## Markdown

Task/bug markdown must be sanitized before rendering.

Never render raw user-supplied HTML as trusted HTML.

## Authentication

Use secure password hashing.

Use: - CSRF protection - secure session cookies - login throttling/rate
limiting where practical - password reset tokens with expiry -
verification tokens with expiry

## Audit Events

Record important events: - login - failed login - password change - role
change - workspace creation - member added/removed - permission denied -
task/bug deletion - security settings changes

Do not log passwords, tokens, or secrets.
