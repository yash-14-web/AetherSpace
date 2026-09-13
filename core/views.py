from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotFound, HttpResponseServerError, JsonResponse
from django.db.models import Q
from django.urls import reverse

from workspaces.models import Workspace, MembershipStatus
from tasks.models import Task
from bugs.models import Bug
from files.models import StoredFile


def landing(request):
    """Public landing page introducing AetherSpace."""
    return render(request, 'core/landing.html', {
        'title': 'AetherSpace — Next-Gen Agile Collaboration Platform',
    })


def about_view(request):
    """Public About page providing a comprehensive guide to AetherSpace."""
    return render(request, 'core/about.html', {
        'title': 'About AetherSpace — High-Performance Team Collaboration',
    })


@login_required
def calendar_view(request):
    """Calendar & Agenda navigation destination - redirects to active workspace calendar."""
    return redirect('calendars:calendar_router')



@login_required
def files_view(request):
    """Files & Workspace Storage navigation destination - redirects to active workspace files."""
    return redirect('files:files_router')


@login_required
def meetings_view(request):
    """Meet Hub navigation destination - redirects to workspace meet hub."""
    return redirect('meetings:meet_router')


@login_required
def chat_view(request):
    """Team Chat navigation destination."""
    return render(request, 'components/placeholder.html', {
        'module_title': 'Team Chat & Channels',
        'phase_badge': 'Phase 5 — Collaboration',
        'module_icon': 'chat',
        'module_description': 'Real-time team messaging, topic channels, direct messages, and code snippet sharing.',
        'empty_heading': 'Collaboration & Channels',
        'empty_text': 'Channel threads, direct messages, asset pins, and WebSocket real-time messaging arrive in Phase 5.',
        'features': [
            'Topic channels (e.g. #general, #frontend, #bugs)',
            '1-to-1 encrypted direct messaging',
            'Markdown formatting & code block syntax highlighting',
            'Pinned workspace assets & shared file drawer',
        ],
    })


@login_required
def time_tracking_view(request):
    """Time Tracking navigation destination."""
    return render(request, 'components/placeholder.html', {
        'module_title': 'Time Tracking & Logs',
        'phase_badge': 'Phase 4 — Shell Rail',
        'module_icon': 'time',
        'module_description': 'Track sprint hours, task durations, and team workload efficiency across active workspaces.',
        'empty_heading': 'Workload & Sprint Hours',
        'empty_text': 'Live stopwatch timers, manual hour logs, and billable time export will accompany the task execution phase.',
        'features': [
            'Real-time task stopwatch timer',
            'Daily and weekly timesheet summaries',
            'Sprint hour burn-down analytics',
            'Exportable CSV timesheets for team leads',
        ],
    })


@login_required
def notifications_view(request):
    """Notification Center navigation destination - redirects to active workspace notifications."""
    return redirect('notifications:notifications_router')


@login_required
def profile_view(request):
    """User Profile & Account settings - redirects to accounts profile."""
    return redirect('accounts:profile')


def error_400(request, exception=None):
    """400 Bad Request error page."""
    return render(request, 'errors/400.html', {
        'status_code': 400,
        'title': 'Bad Request',
        'message': 'Invalid Request — The request could not be processed due to invalid parameters.',
    }, status=400)


def error_403(request, exception=None):
    """403 Forbidden / Access Restricted error page with Request Access workflow."""
    return render(request, 'errors/403.html', {
        'status_code': 403,
        'title': 'Permission Denied',
        'message': 'Access Restricted — You do not have the required permissions to view this workspace or resource.',
        'show_request_access': True,
    }, status=403)


def error_404(request, exception=None):
    """404 Not Found error page."""
    return render(request, 'errors/404.html', {
        'status_code': 404,
        'title': 'Page Not Found',
        'message': 'Page Not Found — The task, bug, or workspace you are looking for does not exist or has been moved.',
    }, status=404)


