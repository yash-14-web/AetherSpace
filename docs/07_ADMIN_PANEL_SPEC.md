# AetherSpace Admin Panel Specification

## Important

Admin pages are application administration pages, not a replacement for
cloud-provider consoles.

Do not fabricate infrastructure metrics.

## User Management

Show: - users - status - role - workspaces - last activity - actions

## User Details

Show: - profile - workspace memberships - roles - activity - security
events where authorized

## Roles & Permissions

Show role definitions and workspace-scoped permissions.

## Invitations

Show: - pending - accepted - expired - revoked

Allow resend/revoke where authorized.

## Workspace Management

Show: - workspace name - owner - member count - status - created date

## Workspace Requests

Show pending access/workspace requests.

## Member Management

Manage membership and workspace roles.

## Audit Logs

Show: - actor - action - object - workspace - timestamp

Provide filters and pagination.

## System Overview

Show real application metrics: - active users - workspaces - open
tasks - open bugs - recent activity - application health

## Integrations

Show configured integrations and connection status.

Never expose secret credentials.

## Storage & Files

Show real: - database usage if available - file storage usage if
available - file count - largest files - recent uploads

Do not claim unsupported quota values as live data. If a metric cannot
be queried, label it clearly.

## Security

Show: - authentication status - RLS status/configuration where known -
recent security events - failed login counts - permission-denied
events - session/security configuration

## Backup & Restore

Show only real backup/export capabilities.

If automatic backup is not configured: - explain that - provide manual
export instructions or an implemented export action

Never show fake backup history.

## Activity Monitor

Show AetherSpace application activity: - logins - workspace changes -
task actions - bug actions - file actions - admin actions

Do not pretend to monitor server CPU/memory unless actual monitoring has
been implemented.

## Performance

Prefer real application metrics: - request duration if collected - slow
operations - database query issues if instrumented - background job
status

Otherwise show: `Monitoring not configured`

## Alerts

Categories: - Critical - Warning - Info - Resolved

Examples: - critical bug - storage threshold - failed login pattern -
permission issue - background job failure

## Admin UI

Maintain the same AetherSpace theme and navigation.

Avoid enterprise observability dashboards that display fabricated
metrics.
