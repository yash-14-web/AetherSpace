# AetherSpace Security, Privacy & Compliance Architecture

This document audits the security controls, privacy safeguards, and vulnerability defenses implemented in AetherSpace.

---

## 1. Security Controls Verification Matrix

| Security Control | Implementation Mechanism | Verification Status | Source Reference |
|---|---|:---:|---|
| **Multi-Tenant Workspace Isolation** | Server-side `@workspace_member_required` decorator checks membership per slug on every request. | **Verified in Code** | `workspaces/decorators.py` |
| **CSRF Defense** | Django `CsrfViewMiddleware` enforces token on all `POST`/`PUT`/`DELETE` HTTP requests. | **Verified in Code** | `aetherspace/settings.py` |
| **Cross-Site Scripting (XSS)** | `bleach` and `markdown` sanitize chat and task descriptions; Django template auto-escaping enabled. | **Verified in Code** | `core/utils.py`, `tests/test_bad_tag_filter_and_xss_security.py` |
| **Open-Redirect Protection** | Redirect targets validated via `url_has_allowed_host_and_scheme` and `is_safe_external_url`. | **Verified in Code** | `tests/test_redirect_security.py`, `core/utils.py` |
| **SQL Injection Defense** | 100% Django ORM parameterized queries; raw SQL queries avoided. | **Verified in Code** | Project-wide ORM audit |
| **WebSocket Authentication** | `AuthMiddlewareStack` validates session cookie during WebSocket connection handshake. | **Verified in Code** | `aetherspace/asgi.py`, `meetings/consumers.py` |
| **WebSocket Channel Authorization** | Consumers check workspace and channel membership before admitting sockets to broadcast groups. | **Verified in Code** | `chat/consumers.py`, `meetings/consumers.py` |
| **File Upload Validation** | Strict file size enforcement against workspace quotas; extension and MIME type allowlists. | **Verified in Code** | `files/views.py`, `files/models.py` |
| **Zero Binary in DB** | Raw binaries streamed to Supabase Storage; PostgreSQL stores only metadata and SHA-256 hashes. | **Verified in Code** | `files/models.py`, `core/supabase_storage.py` |
| **Secret Management** | All credentials injected via OS environment variables; zero hardcoded secrets in repository. | **Verified in Code** | `aetherspace/settings.py`, `.env.example` |
| **Zero Secret Logging** | `AuditLog` and `EmailDeliveryLog` services explicitly omit passwords, tokens, and raw keys. | **Verified in Code** | `admin_panel/models.py`, `notifications/models.py` |
| **SSL Proxy Configuration** | `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` for Render reverse proxy. | **Verified in Code** | `aetherspace/settings.py` (lines 293–307) |
| **Production Cookie Security** | `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, `SECURE_BROWSER_XSS_FILTER = True`. | **Verified in Code** | `aetherspace/settings.py` |
| **Rate Limiting** | Reverse-proxy connection rate limiting on Render; in-app Redis throttling. | **Partially Verified** | Render infrastructure level |
| **Database Encryption at Rest** | AES-256 encryption at rest managed natively by Supabase Cloud. | **Requires Runtime Verification**| Supabase Managed Infrastructure |

---

## 2. Threat Modeling & Mitigation Analysis

### 2.1 Cross-Workspace Tenant Tampering (IDOR)
* **Threat**: A malicious user belonging to Workspace A modifies URL parameters (e.g. changing slug to `workspace-b` or task ID to `619347`) to read or manipulate another team's data.
* **Mitigation**:
  1. Every workspace route passes through `@workspace_member_required`.
  2. The decorator queries `WorkspaceMembership` matching `(workspace, request.user, status=ACTIVE)`.
  3. If no active membership exists and the user is not a platform superuser, Django terminates the pipeline with a `403 Forbidden` response.
  4. Task, bug, channel, and file lookups are always scoped: `workspace.tasks.get(task_code=...)`.

### 2.2 Malicious File Uploads & Quota Exhaustion
* **Threat**: Attacker uploads malicious `.exe` / `.sh` files or massive 500 MB files to exhaust cloud storage quotas.
* **Mitigation**:
  1. File size is checked before streaming to storage.
  2. Workspace active storage is computed (`Sum('size_bytes')`) and compared against `workspace.storage_quota_bytes`.
  3. File downloads proxy through authenticated views that verify workspace membership before issuing binary streams.
  4. External links are validated to ensure only safe `http://` and `https://` schemes are rendered, preventing `javascript:` injection.

### 2.3 Real-Time WebSocket Channel Snooping
* **Threat**: An unauthorized user connects to `ws/chat/c/<channel_id>/` and attempts to eavesdrop on private messages.
* **Mitigation**:
  1. `AuthMiddlewareStack` extracts `request.user` from the authenticated session.
  2. `ChatConsumer.connect()` queries `channel.has_member(user)`.
  3. If user is unauthorized, the socket immediately closes with code `4003` (Forbidden) prior to joining any Channels group.

### 2.4 Credentials & Service Role Isolation
* **Threat**: Supabase service-role secret keys or database passwords leaked into browser JavaScript bundles.
* **Mitigation**:
  1. Supabase service secrets (`SUPABASE_SECRET_KEY`) are utilized **strictly** in Python backend services (`core/supabase_storage.py`).
  2. Templates expose only public, non-sensitive tokens where required.
  3. Automated test `tests/test_supabase_database_security_lockdown.py` asserts that client templates contain zero service credentials.

---

## 3. Privacy & Data Handling Practices

1. **Password Hashing**: Enforces Django's `PBKDF2PasswordHasher` with SHA-256 and salt (minimum 600,000 iterations).
2. **Soft Deletion & Audit Trail**: Messages set `is_deleted = True`; files set `is_trashed = True`. Permanent deletions are restricted to Workspace Administrators.
3. **Session Termination**: Changing passwords immediately invalidates existing session cookies, forcing re-authentication across all active devices.
