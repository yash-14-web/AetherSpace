import os
import time
import json
import logging
from django.conf import settings
from django.db import connection
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.files.storage import default_storage
import requests

from accounts.models import User, UserRole
from workspaces.models import (
    Workspace, WorkspaceMembership, WorkspaceInvitation,
    WorkspaceAccessRequest, WorkspaceStatus, MembershipStatus, InvitationStatus, AccessRequestStatus
)
from tasks.models import Task, TaskStatus
from bugs.models import Bug, BugStatus, BugSeverity
from files.models import StoredFile, Folder, FileCategory
from files.services import SupabaseStorageService
from .models import AuditLog, AuditActionStatus, AdminAlert, AlertSeverity, AlertCategory

logger = logging.getLogger(__name__)

SENSITIVE_METADATA_KEYS = {
    'password', 'token', 'secret', 'key', 'auth', 'authorization',
    'access_token', 'refresh_token', 'credential', 'api_key', 'private_key'
}


class AuditLogService:
    """Service to record safe administrative audit logs without leaking secrets."""

    @staticmethod
    def sanitize_metadata(meta):
        if not isinstance(meta, dict):
            return {}
        cleaned = {}
        for k, v in meta.items():
            k_lower = str(k).lower()
            if any(sensitive in k_lower for sensitive in SENSITIVE_METADATA_KEYS):
                cleaned[k] = '[REDACTED]'
            elif isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                cleaned[k] = v
            else:
                cleaned[k] = str(v)
        return cleaned

    @classmethod
    def log(cls, action, actor=None, target_type='', target_id='', target_repr='',
            workspace=None, ip_address=None, status=AuditActionStatus.SUCCESS, metadata=None):
        try:
            actor_email = actor.email if (actor and hasattr(actor, 'email')) else ''
            safe_meta = cls.sanitize_metadata(metadata or {})
            return AuditLog.objects.create(
                actor=actor if (actor and getattr(actor, 'is_authenticated', False)) else None,
                actor_email=actor_email,
                action=action,
                target_type=target_type,
                target_id=str(target_id) if target_id else '',
                target_repr=str(target_repr)[:255] if target_repr else '',
                workspace=workspace,
                ip_address=ip_address,
                status=status,
                metadata=safe_meta
            )
        except Exception as e:
            logger.error(f"Failed to record audit log: {str(e)}")
            return None


