import os
import io
import re
import logging
from urllib.parse import urlparse
from PIL import Image

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from django.db.models import Q

from accounts.models import User, UserProfile
from workspaces.models import WorkspaceMembership, WorkspaceRole
from tasks.models import Task, TaskStatus, TaskActivity
from bugs.models import Bug, BugStatus, BugSeverity, BugActivity
from files.models import StoredFile, FileActivity

logger = logging.getLogger(__name__)

# Strict KB-only upload constraints for free-tier sustainability
MAX_AVATAR_SIZE_BYTES = 500 * 1024  # 500 KB hard limit
RECOMMENDED_AVATAR_SIZE_KB = 200     # 200 KB recommended
ALLOWED_AVATAR_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

PRESET_AVATAR_THEMES = [
    {
        'id': 'blue',
        'name': 'Blue Indigo',
        'gradient': 'from-blue-600 to-indigo-700',
        'border': 'border-blue-500',
        'bg': 'bg-blue-600',
    },
    {
        'id': 'teal',
        'name': 'Emerald Teal',
        'gradient': 'from-emerald-500 to-teal-700',
        'border': 'border-emerald-500',
        'bg': 'bg-emerald-600',
    },
    {
        'id': 'purple',
        'name': 'Purple Violet',
        'gradient': 'from-purple-600 to-pink-600',
        'border': 'border-purple-500',
        'bg': 'bg-purple-600',
    },
    {
        'id': 'amber',
        'name': 'Amber Flame',
        'gradient': 'from-amber-500 to-orange-600',
        'border': 'border-amber-500',
        'bg': 'bg-amber-600',
    },
    {
        'id': 'rose',
        'name': 'Rose Crimson',
        'gradient': 'from-rose-500 to-red-700',
        'border': 'border-rose-500',
        'bg': 'bg-rose-600',
    },
    {
        'id': 'cyan',
        'name': 'Neon Cyan',
        'gradient': 'from-cyan-500 to-blue-600',
        'border': 'border-cyan-500',
        'bg': 'bg-cyan-600',
    },
]


