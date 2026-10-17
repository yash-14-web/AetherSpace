# AetherSpace Environment Variables Reference

This document provides the authoritative inventory of all configuration variables supported across AetherSpace.

---

## 1. Environment Variables Inventory

| Variable Name | Description | Default Value | Environment | Required | Secret? | Notes |
|---|---|---|---|:---:|:---:|---|
| **`DJANGO_SECRET_KEY`** | Cryptographic signing key for sessions, CSRF, and tokens. | `None` (must be provided) | All | **Yes** | **YES** | Generate a unique random string in production. |
| **`DJANGO_DEBUG`** | Toggles verbose error traces and development behavior. | `True` (dev) / `False` (prod)| All | No | No | Must be `False` in production to prevent stack trace leaks. |
| **`ALLOWED_HOSTS`** | Comma-separated list of valid Host header hostnames. | `localhost,127.0.0.1,.onrender.com` | All | **Yes** | No | Protects against HTTP Host header attacks. |
| **`CSRF_TRUSTED_ORIGINS`**| Comma-separated list of trusted origins for CSRF POST requests. | `https://*.onrender.com` | Prod | **Yes** | No | Must include `https://` scheme. |
| **`DATABASE_URL`** | PostgreSQL connection string (`postgresql://...`). | `None` | All | **Yes** | **YES** | Points to Supabase PostgreSQL (`sslmode=require`). |
| **`CONN_MAX_AGE`** | Maximum database connection lifetime in seconds. | `0` (transaction pooler) | Prod | No | No | Set to `0` when using Supabase PgBouncer pooler. |
| **`DB_CONNECT_TIMEOUT`** | Connection timeout in seconds. | `60` | Prod | No | No | Accommodates cold-start latency. |
| **`REDIS_URL`** | Redis connection URL for Channel layers (`redis://...`). | `None` (InMemory fallback) | Prod | No | **YES** | Attaches `channels-redis` for multi-worker ASGI. |
| **`SUPABASE_URL`** | Base URL for Supabase API (`https://<ref>.supabase.co`). | `None` | All | **Yes** | No | Used for cloud storage REST client. |
| **`SUPABASE_PUBLISHABLE_KEY`**| Supabase public anonymous API key. | `sb_publishable_placeholder` | All | **Yes** | No | Safe for client-side context if needed. |
| **`SUPABASE_SECRET_KEY`** | Supabase service-role secret key. | `sb_secret_placeholder` | All | **Yes** | **YES** | **Backend only**. Never expose to browser JavaScript. |
| **`SUPABASE_STORAGE_BUCKET`**| Supabase storage bucket name for file uploads. | `aetherspace-storage` | All | No | No | Defaults to `aetherspace-storage`. |
| **`JITSI_DOMAIN`** | Hostname of the Jitsi Meet server. | `meet.jit.si` | All | No | No | Active in `settings.py`. Switch to self-hosted domain or `8x8.vc` when JaaS is deployed. |
| **`JITSI_MEET_ENABLED`**| Master toggle for Jitsi conferencing interface. | `True` | All | No | No | Active in `settings.py`. |
| **`JITSI_APP_ID`** | Legacy placeholder string for App ID. | `""` | All | No | No | Active in `settings.py` as stub; not currently consumed in room naming or JWT logic. |
| **`JAAS_APP_ID`** | 8x8 JaaS Tenant / App ID (`vpaas-magic-cookie-...`). | `""` | Prod / Dev | No | No | Active in `settings.py`. Triggers JaaS mode when set. |
| **`JAAS_API_KEY_ID`** | 8x8 JaaS API Key Identifier (`kid` suffix). | `""` | Prod / Dev | No | No | Active in `settings.py`. Combined as `f"{JAAS_APP_ID}/{JAAS_API_KEY_ID}"` in JWT header. |
| **`JAAS_PRIVATE_KEY`** | RSA Private Key contents for signing JaaS RS256 JWTs. | `""` | Prod / Dev | No | **YES** | Multi-line PEM string (`\n` safe). Backend-only; never sent to client. |
| **`JAAS_PRIVATE_KEY_PATH`**| Local filepath to `.pk` private key file. | `""` | Prod / Dev | No | No | Filepath alternative to `JAAS_PRIVATE_KEY`. |
| **`JAAS_JWT_EXP_SECONDS`** | Validity duration of generated JaaS JWTs in seconds. | `7200` (2h) | Prod / Dev | No | No | Expiration claim (`exp = nbf + exp_seconds`). |
| **`EMAIL_BACKEND`** | Django email backend class. | `clean console` (dev) / `smtp` (prod)| All | No | No | Automatically defaults to SMTP when host, user, and password are configured; falls back to console in development. |
| **`EMAIL_HOST`** | Outbound SMTP server hostname. | `smtp-relay.brevo.com` | Prod / Dev | No | No | Brevo SMTP relay host. |
| **`EMAIL_PORT`** | Outbound SMTP server port. | `587` | Prod / Dev | No | No | Standard STARTTLS port. |
| **`EMAIL_USE_TLS`** | Whether to use STARTTLS encryption. | `True` | Prod / Dev | No | No | Enabled for port 587. |
| **`EMAIL_HOST_USER`** | SMTP username / login. | `b92dd5001@smtp-brevo.com` | Prod / Dev | No | No | Brevo SMTP account login identifier. |
| **`EMAIL_HOST_PASSWORD`**| SMTP master key / password. | `None` | Prod / Dev | No | **YES** | Brevo SMTP relay master key. Stored in local `.env` and Render secrets. |
| **`DEFAULT_FROM_EMAIL`** | Sender email address for system notifications. | `AetherSpace <yaswanthmunagoti@gmail.com>`| All | No | No | Displayed in email headers. |

---

## 2. Safe `.env.example` Template

```ini
# Django Core Settings
DJANGO_SECRET_KEY=your-django-secret-key-here
DJANGO_DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,.onrender.com

# Database Connection (Supabase PostgreSQL)
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@[YOUR-HOST]:5432/postgres?sslmode=require
CONN_MAX_AGE=0
DB_CONNECT_TIMEOUT=60

# Supabase Storage & Services
SUPABASE_URL=https://[YOUR-PROJECT-REF].supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_placeholder
SUPABASE_SECRET_KEY=sb_secret_placeholder
SUPABASE_STORAGE_BUCKET=aetherspace-storage

# Real-Time Conferencing (8x8 JaaS or self-hosted Jitsi)
# JITSI_DOMAIN=8x8.vc
# JAAS_APP_ID=vpaas-magic-cookie-xxxxxxxxxxxx
# JAAS_API_KEY_ID=xxxxxxxx
# JAAS_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIIEvg...-----END PRIVATE KEY-----"
# JAAS_PRIVATE_KEY_PATH=/path/to/jaas_private_key.pk
# JAAS_JWT_EXP_SECONDS=7200

# Outbound Email Delivery (Brevo SMTP)
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-brevo-smtp-login
EMAIL_HOST_PASSWORD=your-brevo-smtp-key
DEFAULT_FROM_EMAIL=AetherSpace <yaswanthmunagoti@gmail.com>
```