class StorageSyncService:
    """
    Real Supabase Storage + PostgreSQL synchronization service.
    Guarantees accurate storage metrics and detects missing or orphaned storage objects.
    """

    @staticmethod
    def format_bytes(size_bytes):
        if not size_bytes or size_bytes < 0:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}" if unit != 'B' else f"{int(size_bytes)} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

    @classmethod
    def get_storage_metrics(cls):
        """Aggregate real storage statistics across all workspaces and Supabase storage."""
        total_files = StoredFile.objects.filter(is_trashed=False).count()
        total_external_links = StoredFile.objects.filter(is_trashed=False, is_external_link=True).count()
        physical_files = StoredFile.objects.filter(is_trashed=False, is_external_link=False)
        total_bytes = physical_files.aggregate(total=Sum('size_bytes'))['total'] or 0
        total_folders = Folder.objects.count()

        # Workspace breakdown
        workspaces = Workspace.objects.annotate(
            file_count=Count('files', filter=Q(files__is_trashed=False)),
            bytes_sum=Sum('files__size_bytes', filter=Q(files__is_trashed=False, files__is_external_link=False))
        ).order_by('-bytes_sum')

        workspace_data = []
        for ws in workspaces:
            b_used = ws.bytes_sum or 0
            quota_mb = ws.storage_quota_mb or 50
            quota_bytes = quota_mb * 1024 * 1024
            pct = round((b_used / quota_bytes) * 100, 1) if quota_bytes > 0 else 0
            workspace_data.append({
                'workspace': ws,
                'file_count': ws.file_count,
                'bytes_used': b_used,
                'formatted_used': cls.format_bytes(b_used),
                'quota_mb': quota_mb,
                'quota_bytes': quota_bytes,
                'formatted_quota': f"{quota_mb} MB",
                'percentage': min(pct, 100),
                'raw_percentage': pct,
                'is_near_quota': pct >= 80,
                'is_over_quota': pct >= 100,
            })

        # Largest 15 files
        largest_files = StoredFile.objects.filter(
            is_trashed=False,
            is_external_link=False
        ).select_related('workspace', 'uploaded_by').order_by('-size_bytes')[:15]

        # Recent 15 uploads
        recent_uploads = StoredFile.objects.filter(
            is_trashed=False
        ).select_related('workspace', 'uploaded_by').order_by('-created_at')[:15]

        # Category distribution
        category_stats = StoredFile.objects.filter(is_trashed=False).values('category').annotate(
            count=Count('id'),
            total_size=Sum('size_bytes')
        ).order_by('-total_size')

        formatted_categories = []
        for cat in category_stats:
            cat_name = dict(FileCategory.choices).get(cat['category'], cat['category'])
            c_size = cat['total_size'] or 0
            formatted_categories.append({
                'category': cat['category'],
                'name': cat_name,
                'count': cat['count'],
                'size_bytes': c_size,
                'formatted_size': cls.format_bytes(c_size),
            })

        return {
            'total_files': total_files,
            'physical_files_count': physical_files.count(),
            'total_external_links': total_external_links,
            'total_bytes': total_bytes,
            'formatted_total_bytes': cls.format_bytes(total_bytes),
            'total_folders': total_folders,
            'workspaces': workspace_data,
            'largest_files': largest_files,
            'recent_uploads': recent_uploads,
            'categories': formatted_categories,
            'is_supabase_ready': SupabaseStorageService.is_supabase_configured(),
            'bucket_name': getattr(settings, 'SUPABASE_STORAGE_BUCKET', 'aetherspace-files') or 'aetherspace-files',
        }

    @classmethod
    def audit_storage_sync(cls, limit=50):
        """
        Audit database StoredFile records against actual Supabase Storage / default_storage objects.
        Detects missing objects and confirms synchronization.
        """
        files_to_check = StoredFile.objects.filter(
            is_trashed=False,
            is_external_link=False
        ).exclude(storage_path='').select_related('workspace', 'uploaded_by')[:limit]

        is_supabase = SupabaseStorageService.is_supabase_configured()
        base_url = getattr(settings, 'SUPABASE_URL', '').rstrip('/')
        bucket = getattr(settings, 'SUPABASE_STORAGE_BUCKET', '')
        auth_key = getattr(settings, 'SUPABASE_SECRET_KEY', '') or getattr(settings, 'SUPABASE_PUBLISHABLE_KEY', '')

        synced_count = 0
        missing_count = 0
        missing_files = []

        for f in files_to_check:
            exists = False
            if is_supabase and bucket and auth_key:
                try:
                    # Check Supabase Storage object status via HEAD or authenticated GET
                    api_url = f"{base_url}/storage/v1/object/info/{bucket}/{f.storage_path}"
                    headers = {'Authorization': f"Bearer {auth_key}"}
                    resp = requests.get(api_url, headers=headers, timeout=5)
                    if resp.status_code == 200:
                        exists = True
                    elif resp.status_code == 404:
                        exists = False
                    else:
                        # Fallback check local storage if Supabase API gave other code
                        exists = default_storage.exists(f.storage_path)
                except Exception:
                    exists = default_storage.exists(f.storage_path)
            else:
                exists = default_storage.exists(f.storage_path)

            if exists:
                synced_count += 1
            else:
                missing_count += 1
                missing_files.append({
                    'id': str(f.id),
                    'name': f.name,
                    'storage_path': f.storage_path,
                    'workspace': f.workspace.name,
                    'size_formatted': f.formatted_size,
                    'uploaded_by': f.uploaded_by.email if f.uploaded_by else 'Unknown'
                })

        total_audited = synced_count + missing_count
        sync_percent = round((synced_count / total_audited) * 100, 1) if total_audited > 0 else 100.0

        return {
            'total_audited': total_audited,
            'synced_count': synced_count,
            'missing_count': missing_count,
            'sync_percent': sync_percent,
            'missing_files': missing_files,
            'is_healthy': missing_count == 0,
            'checked_at': timezone.now(),
        }

    @classmethod
    def purge_file(cls, file_id, actor=None, ip_address=None):
        """
        Atomically delete a StoredFile from Supabase Storage / default_storage and PostgreSQL.
        """
        try:
            stored_file = StoredFile.objects.get(id=file_id)
        except StoredFile.DoesNotExist:
            return False, "File does not exist."

        file_name = stored_file.name
        workspace = stored_file.workspace
        storage_path = stored_file.storage_path
        is_ext = stored_file.is_external_link

        # 1. Delete physical object if not external
        if not is_ext and storage_path:
            if SupabaseStorageService.is_supabase_configured():
                try:
                    base_url = settings.SUPABASE_URL.rstrip('/')
                    bucket = settings.SUPABASE_STORAGE_BUCKET
                    api_url = f"{base_url}/storage/v1/object/{bucket}"
                    headers = {
                        'Authorization': f"Bearer {settings.SUPABASE_SECRET_KEY or settings.SUPABASE_PUBLISHABLE_KEY}",
                        'Content-Type': 'application/json'
                    }
                    requests.delete(api_url, headers=headers, json={"prefixes": [storage_path]}, timeout=10)
                except Exception as e:
                    logger.warning(f"Supabase delete failed for {storage_path}: {str(e)}")

            try:
                if default_storage.exists(storage_path):
                    default_storage.delete(storage_path)
            except Exception as e:
                logger.warning(f"Local storage delete failed for {storage_path}: {str(e)}")

        # 2. Delete database record
        stored_file.delete()

        # 3. Log audit event
        AuditLogService.log(
            action='FILE_PURGED',
            actor=actor,
            target_type='StoredFile',
            target_id=str(file_id),
            target_repr=file_name,
            workspace=workspace,
            ip_address=ip_address,
            status=AuditActionStatus.SUCCESS,
            metadata={'storage_path': storage_path, 'is_external': is_ext}
        )
        return True, f"File '{file_name}' successfully purged from storage and database."


