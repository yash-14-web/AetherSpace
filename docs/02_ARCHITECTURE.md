# AetherSpace Technical Architecture

## High-Level

``` text
Browser
  |
  | HTTPS
  v
Django
  |
  +-- core
  +-- accounts
  +-- workspaces
  +-- tasks
  +-- bugs
  +-- chat
  +-- meetings
  +-- calendar
  +-- files
  +-- notifications
  |
  +--> Supabase PostgreSQL
  |
  +--> Supabase Storage
  |
  +--> Jitsi/WebRTC-compatible meeting service
```

## Django Responsibility

Django owns: - routing - business rules - forms - server-side
permissions - HTML rendering - transactions - validation - audit event
generation - application notifications

## Database Responsibility

PostgreSQL stores relational/application data.

Do not store uploaded binary files in database columns.

## Storage Responsibility

Supabase Storage stores: - avatars - task attachments - bug
screenshots - project documents - chat file attachments

Store only metadata and storage paths in PostgreSQL.

## Services

Use a service layer when business logic becomes complex.

Example:

``` text
tasks/
  services.py
bugs/
  services.py
workspaces/
  services.py
notifications/
  services.py
```

Do not put large amounts of business logic directly inside templates.

## Query Performance

Use: - `select_related` - `prefetch_related` - indexes - pagination -
aggregation where appropriate

Avoid N+1 queries.

## Security

Use: - Django CSRF - secure cookies in production - environment
variables - server-side permission checks - workspace membership
checks - object-level authorization - Supabase RLS where Supabase is
accessed directly - strict upload validation - safe markdown rendering -
output escaping

Never expose secret/service-role keys to the frontend.

## Environment

Use `.env` locally and platform environment variables in deployment.

Never commit: - passwords - API keys - Supabase service keys - Django
secret key - database URLs containing credentials