def error_500(request):
    """500 Internal Server Error page."""
    return render(request, 'errors/500.html', {
        'status_code': 500,
        'title': 'Internal Server Error',
        'message': 'Internal Server Error — Something went wrong on our end. Our engineering team has been notified.',
    }, status=500)


@login_required
def global_search_api(request):
    """
    Global omnibar search endpoint.
    Searches tasks by 6-digit ID (#619347), bugs by code (B-882316), files, and workspaces.
    Respects strict workspace isolation and RBAC.
    """
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'status': 'ok', 'results': []})

    # Workspaces visible to user
    if getattr(request.user, 'is_admin_role', False) or request.user.is_superuser:
        workspaces_qs = Workspace.objects.all()
    else:
        workspaces_qs = Workspace.objects.filter(
            memberships__user=request.user,
            memberships__status=MembershipStatus.ACTIVE
        )

    ws_ids = list(workspaces_qs.values_list('id', flat=True))
    results = []

    # 1. Search Tasks by 6-digit task_code (#619347 / 619347) or title
    clean_task_code = q.lstrip('#').replace('T-', '').replace('t-', '').strip()
    task_filter = Q(workspace_id__in=ws_ids)
    if clean_task_code and clean_task_code.isdigit():
        task_filter &= (Q(task_code__icontains=clean_task_code) | Q(title__icontains=q))
    else:
        task_filter &= (Q(task_code__icontains=q) | Q(title__icontains=q))

    tasks = Task.objects.filter(task_filter).select_related('workspace')[:8]
    for t in tasks:
        results.append({
            'type': 'task',
            'id': str(t.id),
            'code': f"#{t.task_code}",
            'title': t.title,
            'workspace': t.workspace.name,
            'status': t.get_status_display(),
            'priority': t.get_priority_display(),
            'url': reverse('tasks:task_detail', kwargs={'slug': t.workspace.slug, 'task_code': t.task_code}),
            'icon': 'task',
        })

    # 2. Search Bugs by bug_code (B-882316 / 882316) or title
    clean_bug = q.upper().replace('B-', '').strip()
    bug_filter = Q(workspace_id__in=ws_ids)
    if clean_bug and clean_bug.isdigit():
        bug_filter &= (Q(bug_code__icontains=clean_bug) | Q(title__icontains=q))
    else:
        bug_filter &= (Q(bug_code__icontains=q) | Q(title__icontains=q))

    bugs = Bug.objects.filter(bug_filter).select_related('workspace')[:8]
    for b in bugs:
        results.append({
            'type': 'bug',
            'id': str(b.id),
            'code': b.bug_code,
            'title': b.title,
            'workspace': b.workspace.name,
            'status': b.get_status_display(),
            'severity': b.get_severity_display(),
            'url': reverse('bugs:bug_detail', kwargs={'slug': b.workspace.slug, 'bug_code': b.bug_code}),
            'icon': 'bug',
        })

    # 3. Search Workspaces by name or slug
    workspaces = workspaces_qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))[:5]
    for ws in workspaces:
        results.append({
            'type': 'workspace',
            'id': str(ws.id),
            'code': f"/{ws.slug}/",
            'title': ws.name,
            'workspace': ws.name,
            'status': ws.get_status_display(),
            'url': reverse('workspaces:workspace_dashboard', kwargs={'slug': ws.slug}),
            'icon': 'workspace',
        })

    # 4. Search Files by name
    files = StoredFile.objects.filter(
        workspace_id__in=ws_ids,
        is_trashed=False,
        name__icontains=q
    ).select_related('workspace')[:5]
    for f in files:
        results.append({
            'type': 'file',
            'id': str(f.id),
            'code': f.category,
            'title': f.name,
            'workspace': f.workspace.name,
            'status': f.formatted_size,
            'url': reverse('files:file_detail', kwargs={'slug': f.workspace.slug, 'file_id': f.id}),
            'icon': 'file',
        })

    return JsonResponse({'status': 'ok', 'query': q, 'count': len(results), 'results': results})

