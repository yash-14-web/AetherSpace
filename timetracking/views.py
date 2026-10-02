import csv
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Sum, Q
from django.core.paginator import Paginator

from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceStatus, WorkspaceRole
from workspaces.permissions import workspace_member_required
from tasks.models import Task, TaskStatus
from .models import TimeEntry, TimeEntryType, TimerStatus
from .forms import ManualTimeEntryForm


@login_required
def time_tracking_router(request):
    """
    Intelligent router for Time Tracking in the global rail.
    Redirects user to their active workspace timesheet.
    """
    memberships = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE,
        workspace__status=WorkspaceStatus.ACTIVE
    ).select_related('workspace')

    count = memberships.count()
    if count == 0:
        if request.user.is_superuser or getattr(request.user, 'is_admin_role', False):
            first_ws = Workspace.objects.filter(status=WorkspaceStatus.ACTIVE).first()
            if first_ws:
                return redirect('timetracking:workspace_timesheet', slug=first_ws.slug)
        # Informative empty state for users without workspaces
        return render(request, 'timetracking/no_workspaces.html', {
            'title': 'Time Tracking — No Workspace Membership',
        })

    first_mem = memberships.first()
    return redirect('timetracking:workspace_timesheet', slug=first_mem.workspace.slug)


@workspace_member_required
def workspace_timesheet(request, slug):
    """
    Main workspace time tracking dashboard.
    Shows real database metrics, live stopwatch widget, manual log modal, and history.
    """
    workspace = request.workspace
    membership = request.membership
    now = timezone.now()
    today = now.date()

    is_privileged = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )

    # Base queryset
    qs = TimeEntry.objects.filter(workspace=workspace).select_related('user', 'task')

    # RBAC filtering: Contributors only see their own logs; Managers/Admins can see all
    member_filter = request.GET.get('member', '').strip()
    if not is_privileged:
        qs = qs.filter(user=request.user)
    elif member_filter:
        qs = qs.filter(user_id=member_filter)

    # Date filtering
    date_filter = request.GET.get('date_range', 'week').strip()
    if date_filter == 'today':
        qs = qs.filter(started_at__date=today)
    elif date_filter == 'week':
        start_of_week = today - timedelta(days=today.weekday())
        qs = qs.filter(started_at__date__gte=start_of_week)
    elif date_filter == 'month':
        start_of_month = today.replace(day=1)
        qs = qs.filter(started_at__date__gte=start_of_month)

    # Task filter
    task_filter = request.GET.get('task', '').strip()
    if task_filter:
        qs = qs.filter(Q(task__task_code__icontains=task_filter) | Q(task__title__icontains=task_filter))

    # Real Database Metrics Aggregations
    user_qs = TimeEntry.objects.filter(workspace=workspace, user=request.user)
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    today_secs = user_qs.filter(started_at__date=today).aggregate(s=Sum('duration_seconds'))['s'] or 0
    week_secs = user_qs.filter(started_at__date__gte=start_of_week).aggregate(s=Sum('duration_seconds'))['s'] or 0
    month_secs = user_qs.filter(started_at__date__gte=start_of_month).aggregate(s=Sum('duration_seconds'))['s'] or 0

    # Team metric for Managers/Admins
    team_week_secs = 0
    if is_privileged:
        team_week_secs = TimeEntry.objects.filter(
            workspace=workspace,
            started_at__date__gte=start_of_week
        ).aggregate(s=Sum('duration_seconds'))['s'] or 0

    # Check for active running or paused timer for current user
    active_timer = TimeEntry.objects.filter(
        workspace=workspace,
        user=request.user,
        status__in=[TimerStatus.RUNNING, TimerStatus.PAUSED]
    ).select_related('task').first()

    if not active_timer:
        # Fallback check for is_running
        active_timer = TimeEntry.objects.filter(
            workspace=workspace,
            user=request.user,
            is_running=True
        ).select_related('task').first()

    # Active tasks for stopwatch dropdown & manual entry
    available_tasks = Task.objects.filter(workspace=workspace).exclude(status=TaskStatus.DONE).order_by('-created_at')[:30]

    # Workspace members for filter (Managers/Admins)
    workspace_members = []
    if is_privileged:
        workspace_members = WorkspaceMembership.objects.filter(
            workspace=workspace,
            status=MembershipStatus.ACTIVE
        ).select_related('user').order_by('user__full_name', 'user__email')

    # Pagination
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    logs_page = paginator.get_page(page_number)

    manual_form = ManualTimeEntryForm(workspace=workspace)

    context = {
        'title': f"{workspace.name} — Time Tracking & Logs",
        'workspace': workspace,
        'membership': membership,
        'is_privileged': is_privileged,
        'logs_page': logs_page,
        'active_timer': active_timer,
        'available_tasks': available_tasks,
        'workspace_members': workspace_members,
        'manual_form': manual_form,
        'date_filter': date_filter,
        'member_filter': member_filter,
        'task_filter': task_filter,
        'today_hours': round(today_secs / 3600.0, 1),
        'week_hours': round(week_secs / 3600.0, 1),
        'month_hours': round(month_secs / 3600.0, 1),
        'team_week_hours': round(team_week_secs / 3600.0, 1) if is_privileged else None,
    }
    return render(request, 'timetracking/timesheet.html', context)


