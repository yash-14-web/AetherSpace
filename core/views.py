from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotFound, HttpResponseServerError, JsonResponse
from django.db.models import Q
from django.urls import reverse

from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus
from tasks.models import Task
from bugs.models import Bug
from files.models import StoredFile
from accounts.models import User, ApprovalStatus


def landing(request):
    """Public landing page introducing AetherSpace."""
    if request.user.is_authenticated:
        if getattr(request.user, 'approval_status', None) == 'PENDING':
            return redirect('accounts:pending_approval')
        return redirect('workspaces:dashboard')
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
    """Team Chat navigation destination - redirects to active workspace chat."""
    return redirect('chat:chat_router')


@login_required
def time_tracking_view(request):
    """Time Tracking navigation destination - redirects to active workspace timesheet."""
    return redirect('timetracking:router')


@login_required
def notifications_view(request):
    """Notification Center navigation destination - redirects to active workspace notifications."""
    return redirect('notifications:notifications_router')


@login_required
def profile_view(request):
    """User Profile & Account settings - redirects to accounts profile."""
    return redirect('accounts:profile')


import secrets


def error_400(request, exception=None):
    """400 Bad Request error page."""
    return render(request, 'errors/400.html', {
        'status_code': 400,
        'title': 'Bad Request',
        'headline': 'Invalid Request',
        'message': 'The request could not be processed due to invalid parameters.',
    }, status=400)


def error_401(request, exception=None):
    """401 Unauthorized / Authentication Required error page."""
    return render(request, 'errors/401.html', {
        'status_code': 401,
        'title': 'Authentication Required',
        'headline': 'Authentication Required',
        'message': 'Please sign in to continue.',
    }, status=401)


def error_403(request, exception=None, message=None):
    """
    403 Forbidden / Access Restricted error page with Request Access workflow.
    Request Access button only renders when a legitimate, existing workspace is identified
    and the requesting user is authenticated but not yet a member.
    Preserves specific permission failure reasons (e.g. workspace creation restriction).
    """
    if not message and exception:
        message = str(exception)
    if not message:
        message = "You do not have the required permissions to view this workspace or resource."

    ws = getattr(request, 'workspace', None)
    if not ws and request.path:
        parts = [p for p in request.path.strip('/').split('/') if p]
        if len(parts) >= 2 and parts[0] == 'workspaces':
            candidate_slug = parts[1]
            if candidate_slug not in ('dashboard', 'create', 'search', 'invitations'):
                ws = Workspace.objects.filter(slug=candidate_slug).first()

    show_request_access = False
    if ws and request.user.is_authenticated:
        # Show request access only if user is NOT an active member
        is_member = ws.memberships.filter(user=request.user, status=MembershipStatus.ACTIVE).exists()
        if not is_member:
            show_request_access = True

    return render(request, 'errors/403.html', {
        'status_code': 403,
        'title': 'Permission Denied',
        'headline': 'Access Restricted',
        'message': message,
        'show_request_access': show_request_access,
        'workspace': ws,
    }, status=403)


def error_404(request, exception=None):
    """404 Not Found error page."""
    return render(request, 'errors/404.html', {
        'status_code': 404,
        'title': 'Page Not Found',
        'headline': 'Page Not Found',
        'message': 'The task, bug, or workspace you are looking for does not exist or has been moved.',
    }, status=404)


def error_408(request, exception=None):
    """408 Request Timeout error page."""
    return render(request, 'errors/408.html', {
        'status_code': 408,
        'title': 'Request Timed Out',
        'headline': 'Request Timed Out',
        'message': 'The request took too long to complete. Please try again.',
    }, status=408)


def error_429(request, exception=None):
    """429 Too Many Requests rate-limit error page."""
    response = render(request, 'errors/429.html', {
        'status_code': 429,
        'title': 'Too Many Requests',
        'headline': 'Too Many Requests',
        'message': "You've made too many requests in a short period. Please wait a moment and try again.",
        'retry_after': getattr(exception, 'retry_after', 60),
    }, status=429)
    response['Retry-After'] = str(getattr(exception, 'retry_after', 60))
    return response


def error_500(request, error_id=None):
    """
    500 Internal Server Error page.
    Generates a secure correlation Error ID and guarantees zero leakage of stack traces or credentials.
    """
    if not error_id:
        error_id = secrets.token_hex(4).upper()
    return render(request, 'errors/500.html', {
        'status_code': 500,
        'title': 'Internal Server Error',
        'headline': 'Something Went Wrong',
        'message': 'Something went wrong on our end. Our engineering team has been notified.',
        'error_id': error_id,
    }, status=500)


def error_503(request, exception=None):
    """503 Service Unavailable error page."""
    return render(request, 'errors/503.html', {
        'status_code': 503,
        'title': 'Service Unavailable',
        'headline': 'Service Temporarily Unavailable',
        'message': 'AetherSpace is temporarily unable to process your request. We are working to restore service.',
    }, status=503)


def error_network(request):
    """Network connection failure preview and recovery destination."""
    return render(request, 'errors/network_error.html', {
        'title': 'Connection Lost — AetherSpace',
    }, status=503)