def get_or_create_user_profile(user):
    """Ensure UserProfile instance exists for the user."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def get_user_profile_metrics(user):
    """
    Calculate high-level profile metrics across all accessible workspaces.
    """
    assigned_tasks = Task.objects.filter(assignee=user)
    active_tasks_count = assigned_tasks.exclude(status=TaskStatus.DONE).count()
    completed_tasks_count = assigned_tasks.filter(status=TaskStatus.DONE).count()

    assigned_bugs = Bug.objects.filter(assignee=user)
    open_bugs_count = assigned_bugs.filter(status__in=[BugStatus.OPEN, BugStatus.IN_PROGRESS]).count()
    reported_bugs_count = Bug.objects.filter(reporter=user).count()

    workspaces_count = WorkspaceMembership.objects.filter(
        user=user,
        status='ACTIVE'
    ).count()

    # Total combined personal activities
    task_act_count = TaskActivity.objects.filter(actor=user).count()
    bug_act_count = BugActivity.objects.filter(actor=user).count()
    file_act_count = FileActivity.objects.filter(actor=user).count()
    total_activities_count = task_act_count + bug_act_count + file_act_count

    return {
        'total_assigned_tasks': assigned_tasks.count(),
        'active_tasks_count': active_tasks_count,
        'completed_tasks_count': completed_tasks_count,
        'assigned_bugs_count': assigned_bugs.count(),
        'open_bugs_count': open_bugs_count,
        'reported_bugs_count': reported_bugs_count,
        'workspaces_count': workspaces_count,
        'activities_count': total_activities_count,
    }


def get_user_assigned_tasks(user, status=None, workspace_slug=None, query=None):
    """
    Query tasks assigned to user across accessible workspaces.
    """
    qs = Task.objects.filter(
        assignee=user,
        workspace__memberships__user=user,
        workspace__memberships__status='ACTIVE'
    ).select_related('workspace').distinct()

    if status and status != 'ALL':
        qs = qs.filter(status=status)

    if workspace_slug and workspace_slug != 'ALL':
        qs = qs.filter(workspace__slug=workspace_slug)

    if query:
        q_clean = query.strip()
        qs = qs.filter(
            Q(title__icontains=q_clean) |
            Q(task_code__icontains=q_clean) |
            Q(description__icontains=q_clean)
        )

    return qs.order_by('-updated_at')


def get_user_bugs(user, relation='ALL', severity=None, status=None, query=None):
    """
    Query bugs assigned to or reported by user across accessible workspaces.
    """
    base_q = Q(workspace__memberships__user=user, workspace__memberships__status='ACTIVE')

    if relation == 'ASSIGNED':
        qs = Bug.objects.filter(base_q, assignee=user)
    elif relation == 'REPORTED':
        qs = Bug.objects.filter(base_q, reporter=user)
    elif relation == 'RESOLVED':
        qs = Bug.objects.filter(base_q, assignee=user, status__in=[BugStatus.RESOLVED, BugStatus.CLOSED])
    else:
        qs = Bug.objects.filter(base_q & (Q(assignee=user) | Q(reporter=user)))

    qs = qs.select_related('workspace', 'assignee', 'reporter').distinct()

    if severity and severity != 'ALL':
        qs = qs.filter(severity=severity)

    if status and status != 'ALL':
        qs = qs.filter(status=status)

    if query:
        q_clean = query.strip()
        qs = qs.filter(
            Q(title__icontains=q_clean) |
            Q(bug_code__icontains=q_clean) |
            Q(description__icontains=q_clean)
        )

    return qs.order_by('-updated_at')


def get_user_activities(user, category='ALL', limit=50):
    """
    Chronological text-based activity stream for user.
    Rule 57: Text-based; no radar/graph charts.
    """
    activities = []

    # 1. Task Activities
    if category in ['ALL', 'TASKS']:
        task_acts = TaskActivity.objects.filter(actor=user).select_related(
            'task', 'task__workspace'
        ).order_by('-created_at')[:limit]

        for a in task_acts:
            activities.append({
                'category': 'TASKS',
                'category_label': 'Task',
                'action': str(getattr(a, 'action', 'Updated')).replace('_', ' ').capitalize(),
                'description': a.message or f"Updated task {a.task.task_code}: {a.task.title}",
                'timestamp': a.created_at,
                'link': f"/tasks/w/{a.task.workspace.slug}/{a.task.id}/" if a.task and a.task.workspace else '#',
                'code': a.task.task_code if a.task else '',
                'workspace': a.task.workspace.name if a.task and a.task.workspace else 'Workspace',
                'icon': 'task',
            })

    # 2. Bug Activities
    if category in ['ALL', 'BUGS']:
        bug_acts = BugActivity.objects.filter(actor=user).select_related(
            'bug', 'bug__workspace'
        ).order_by('-created_at')[:limit]

        for a in bug_acts:
            activities.append({
                'category': 'BUGS',
                'category_label': 'Bug',
                'action': str(getattr(a, 'action', 'Updated')).replace('_', ' ').capitalize(),
                'description': a.message or f"Updated defect {a.bug.bug_code}: {a.bug.title}",
                'timestamp': a.created_at,
                'link': f"/bugs/w/{a.bug.workspace.slug}/{a.bug.id}/" if a.bug and a.bug.workspace else '#',
                'code': a.bug.bug_code if a.bug else '',
                'workspace': a.bug.workspace.name if a.bug and a.bug.workspace else 'Workspace',
                'icon': 'bug',
            })

    # 3. File Activities
    if category in ['ALL', 'FILES']:
        file_acts = FileActivity.objects.filter(actor=user).select_related(
            'file', 'file__workspace'
        ).order_by('-created_at')[:limit]

        for a in file_acts:
            activities.append({
                'category': 'FILES',
                'category_label': 'File',
                'action': a.get_activity_type_display() if hasattr(a, 'get_activity_type_display') else 'File Action',
                'description': a.details or f"Action on file {a.file.name if a.file else 'item'}",
                'timestamp': a.created_at,
                'link': f"/files/w/{a.file.workspace.slug}/file/{a.file.id}/" if a.file and a.file.workspace else '#',
                'code': 'FILE',
                'workspace': a.file.workspace.name if a.file and a.file.workspace else 'Workspace',
                'icon': 'file',
            })

    # Sort all chronologically descending
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return activities[:limit]


def get_user_workspace_roles(user):
    """
    Retrieve all workspace memberships with role information.
    """
    memberships = WorkspaceMembership.objects.filter(
        user=user
    ).select_related('workspace', 'workspace__owner').order_by('-joined_at')

    roles_data = []
    for m in memberships:
        roles_data.append({
            'membership_id': m.id,
            'workspace': m.workspace,
            'workspace_name': m.workspace.name,
            'workspace_slug': m.workspace.slug,
            'role': m.role,
            'role_display': m.get_role_display(),
            'status': m.status,
            'is_owner': m.workspace.owner == user,
            'joined_at': m.joined_at,
            'is_admin': m.role == WorkspaceRole.ADMIN,
            'is_manager': m.role == WorkspaceRole.MANAGER,
            'is_contributor': m.role == WorkspaceRole.CONTRIBUTOR,
        })
    return roles_data


def process_and_save_avatar(user, file_obj=None, avatar_url=None, preset_color=None):
    """
    Strict KB-only avatar processor:
    1. If preset_color: sets 'preset:<id>' (0 KB storage).
    2. If avatar_url: sets external URL directly (0 KB storage).
    3. If file_obj: validates size <= 500 KB, compresses & resizes to 200x200 thumbnail
       yielding an ultra-compact ~15-30 KB file saved via default_storage.
    """
    if preset_color:
        valid_preset_ids = {p['id'] for p in PRESET_AVATAR_THEMES}
        if preset_color in valid_preset_ids:
            user.avatar = f"preset:{preset_color}"
            user.save(update_fields=['avatar'])
            return True, "Avatar style preset applied successfully."
        return False, "Invalid preset selection."

    if avatar_url:
        clean_url = avatar_url.strip()
        parsed = urlparse(clean_url)
        if parsed.scheme in ('http', 'https') and parsed.netloc:
            user.avatar = clean_url
            user.save(update_fields=['avatar'])
            return True, "External profile photo linked successfully (0 KB storage used)."
        return False, "Please enter a valid HTTP/HTTPS image URL."

    if file_obj:
        # 1. Enforce hard 500 KB limit
        if file_obj.size > MAX_AVATAR_SIZE_BYTES:
            size_kb = round(file_obj.size / 1024)
            return False, f"File size ({size_kb} KB) exceeds the maximum allowed limit of 500 KB."

        ext = os.path.splitext(file_obj.name)[1].lstrip('.').lower()
        if ext not in ALLOWED_AVATAR_EXTENSIONS:
            return False, f"Unsupported file format '.{ext}'. Allowed formats: JPG, PNG, WEBP, GIF."

        # 2. Open image with Pillow and compress to a 200x200 square thumbnail
        try:
            image = Image.open(file_obj)
            image = image.convert('RGB')

            # Center crop to square
            width, height = image.size
            min_dim = min(width, height)
            left = (width - min_dim) / 2
            top = (height - min_dim) / 2
            right = (width + min_dim) / 2
            bottom = (height + min_dim) / 2
            image = image.crop((left, top, right, bottom))

            # Resize to 200x200
            image.thumbnail((200, 200), Image.Resampling.LANCZOS)

            # Compress to lightweight JPEG buffer
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85, optimize=True)
            compressed_bytes = buffer.getvalue()
            compressed_kb = round(len(compressed_bytes) / 1024, 1)

            # Save to storage
            filename = f"avatars/{user.id}/avatar.jpg"
            if default_storage.exists(filename):
                default_storage.delete(filename)

            saved_path = default_storage.save(filename, ContentFile(compressed_bytes))
            file_url = default_storage.url(saved_path)

            user.avatar = file_url
            user.save(update_fields=['avatar'])

            logger.info(f"User {user.id} avatar compressed to {compressed_kb} KB and saved.")
            return True, f"Profile avatar updated and compressed to {compressed_kb} KB."

        except Exception as e:
            logger.error(f"Avatar processing error: {str(e)}")
            return False, "Could not process avatar image. Please ensure it is a valid image file."

    return False, "No avatar file or URL provided."


def remove_user_avatar(user):
    """
    Remove user avatar and reclaim storage.
    """
    if user.avatar:
        # If avatar is stored locally in default_storage
        if user.avatar.startswith('/media/avatars/') or 'avatars/' in user.avatar:
            filename = f"avatars/{user.id}/avatar.jpg"
            try:
                if default_storage.exists(filename):
                    default_storage.delete(filename)
            except Exception as e:
                logger.warning(f"Failed to delete stored avatar file: {e}")

        user.avatar = ""
        user.save(update_fields=['avatar'])
        return True, "Avatar removed. Initials fallback restored."
    return True, "No avatar to remove."