@require_POST
@workspace_member_required
def api_timer_start(request, slug):
    """
    Starts a live stopwatch timer for the current user in this workspace.
    Stops any previously active (running or paused) timer first.
    """
    workspace = request.workspace

    # Stop any existing running or paused timer for this user
    open_timers = TimeEntry.objects.filter(
        user=request.user,
        status__in=[TimerStatus.RUNNING, TimerStatus.PAUSED]
    )
    for t in open_timers:
        t.stop()

    # Legacy is_running cleanup
    legacy_running = TimeEntry.objects.filter(user=request.user, is_running=True)
    for t in legacy_running:
        t.stop()

    task_id = request.POST.get('task_id', '').strip()
    description = request.POST.get('description', '').strip()

    task = None
    if task_id:
        task = Task.objects.filter(workspace=workspace, id=task_id).first()

    now = timezone.now()
    entry = TimeEntry.objects.create(
        workspace=workspace,
        user=request.user,
        task=task,
        description=description,
        started_at=now,
        last_resumed_at=now,
        status=TimerStatus.RUNNING,
        is_running=True,
        entry_type=TimeEntryType.TIMER
    )

    # When starting tracking, if user's availability status is away/ooo/offline, automatically switch to available
    user_availability = getattr(request.user, 'availability_status', 'available')
    if user_availability in ['away', 'ooo', 'offline']:
        profile = getattr(request.user, 'profile', None)
        if profile:
            pref = profile.preferences or {}
            pref['status'] = 'available'
            profile.preferences = pref
            profile.save(update_fields=['preferences', 'updated_at'])
            user_availability = 'available'

    return JsonResponse({
        'status': 'ok',
        'timer_status': 'running',
        'is_running': True,
        'timer_id': str(entry.id),
        'task_code': f"#{entry.task.task_code}" if entry.task else "",
        'task_title': entry.task.title if entry.task else "",
        'started_at': entry.started_at.isoformat(),
        'elapsed_seconds': 0,
        'user_availability': user_availability,
    })


@require_POST
@workspace_member_required
def api_timer_pause(request, slug):
    """
    Pauses active live timer for current user.
    Preserves accumulated duration without finalizing the entry.
    """
    workspace = request.workspace
    active_timer = TimeEntry.objects.filter(
        workspace=workspace,
        user=request.user,
        status=TimerStatus.RUNNING
    ).first()

    if not active_timer:
        active_timer = TimeEntry.objects.filter(
            workspace=workspace,
            user=request.user,
            is_running=True
        ).first()

    if not active_timer:
        return JsonResponse({'status': 'error', 'message': 'No running timer found to pause.'}, status=400)

    active_timer.pause()
    return JsonResponse({
        'status': 'ok',
        'timer_status': 'paused',
        'is_running': False,
        'timer_id': str(active_timer.id),
        'elapsed_seconds': active_timer.current_duration_seconds,
        'duration_formatted': active_timer.duration_formatted,
    })


@require_POST
@workspace_member_required
def api_timer_resume(request, slug):
    """
    Resumes a paused timer for current user.
    Continues elapsed duration from preserved accumulated seconds.
    """
    workspace = request.workspace
    paused_timer = TimeEntry.objects.filter(
        workspace=workspace,
        user=request.user,
        status=TimerStatus.PAUSED
    ).first()

    if not paused_timer:
        return JsonResponse({'status': 'error', 'message': 'No paused timer found to resume.'}, status=400)

    paused_timer.resume()

    # When user resumes tracking, automatically switch availability from away/ooo/offline to available
    user_availability = getattr(request.user, 'availability_status', 'available')
    if user_availability in ['away', 'ooo', 'offline']:
        profile = getattr(request.user, 'profile', None)
        if profile:
            pref = profile.preferences or {}
            pref['status'] = 'available'
            profile.preferences = pref
            profile.save(update_fields=['preferences', 'updated_at'])
            user_availability = 'available'

    return JsonResponse({
        'status': 'ok',
        'timer_status': 'running',
        'is_running': True,
        'timer_id': str(paused_timer.id),
        'task_code': f"#{paused_timer.task.task_code}" if paused_timer.task else "",
        'task_title': paused_timer.task.title if paused_timer.task else "",
        'elapsed_seconds': paused_timer.current_duration_seconds,
        'duration_formatted': paused_timer.duration_formatted,
        'user_availability': user_availability,
    })


