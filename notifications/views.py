from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.urls import reverse
from django.contrib import messages

from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceStatus
from workspaces.permissions import workspace_member_required, get_workspace_and_membership
from .models import Notification, NotificationCategory
from .services import (
    get_user_notifications,
    get_notification_metrics,
    get_unread_count,
    mark_as_read,
    mark_as_unread,
    mark_all_as_read,
    delete_notification
)


@login_required
def notifications_router(request):
    """
    Intelligent entry router for /notifications/.
    Directs to the user's active or primary workspace Notification Center.
    """
    # If active workspace in session or request
    active_ws = getattr(request, 'workspace', None)
    if active_ws:
        return redirect('notifications:workspace_notifications', slug=active_ws.slug)

    # Check user memberships
    first_membership = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE,
        workspace__status=WorkspaceStatus.ACTIVE
    ).select_related('workspace').first()

    if first_membership:
        return redirect('notifications:workspace_notifications', slug=first_membership.workspace.slug)

    # No workspace membership: render global notifications view
    notifications_qs = get_user_notifications(request.user)
    paginator = Paginator(notifications_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    metrics = get_notification_metrics(request.user)

    return render(request, 'notifications/notification_center.html', {
        'workspace': None,
        'notifications': page_obj,
        'metrics': metrics,
        'active_tab': 'all',
        'search_query': '',
    })


@login_required
@workspace_member_required
def workspace_notifications(request, slug):
    """
    Full workspace-scoped Notification Center (Screen 52).
    Provides tabbed category filtering: All, Unread, Tasks, Bugs, Mentions.
    """
    workspace = request.workspace
    active_tab = request.GET.get('tab', 'all').lower()
    search_query = request.GET.get('q', '').strip()

    unread_only = (active_tab == 'unread')
    category = None
    if active_tab == 'tasks':
        category = NotificationCategory.TASK
    elif active_tab == 'bugs':
        category = NotificationCategory.BUG
    elif active_tab == 'mentions':
        category = NotificationCategory.MENTION

    notifications_qs = get_user_notifications(
        user=request.user,
        workspace=workspace,
        category=category,
        unread_only=unread_only,
        search_query=search_query
    )

    paginator = Paginator(notifications_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    metrics = get_notification_metrics(request.user, workspace=workspace)

    return render(request, 'notifications/notification_center.html', {
        'workspace': workspace,
        'notifications': page_obj,
        'metrics': metrics,
        'active_tab': active_tab,
        'search_query': search_query,
    })


@login_required
@require_POST
def mark_notification_read_view(request, notification_id):
    """
    Marks a single notification as read. Supports both standard form POST and JSON/AJAX.
    """
    success = mark_as_read(notification_id, request.user)
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        workspace = getattr(request, 'workspace', None)
        unread_count = get_unread_count(request.user, workspace=workspace)
        return JsonResponse({'status': 'ok' if success else 'not_found', 'unread_count': unread_count})

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('notifications:notifications_router')


@login_required
@require_POST
def mark_notification_unread_view(request, notification_id):
    """
    Toggles a single notification back to unread.
    """
    success = mark_as_unread(notification_id, request.user)
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        workspace = getattr(request, 'workspace', None)
        unread_count = get_unread_count(request.user, workspace=workspace)
        return JsonResponse({'status': 'ok' if success else 'not_found', 'unread_count': unread_count})

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('notifications:notifications_router')


@login_required
@require_POST
def mark_all_notifications_read_view(request):
    """
    Marks all notifications for the user (optionally scoped to a workspace/category) as read.
    """
    workspace_slug = request.POST.get('workspace_slug')
    category = request.POST.get('category')
    
    workspace = None
    if workspace_slug:
        workspace = get_object_or_404(Workspace, slug=workspace_slug)
        # Verify user is a member of this workspace
        if not WorkspaceMembership.objects.filter(workspace=workspace, user=request.user, status=MembershipStatus.ACTIVE).exists():
            return HttpResponseForbidden("Not authorized for this workspace.")

    updated_count = mark_all_as_read(request.user, workspace=workspace, category=category)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({'status': 'ok', 'updated_count': updated_count, 'unread_count': 0})

    messages.success(request, f"Marked {updated_count} notification(s) as read.")
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    if workspace:
        return redirect('notifications:workspace_notifications', slug=workspace.slug)
    return redirect('notifications:notifications_router')


@login_required
@require_POST
def delete_notification_view(request, notification_id):
    """
    Deletes or dismisses a notification.
    """
    success = delete_notification(notification_id, request.user)
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        workspace = getattr(request, 'workspace', None)
        unread_count = get_unread_count(request.user, workspace=workspace)
        return JsonResponse({'status': 'ok' if success else 'not_found', 'unread_count': unread_count})

    messages.info(request, "Notification dismissed.")
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('notifications:notifications_router')


@login_required
def api_unread_notifications(request):
    """
    API endpoint returning live unread count and latest 6 notifications for Alpine.js header synchronization.
    """
    workspace_slug = request.GET.get('workspace')
    workspace = None
    if workspace_slug:
        workspace = Workspace.objects.filter(slug=workspace_slug).first()

    unread_count = get_unread_count(request.user, workspace=workspace)
    recent_qs = get_user_notifications(request.user, workspace=workspace)[:6]

    items = []
    for n in recent_qs:
        items.append({
            'id': str(n.id),
            'title': n.title,
            'body': n.body[:100] + '...' if len(n.body) > 100 else n.body,
            'category': n.category,
            'action_url': n.action_url or '#',
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%b %d, %H:%M'),
            'actor_name': n.actor.full_name if n.actor else 'AetherSpace',
        })

    return JsonResponse({
        'status': 'ok',
        'unread_count': unread_count,
        'notifications': items,
    })
