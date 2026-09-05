# AetherSpace Free-Tier Architecture

## Goal

Keep AetherSpace practical for a small 5--15 member team without
requiring paid infrastructure.

Free-tier constraints are provider-dependent and can change. Do not
promise that any external provider will remain free forever.

## Supabase

Current project design assumes: - PostgreSQL database for relational
data - Supabase Storage for files

Design around the current Free plan quotas rather than assuming
unlimited resources.

## Database Efficiency

To protect database capacity: - avoid duplicate denormalized blobs -
avoid storing binary files in PostgreSQL - paginate activity logs -
prune unnecessary high-volume events - avoid storing huge message
payloads - use appropriate indexes - keep audit metadata concise

## File Efficiency

Use Supabase Storage.

Application upload limits should be conservative.

Suggested defaults: - Avatar: 2 MB - Bug screenshot: 5 MB - Task
attachment: 10 MB - PDF/document: 10 MB - General file: 20 MB

Compress images when appropriate.

## Alerts

Build lightweight application alerts in Django.

Examples: - critical bug - overdue task - storage nearing limit -
repeated failed login - permission denial spike - failed background job

Do not implement expensive infrastructure monitoring unless explicitly
requested.

## Security

Security is implemented through: - Django auth - RBAC - object-level
authorization - CSRF - secure cookies - input validation - Supabase RLS
where applicable - environment secrets

## Backups

Do not assume the Free plan provides the same automated backup features
as paid plans.

Provide a documented manual/export backup procedure.

The Backup & Restore UI must not falsely claim that a full automatic
backup exists if the backend does not actually provide it.

## Monitoring

Application-level health checks are sufficient for this project.

Do not create fake CPU/memory/server graphs.

If a metric is not actually collected, show a clear status such as:
`Not configured`.

## Cost Principle

Prefer: 1. Django 2. PostgreSQL/Supabase Free 3. Supabase Storage Free
4. Browser APIs 5. Open-source/free services

before introducing any paid vendor.