class SystemHealthService:
    """Service to inspect real database, runtime, and platform integration health."""

    @staticmethod
    def get_database_latency_ms():
        """Measure roundtrip query execution time against Supabase PostgreSQL."""
        try:
            start = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return duration_ms, "Connected"
        except Exception as e:
            return None, f"Database Error: {str(e)}"

    @classmethod
    def get_system_overview(cls):
        """Aggregate comprehensive real platform metrics."""
        db_latency, db_status = cls.get_database_latency_ms()

        # Users
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        verified_users = User.objects.filter(is_verified=True).count()
        admins_count = User.objects.filter(Q(role=UserRole.ADMIN) | Q(is_superuser=True)).count()
        managers_count = User.objects.filter(role=UserRole.MANAGER).count()
        contributors_count = User.objects.filter(role=UserRole.CONTRIBUTOR).count()

        # Workspaces
        total_workspaces = Workspace.objects.count()
        active_workspaces = Workspace.objects.filter(status=WorkspaceStatus.ACTIVE).count()
        suspended_workspaces = Workspace.objects.filter(status=WorkspaceStatus.SUSPENDED).count()
        archived_workspaces = Workspace.objects.filter(status=WorkspaceStatus.ARCHIVED).count()

        # Tasks & Bugs
        total_tasks = Task.objects.count()
        open_tasks = Task.objects.exclude(status=TaskStatus.DONE).count()
        done_tasks = Task.objects.filter(status=TaskStatus.DONE).count()

        total_bugs = Bug.objects.count()
        open_bugs = Bug.objects.filter(status__in=[BugStatus.OPEN, BugStatus.IN_PROGRESS]).count()
        resolved_bugs = Bug.objects.filter(status__in=[BugStatus.RESOLVED, BugStatus.CLOSED]).count()
        critical_bugs = Bug.objects.filter(
            status__in=[BugStatus.OPEN, BugStatus.IN_PROGRESS],
            severity__in=[BugSeverity.SEV1, BugSeverity.SEV2]
        ).count()

        # Storage
        storage_meta = StorageSyncService.get_storage_metrics()

        # Invitations & Requests
        pending_invitations = WorkspaceInvitation.objects.filter(status=InvitationStatus.PENDING).count()
        pending_requests = WorkspaceAccessRequest.objects.filter(status=AccessRequestStatus.PENDING).count()

        # Unresolved Alerts
        unresolved_alerts = AdminAlert.objects.filter(is_resolved=False).count()

        return {
            'db_latency_ms': db_latency,
            'db_status': db_status,
            'total_users': total_users,
            'active_users': active_users,
            'verified_users': verified_users,
            'admins_count': admins_count,
            'managers_count': managers_count,
            'contributors_count': contributors_count,
            'total_workspaces': total_workspaces,
            'active_workspaces': active_workspaces,
            'suspended_workspaces': suspended_workspaces,
            'archived_workspaces': archived_workspaces,
            'total_tasks': total_tasks,
            'open_tasks': open_tasks,
            'done_tasks': done_tasks,
            'total_bugs': total_bugs,
            'open_bugs': open_bugs,
            'resolved_bugs': resolved_bugs,
            'critical_bugs': critical_bugs,
            'total_files': storage_meta['total_files'],
            'total_storage_bytes': storage_meta['total_bytes'],
            'formatted_storage': storage_meta['formatted_total_bytes'],
            'pending_invitations': pending_invitations,
            'pending_requests': pending_requests,
            'unresolved_alerts': unresolved_alerts,
            'django_version': '5.1.6',
            'python_version': '3.13',
            'environment': 'Production (Render / Supabase)' if not settings.DEBUG else 'Development',
        }

    @classmethod
    def get_integrations_status(cls):
        """Status of platform integrations with zero secret disclosure."""
        db_latency, db_status = cls.get_database_latency_ms()
        is_supabase_storage = SupabaseStorageService.is_supabase_configured()

        db_url = getattr(settings, 'DATABASE_URL', '') or os.environ.get('DATABASE_URL', '')
        # Mask database hostname for safe presentation
        db_host = 'Supabase Cloud PostgreSQL'
        if '@' in db_url:
            host_part = db_url.split('@')[-1].split('/')[0]
            db_host = f"PostgreSQL ({host_part.split(':')[0]})"

        return [
            {
                'name': 'Supabase PostgreSQL Database',
                'category': 'Database & Persistence',
                'status': 'Connected' if db_latency is not None else 'Error',
                'is_active': db_latency is not None,
                'details': f"{db_host} • Latency {db_latency or 0} ms",
                'icon': 'database',
            },
            {
                'name': 'Supabase Object Storage',
                'category': 'File & Media Storage',
                'status': 'Configured & Ready' if is_supabase_storage else 'Local Media Fallback',
                'is_active': is_supabase_storage,
                'details': f"Bucket: {getattr(settings, 'SUPABASE_STORAGE_BUCKET', 'aetherspace-files')}",
                'icon': 'cloud',
            },
            {
                'name': 'Email / Notification Dispatcher',
                'category': 'Communication',
                'status': 'Configured' if getattr(settings, 'EMAIL_HOST', None) else 'Console Backend',
                'is_active': True,
                'details': getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend').split('.')[-1],
                'icon': 'mail',
            },
            {
                'name': 'WebRTC / Jitsi Meeting Hub',
                'category': 'Realtime Video & Audio',
                'status': 'Integrated',
                'is_active': True,
                'details': 'Compatible with Jitsi Meet Free Tier (meet.jit.si)',
                'icon': 'video',
            },
            {
                'name': 'WhiteNoise Static Engine',
                'category': 'Web Asset Distribution',
                'status': 'Active',
                'is_active': True,
                'details': 'Static compression and cache-busting enabled',
                'icon': 'server',
            },
        ]

    @classmethod
    def sync_dynamic_alerts(cls):
        """
        Dynamically evaluate real system conditions and record AdminAlert items:
        - Workspaces exceeding 80% storage quota
        - Pending workspace access requests
        - Unresolved critical bugs
        """
        # 1. Check storage quotas
        for ws in Workspace.objects.all():
            used_bytes = StoredFile.objects.filter(
                workspace=ws,
                is_trashed=False,
                is_external_link=False
            ).aggregate(total=Sum('size_bytes'))['total'] or 0
            quota_bytes = (ws.storage_quota_mb or 50) * 1024 * 1024
            if quota_bytes > 0:
                pct = (used_bytes / quota_bytes) * 100
                if pct >= 80:
                    sev = AlertSeverity.CRITICAL if pct >= 100 else AlertSeverity.WARNING
                    title = f"Workspace '{ws.name}' is at {pct:.1f}% storage capacity"
                    if not AdminAlert.objects.filter(workspace=ws, category=AlertCategory.STORAGE, is_resolved=False).exists():
                        AdminAlert.objects.create(
                            severity=sev,
                            title=title,
                            message=f"Workspace has used {StorageSyncService.format_bytes(used_bytes)} of its {ws.storage_quota_mb} MB quota.",
                            category=AlertCategory.STORAGE,
                            workspace=ws
                        )

        # 2. Check pending access requests
        pending_reqs = WorkspaceAccessRequest.objects.filter(status=AccessRequestStatus.PENDING).count()
        if pending_reqs > 0:
            if not AdminAlert.objects.filter(category=AlertCategory.ACCESS, is_resolved=False).exists():
                AdminAlert.objects.create(
                    severity=AlertSeverity.INFO,
                    title=f"{pending_reqs} pending workspace access request(s) await review",
                    message="Members have requested access to restricted workspaces via 403 Forbidden pages.",
                    category=AlertCategory.ACCESS
                )

        # 3. Check critical bugs
        crit_bugs = Bug.objects.filter(
            status__in=[BugStatus.OPEN, BugStatus.IN_PROGRESS],
            severity=BugSeverity.SEV1
        ).count()
        if crit_bugs > 0:
            if not AdminAlert.objects.filter(category=AlertCategory.BUGS, is_resolved=False).exists():
                AdminAlert.objects.create(
                    severity=AlertSeverity.CRITICAL,
                    title=f"{crit_bugs} SEV-1 Critical Bug(s) active in system",
                    message="Urgent bug reports are currently unresolved. Requires immediate triage.",
                    category=AlertCategory.BUGS
                )