@require_POST
@workspace_member_required
def api_timer_stop(request, slug):
    """
    Stops the active live timer (running or paused) and finalizes elapsed duration.
    """
    workspace = request.workspace
    active_timer = TimeEntry.objects.filter(
        workspace=workspace,
        user=request.user,
        status__in=[TimerStatus.RUNNING, TimerStatus.PAUSED]
    ).first()

    if not active_timer:
        active_timer = TimeEntry.objects.filter(
            workspace=workspace,
            user=request.user,
            is_running=True
        ).first()

    if not active_timer:
        return JsonResponse({'status': 'error', 'message': 'No active timer found to stop.'}, status=400)

    active_timer.stop()
    return JsonResponse({
        'status': 'ok',
        'timer_status': 'completed',
        'is_running': False,
        'duration_seconds': active_timer.duration_seconds,
        'duration_formatted': active_timer.duration_formatted,
        'hours_decimal': active_timer.hours_decimal
    })


@workspace_member_required
def api_timer_status(request, slug):
    """
    Returns active timer state (idle, running, paused) for live synchronization.
    """
    workspace = request.workspace
    active_timer = TimeEntry.objects.filter(
        workspace=workspace,
        user=request.user,
        status__in=[TimerStatus.RUNNING, TimerStatus.PAUSED]
    ).select_related('task').first()

    if not active_timer:
        active_timer = TimeEntry.objects.filter(
            workspace=workspace,
            user=request.user,
            is_running=True
        ).select_related('task').first()

    if not active_timer:
        return JsonResponse({'status': 'idle', 'timer_status': 'idle', 'is_running': False})

    is_paused = (active_timer.status == TimerStatus.PAUSED)
    return JsonResponse({
        'status': 'paused' if is_paused else 'running',
        'timer_status': 'paused' if is_paused else 'running',
        'is_running': not is_paused,
        'timer_id': str(active_timer.id),
        'task_code': f"#{active_timer.task.task_code}" if active_timer.task else "",
        'task_title': active_timer.task.title if active_timer.task else "",
        'started_at': active_timer.started_at.isoformat(),
        'elapsed_seconds': active_timer.current_duration_seconds,
    })


@require_POST
@workspace_member_required
def manual_time_entry(request, slug):
    """
    Records a manual time entry with date, hours, minutes, task, and description.
    """
    workspace = request.workspace
    form = ManualTimeEntryForm(workspace, request.POST)

    if form.is_valid():
        hours = form.cleaned_data['hours']
        minutes = form.cleaned_data['minutes']
        total_seconds = (hours * 3600) + (minutes * 60)
        date = form.cleaned_data['date']
        task = form.cleaned_data['task']
        description = form.cleaned_data['description']

        started_at = timezone.datetime.combine(date, timezone.now().time())
        started_at = timezone.make_aware(started_at) if timezone.is_naive(started_at) else started_at

        TimeEntry.objects.create(
            workspace=workspace,
            user=request.user,
            task=task,
            description=description,
            started_at=started_at,
            ended_at=started_at + timedelta(seconds=total_seconds),
            duration_seconds=total_seconds,
            is_running=False,
            entry_type=TimeEntryType.MANUAL
        )
        messages.success(request, f"Logged {hours}h {minutes}m successfully.")
    else:
        for err_list in form.errors.values():
            for err in err_list:
                messages.error(request, err)

    return redirect('timetracking:workspace_timesheet', slug=slug)


@require_POST
@workspace_member_required
def delete_time_entry(request, slug, entry_id):
    """
    Deletes a time entry with strict server-side permission checks (owner or Manager/Admin).
    """
    workspace = request.workspace
    entry = get_object_or_404(TimeEntry, id=entry_id, workspace=workspace)

    can_delete = (
        entry.user == request.user or
        request.membership.is_admin or
        request.membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )

    if not can_delete:
        return HttpResponseForbidden("Permission Denied: You cannot delete another member's time log.")

    entry.delete()
    messages.success(request, "Time log deleted successfully.")
    return redirect('timetracking:workspace_timesheet', slug=slug)


@workspace_member_required
def export_timesheet_csv(request, slug):
    """
    Exports filtered timesheet logs to a clean CSV file for team leads.
    """
    workspace = request.workspace
    membership = request.membership

    is_privileged = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )

    qs = TimeEntry.objects.filter(workspace=workspace).select_related('user', 'task').order_by('-started_at')
    if not is_privileged:
        qs = qs.filter(user=request.user)

    response = HttpResponse(content_type='text/csv')
    filename = f"timesheet_{workspace.slug}_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Member Name', 'Contributor ID', 'Email', 'Task ID', 'Task Title', 'Duration (Hours)', 'Duration (Formatted)', 'Type', 'Description'])

    for e in qs:
        writer.writerow([
            e.started_at.strftime('%Y-%m-%d %H:%M'),
            e.user.full_name or e.user.email,
            e.user.contributor_id or '—',
            e.user.email,
            f"#{e.task.task_code}" if e.task else '—',
            e.task.title if e.task else '—',
            e.hours_decimal,
            e.duration_formatted,
            e.get_entry_type_display(),
            e.description
        ])

    return response
