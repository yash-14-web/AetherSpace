# Module 12: Administration & System Governance

## 1. Purpose
Provides platform-level governance, user registration approval queues, immutable security audit logging (`AuditLog`), actionable system alerts, module feature gating, and database backup exports.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `admin_panel/models.py`, `admin_panel/views.py`, `admin_panel/backup_service.py`, `admin_panel/tests.py`.

## 3. Main User Workflows
1. **User Approval Queue (`/admin-panel/approvals/`)**:
   - Lists self-registered users with `approval_status == 'PENDING'`.
   - Admin reviews name, email, generated Contributor ID (`#####C`), and registration timestamp.
   - Admin clicks "Approve" (activates account) or "Reject" (denies account with feedback).
2. **Audit Log Inspection (`/admin-panel/audit-logs/`)**:
   - Filterable stream of all administrative actions, logins, permission grants, workspace modifications, and membership changes.
3. **Module Operational Status (`/admin-panel/modules/`)**:
   - Admin controls `ModuleStatus` feature flags: `AVAILABLE`, `MAINTENANCE`, `COMING_SOON`.
   - Controls public explanation banners and server-side view enforcement.
4. **Database Backup & Export (`/admin-panel/backups/`)**:
   - Triggers full database JSON / CSV export archives for disaster recovery compliance.
5. **System Alerts (`/admin-panel/alerts/`)**:
   - Tracks operational alerts across categories: `STORAGE`, `SECURITY`, `BUGS`, `ACCESS`, `SYSTEM`.

## 4. User Roles & Permissions
* **Platform Admin (`User.role == 'ADMIN'` or `is_superuser`)**: Sole authorized audience.
* **Non-Admin Users**: Accessing `/admin-panel/` strictly returns `403 Forbidden` via `admin_panel.permissions.admin_required`.

## 5. Pages & Templates
* `templates/admin_panel/dashboard.html`: Executive admin cockpit with key metrics.
* `templates/admin_panel/user_approvals.html`: Registration approval queue.
* `templates/admin_panel/audit_logs.html`: Filterable immutable audit table.
* `templates/admin_panel/module_status.html`: Feature gate toggles.
* `templates/admin_panel/backup_management.html`: Backup generation and download console.

## 6. URLs, Views, Services & Models
* **URLs**: `admin_panel/urls.py` (`dashboard`, `user_approvals`, `audit_logs`, `module_management`, `backup_export`).
* **Views**: `admin_panel/views.py` (`dashboard_view`, `approve_user_api`, `module_status_view`).
* **Services**: `admin_panel/services.py`, `admin_panel/backup_service.py`.
* **Models**: `AuditLog`, `AdminAlert`, `core.ModuleStatus`.

## 7. Business Rules & Invariants
* Strict Audit Immutability: `AuditLog` records cannot be updated or deleted through the application interface.
* Zero Secret Logging: Model docstring and service strictly forbid recording passwords, session tokens, API keys, or raw secrets in `AuditLog.metadata`.
* Superuser Exemption: Django superusers bypass approval queues automatically.

## 8. Database Relationships
* `AuditLog` optionally references actor `accounts.User` and `workspaces.Workspace` (SET_NULL).
* `AdminAlert` optionally references resolved_by `accounts.User` and `workspaces.Workspace` (SET_NULL).

## 9. API & WebSocket Interactions
* `POST /admin-panel/approvals/<uuid:user_id>/decide/`: Asynchronous user approval/rejection API.
* `POST /admin-panel/modules/<module_key>/update/`: Feature gate toggle API.

## 10. Notifications & Integrations
* Dispatches `ACCOUNT_APPROVED` or `ACCOUNT_STATUS` notifications upon admin decision.

## 11. Error States & Edge Cases
* Non-admin user visiting `/admin-panel/` -> `403 Forbidden`.
* Re-approving an already approved user -> Safe no-op returning `400 Bad Request: "User already processed"`.

## 12. Tests & Verification Evidence
* `admin_panel/tests.py`: 100% passing tests covering admin authorization, user approvals, audit log creation, and backup exports.

## 13. Known Limitations
* Automated database restores through the web UI are disabled for safety; restores are performed via `psql` command line tools.

## 14. Future Work
* Automated daily pg_dump cron jobs dispatched to encrypted S3 cloud buckets.