def errors_showcase_view(request):
    """
    Comprehensive Showcase Page auditing all full-page error states,
    component-level error states, file/calendar errors, and network telemetry.
    Matches AetherSpace_Designs/a_high_resolution_dark_ui_graphic_design_showcase.png
    """
    return render(request, 'errors/errors_showcase.html', {
        'title': 'Error & Empty States Showcase — AetherSpace',
    })


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

    # 5. Search People by ID (#####C), Email, or Name
    clean_person_q = q.lstrip('#').lstrip('@').strip()
    digits_only = ''.join(c for c in clean_person_q if c.isdigit())

    person_q_filter = (
        Q(user__full_name__icontains=q) |
        Q(user__username__icontains=clean_person_q) |
        Q(user__email__icontains=q) |
        Q(user__contributor_id__icontains=clean_person_q)
    )
    if digits_only:
        person_q_filter |= Q(user__contributor_id__icontains=digits_only)

    user_filter = Q(workspace_id__in=ws_ids, status=MembershipStatus.ACTIVE, user__is_active=True) & person_q_filter
    memberships = WorkspaceMembership.objects.filter(user_filter).select_related('user', 'workspace')[:10]
    seen_user_ids = set()

    for m in memberships:
        u = m.user
        if u.id in seen_user_ids:
            continue
        seen_user_ids.add(u.id)
        name = u.full_name or u.email.split('@')[0]
        initials = ''.join([part[0].upper() for part in name.split()[:2]]) or name[:1].upper()
        avatar_val = str(u.avatar) if getattr(u, 'avatar', None) else ''
        if avatar_val.startswith('preset:'):
            avatar_val = ''

        profile = getattr(u, 'profile', None)
        headline = getattr(profile, 'headline', '') if profile else ''
        role_disp = m.get_role_display()
        system_role = u.get_role_display() if hasattr(u, 'get_role_display') else str(u.role)
        tagging_role = getattr(m, 'role_tag', '') or getattr(m, 'functional_role', '') or getattr(u, 'tagging_role', '')
        dm_url = reverse('chat:direct_message', kwargs={'slug': m.workspace.slug, 'user_id': u.id}) if u.id != request.user.id else None
        profile_url = reverse('accounts:public_profile', kwargs={'user_id': u.id}) if u.id != request.user.id else reverse('accounts:profile')

        results.append({
            'type': 'person',
            'id': str(u.id),
            'code': u.contributor_id or 'MEMBER',
            'title': name,
            'email': u.email,
            'username': u.username,
            'initials': initials,
            'avatar': avatar_val,
            'workspace': m.workspace.name,
            'workspace_slug': m.workspace.slug,
            'status': role_disp,
            'role': role_disp,
            'system_role': system_role,
            'tagging_role': tagging_role,
            'availability_status': getattr(u, 'availability_status', 'available'),
            'status_message': getattr(u, 'status_message', ''),
            'headline': headline,
            'dm_url': dm_url,
            'profile_url': profile_url,
            'url': profile_url,
            'icon': 'person',
        })

    # Search global approved active users by ID, email, or name if capacity allows
    if len(seen_user_ids) < 8:
        global_q_filter = (
            Q(full_name__icontains=q) |
            Q(username__icontains=clean_person_q) |
            Q(email__icontains=q) |
            Q(contributor_id__icontains=clean_person_q)
        )
        if digits_only:
            global_q_filter |= Q(contributor_id__icontains=digits_only)

        global_users = User.objects.filter(
            is_active=True,
            approval_status=ApprovalStatus.APPROVED
        ).exclude(
            id__in=seen_user_ids
        ).filter(global_q_filter)[:(8 - len(seen_user_ids))]

        for u in global_users:
            seen_user_ids.add(u.id)
            name = u.full_name or u.email.split('@')[0]
            initials = ''.join([part[0].upper() for part in name.split()[:2]]) or name[:1].upper()
            avatar_val = str(u.avatar) if getattr(u, 'avatar', None) else ''
            if avatar_val.startswith('preset:'):
                avatar_val = ''

            profile = getattr(u, 'profile', None)
            headline = getattr(profile, 'headline', '') if profile else ''
            system_role = u.get_role_display() if hasattr(u, 'get_role_display') else str(u.role)
            profile_url = reverse('accounts:public_profile', kwargs={'user_id': u.id}) if u.id != request.user.id else reverse('accounts:profile')

            results.append({
                'type': 'person',
                'id': str(u.id),
                'code': u.contributor_id or 'MEMBER',
                'title': name,
                'email': u.email,
                'username': u.username,
                'initials': initials,
                'avatar': avatar_val,
                'workspace': 'AetherSpace Network',
                'workspace_slug': '',
                'status': system_role,
                'role': system_role,
                'system_role': system_role,
                'tagging_role': getattr(u, 'tagging_role', ''),
                'availability_status': getattr(u, 'availability_status', 'available'),
                'status_message': getattr(u, 'status_message', ''),
                'headline': headline,
                'dm_url': None,
                'profile_url': profile_url,
                'url': profile_url,
                'icon': 'person',
            })

    return JsonResponse({'status': 'ok', 'query': q, 'count': len(results), 'results': results})


@login_required
def api_markdown_preview(request):
    """
    Central API endpoint for live markdown preview.
    Accepts raw markdown content and returns sanitized HTML matching the
    persisted server-side render pipeline exactly (LIVE PREVIEW == SAVED MESSAGE).
    """
    import json
    from core.templatetags.rich_text import render_rich_text
    if request.method == 'POST':
        content = ''
        if request.content_type == 'application/json':
            try:
                body = json.loads(request.body.decode('utf-8'))
                content = (
                    body.get('content') or
                    body.get('markdown') or
                    body.get('text') or
                    body.get('body') or
                    ''
                )
            except Exception:
                content = ''
        else:
            content = (
                request.POST.get('content') or
                request.POST.get('markdown') or
                request.POST.get('text') or
                ''
            )

        html = render_rich_text(content)
        return JsonResponse({'status': 'ok', 'html': str(html)})
    return HttpResponseBadRequest("POST required")



