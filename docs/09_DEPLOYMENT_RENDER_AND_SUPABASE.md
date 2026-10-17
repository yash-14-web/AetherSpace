# AetherSpace Deployment Guide: Render & Supabase

This document details the production deployment architecture, cloud service configurations, build pipelines, and free-tier sustainability strategies for AetherSpace.

---

## 1. Cloud Architecture Overview

AetherSpace is engineered to run sustainably on **free-tier friendly cloud services**:
- **Application Runtime**: Render Cloud Web Service (Free Tier, Oregon region).
- **Relational Database**: PostgreSQL 15+ hosted on Supabase Cloud.
- **Object Storage**: Supabase Cloud Object Storage (`aetherspace-storage` bucket).
- **Media Engine**: Jitsi Meet External API (currently configured to public `meet.jit.si`; `8x8.vc` JaaS integration is planned for a future release).

```mermaid
flowchart TB
    Browser["Client Browser (HTTPS/WSS)"]
    
    subgraph Render["Render Cloud (Free Tier)"]
        LoadBalancer["Render Edge Router & SSL"]
        DaphneContainer["Daphne Web Service ($PORT)"]
        WhiteNoise["WhiteNoise Static Engine"]
    end
    
    subgraph Supabase["Supabase Cloud Infrastructure"]
        PostgresDB[("PostgreSQL 15+ (Port 5432 / Pooler)")]
        StorageBucket[("Storage Bucket: aetherspace-storage")]
    end
    
    subgraph External["Third-Party Media"]
        JitsiEngine["Jitsi Meet Media SFU"]
    end

    Browser -->|HTTPS / WSS| LoadBalancer
    LoadBalancer --> DaphneContainer
    DaphneContainer --> WhiteNoise
    DaphneContainer -->|DATABASE_URL (SSL Required)| PostgresDB
    DaphneContainer -->|REST API (HTTPS)| StorageBucket
    Browser <-->|WebRTC Audio/Video| JitsiEngine
```

---

## 2. Render Web Service Configuration

The repository contains an authoritative `render.yaml` specification and `Procfile`:

### 2.1 `render.yaml` Parameters
* **Service Type**: `web`
* **Environment**: `python`
* **Region**: `oregon`
* **Plan**: `free`
* **Python Version**: `3.13.2`
* **Build Command**:
  ```bash
  pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate
  ```
* **Start Command**:
  ```bash
  daphne -b 0.0.0.0 -p $PORT aetherspace.asgi:application
  ```
* **Health Check Path**: `/`

### 2.2 Free-Tier Sleep & Spin-Down Behavior
* Render free instances spin down after 15 minutes of inactivity.
* The first incoming HTTP request wakes the instance, incurring an initial 30–50 second cold-start latency.
* Daphne initializes cleanly upon wake-up; SQLite is **prohibited**, ensuring that spin-downs cause zero data loss since all state lives in Supabase PostgreSQL.

---

## 3. Supabase Cloud Configuration

### 3.1 PostgreSQL Database Setup
1. Create a project in [Supabase](https://supabase.com).
2. Retrieve the connection string under **Project Settings -> Database**:
   - **Direct Connection**: `postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres?sslmode=require`
   - **Transaction Pooler (PgBouncer)**: Port `6543`.
3. In `aetherspace/settings.py`, `CONN_MAX_AGE` is set to `0` when running under transaction poolers to avoid connection pinning.
4. `DB_CONNECT_TIMEOUT` is configured to `60` seconds to accommodate network latency during cold starts.

### 3.2 Storage Bucket Setup
1. In the Supabase Dashboard, navigate to **Storage -> New Bucket**.
2. Name the bucket: `aetherspace-storage`.
3. Set bucket access to **Public** (or configure authenticated download proxies).
4. Configure Allowed MIME Types:
   `image/*, application/pdf, text/*, application/zip, application/msword, application/vnd.openxmlformats-officedocument.*`.
5. Max file size: 25 MB per object.

### 3.3 Security & API Keys
* `SUPABASE_URL`: `https://[PROJECT-REF].supabase.co`
* `SUPABASE_PUBLISHABLE_KEY`: Public anonymous token (safe for public context).
* `SUPABASE_SECRET_KEY`: Service-role secret key (used strictly in backend Python code; **never exposed to browser**).

---

## 4. Production Environment Variables (Render Dashboard)

Configure the following environment variables in the Render Dashboard under **Environment**:

| Variable Name | Example Value / Purpose | Required |
|---|---|:---:|
| `DJANGO_DEBUG` | `False` | Yes |
| `DJANGO_SECRET_KEY` | Generate via Render "Generate Value" | Yes |
| `ALLOWED_HOSTS` | `.onrender.com,localhost,127.0.0.1` | Yes |
| `CSRF_TRUSTED_ORIGINS` | `https://*.onrender.com` | Yes |
| `DATABASE_URL` | `postgresql://postgres:[PW]@[HOST]:5432/postgres?sslmode=require` | Yes |
| `CONN_MAX_AGE` | `0` | Yes |
| `DB_CONNECT_TIMEOUT` | `60` | Yes |
| `SUPABASE_URL` | `https://[REF].supabase.co` | Yes |
| `SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_...` | Yes |
| `SUPABASE_SECRET_KEY` | `sb_secret_...` | Yes |
| `SUPABASE_STORAGE_BUCKET`| `aetherspace-storage` | Yes |

---

## 5. Pre-Deployment Verification Checklist

Before triggering a deployment or git push:
- [ ] Run `python manage.py check --deploy`: Validates security headers, SSL proxy settings, and session cookies.
- [ ] Run `python manage.py test`: Verify 100% test pass rate across all apps.
- [ ] Confirm no unapplied migrations: `python manage.py makemigrations --check --dry-run`.
- [ ] Ensure `.env` is absent from Git staging: `git status --ignored`.
- [ ] Verify `render.yaml` buildCommand and startCommand match current Daphne configuration.

---

## 6. Post-Deployment Smoke Tests

Once Render reports "Service is live":
1. **Health Check**: Open `https://<your-app>.onrender.com/` — verifies SSL certificate and HTTP 200 response.
2. **Static Assets**: Inspect browser console — verifies WhiteNoise is serving CSS and JS with HTTP 200/304 without MIME errors.
3. **Authentication**: Log in with administrator account at `/auth/login/`.
4. **WebSocket Handshake**: Open a Chat channel or Meeting page — verify WebSocket handshake completes with HTTP 101 Switching Protocols.
5. **Database Persistence**: Create a test task `619347` — verify task persists after a page reload.
6. **File Storage**: Upload an avatar or task attachment — verify object appears in Supabase `aetherspace-storage` bucket.