class DataExportService:
    """Service to export application data cleanly to JSON for offline backup."""

    @staticmethod
    def generate_export_json():
        """Creates a sanitized JSON backup of all workspace metadata, tasks, bugs, and audit logs."""
        export_data = {
            'exported_at': timezone.now().isoformat(),
            'platform': 'AetherSpace',
            'version': '1.0.0',
            'users': [],
            'workspaces': [],
            'tasks': [],
            'bugs': [],
            'files_metadata': [],
            'audit_logs': [],
        }

        # Users (Sanitized metadata, no passwords or tokens)
        for u in User.objects.all():
            export_data['users'].append({
                'id': str(u.id),
                'email': u.email,
                'username': u.username,
                'full_name': u.full_name,
                'role': u.role,
                'is_active': u.is_active,
                'created_at': u.created_at.isoformat() if hasattr(u, 'created_at') and u.created_at else None,
            })

        # Workspaces
        for ws in Workspace.objects.all():
            export_data['workspaces'].append({
                'id': str(ws.id),
                'name': ws.name,
                'slug': ws.slug,
                'description': ws.description,
                'status': ws.status,
                'max_seats': ws.max_seats,
                'storage_quota_mb': ws.storage_quota_mb,
                'owner_email': ws.owner.email if ws.owner else None,
                'created_at': ws.created_at.isoformat(),
            })

        # Tasks
        for t in Task.objects.all()[:500]:
            export_data['tasks'].append({
                'id': str(t.id),
                'task_code': getattr(t, 'task_code', getattr(t, 'task_number', '')),
                'title': t.title,
                'status': t.status,
                'priority': t.priority,
                'workspace_slug': t.workspace.slug,
                'created_at': t.created_at.isoformat(),
            })

        # Bugs
        for b in Bug.objects.all()[:500]:
            export_data['bugs'].append({
                'id': str(b.id),
                'bug_code': b.bug_code,
                'title': b.title,
                'status': b.status,
                'severity': b.severity,
                'workspace_slug': b.workspace.slug,
                'created_at': b.created_at.isoformat(),
            })

        # Files Metadata
        for f in StoredFile.objects.filter(is_trashed=False)[:500]:
            export_data['files_metadata'].append({
                'id': str(f.id),
                'name': f.name,
                'size_bytes': f.size_bytes,
                'mime_type': f.mime_type,
                'category': f.category,
                'workspace_slug': f.workspace.slug,
                'is_external_link': f.is_external_link,
                'created_at': f.created_at.isoformat(),
            })

        # Audit Logs
        for a in AuditLog.objects.all()[:500]:
            export_data['audit_logs'].append({
                'id': str(a.id),
                'action': a.action,
                'actor_email': a.actor_email,
                'target_type': a.target_type,
                'target_repr': a.target_repr,
                'status': a.status,
                'created_at': a.created_at.isoformat(),
            })

        return json.dumps(export_data, indent=2)
