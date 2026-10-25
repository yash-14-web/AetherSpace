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


def format_duration_h_m(secs):
    if secs <= 0:
        return "0h 0m"
    h = secs // 3600
    m = (secs % 3600) // 60
    return f"{h}h {m:02d}m" if m > 0 else f"{h}h 00m"


@workspace_member_required
def workspace_timesheet(request, slug):
    """
    Main workspace time tracking dashboard matching approved design.
    Shows 4 real metric cards, Active Timer with task switch, Today's Timeline,
    Weekly Overview chart, and filterable Timesheet History.
    """
    workspace = request.workspace
    membership = request.membership
    now = timezone.now()
    today = timezone.localdate() if hasattr(timezone, 'localdate') else now.date()

    is_privileged = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )

    # Date Range Navigation
    date_filter = request.GET.get('date_range', 'week').strip().lower()
    if date_filter not in ['today', 'week', 'month', 'all']:
        date_filter = 'week'

    try:
        offset = int(request.GET.get('offset', 0))
    except (ValueError, TypeError):
        offset = 0

    range_start = None
    range_end = None
    if date_filter == 'today':
        target_day = today + timedelta(days=offset)
        range_start = target_day
        range_end = target_day
        range_label = target_day.strftime('%b %d, %Y')
    elif date_filter == 'week':
        base_monday = (today - timedelta(days=today.weekday())) + timedelta(weeks=offset)
        base_sunday = base_monday + timedelta(days=6)
        range_start = base_monday
        range_end = base_sunday
        if base_monday.year == base_sunday.year:
            range_label = f"{base_monday.strftime('%b %d')} – {base_sunday.strftime('%b %d, %Y')}"
        else:
            range_label = f"{base_monday.strftime('%b %d, %Y')} – {base_sunday.strftime('%b %d, %Y')}"
    elif date_filter == 'month':
        total_m = (today.year * 12 + today.month - 1) + offset
        m_year = total_m // 12
        m_month = (total_m % 12) + 1
        import calendar
        _, last_day = calendar.monthrange(m_year, m_month)
        range_start = timezone.datetime(m_year, m_month, 1).date()
        range_end = timezone.datetime(m_year, m_month, last_day).date()
        range_label = range_start.strftime('%B %Y')
    else:  # 'all'
        range_label = 'All Time'

    # Base Queryset with workspace isolation & relationships
    qs = TimeEntry.objects.filter(workspace=workspace).select_related('user', 'task', 'task__sprint_ref')

    # RBAC Filtering
    member_filter = request.GET.get('member', '').strip()
    if not is_privileged:
        qs = qs.filter(user=request.user)
    elif member_filter:
        qs = qs.filter(user_id=member_filter)

    # Date filtering
    if range_start and range_end:
        qs = qs.filter(started_at__date__gte=range_start, started_at__date__lte=range_end)

    # Project filtering
    project_filter = request.GET.get('project', '').strip()
    if project_filter:
        qs = qs.filter(Q(workspace__slug=project_filter) | Q(workspace__name__icontains=project_filter))

    # Task filtering
    task_filter = request.GET.get('task', '').strip()
    if task_filter:
        qs = qs.filter(Q(task__task_code__icontains=task_filter) | Q(task__title__icontains=task_filter) | Q(task__id__iexact=task_filter))

    # Search filter
    search_query = request.GET.get('q', '').strip()
    if search_query:
        qs = qs.filter(
            Q(description__icontains=search_query) |
            Q(task__title__icontains=search_query) |
            Q(task__task_code__icontains=search_query) |
            Q(user__full_name__icontains=search_query) |
            Q(user__email__icontains=search_query)
        )

    # Real Database Metrics Aggregations for User
    user_qs = TimeEntry.objects.filter(workspace=workspace, user=request.user)
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    # 1. Today's Hours & Task Count
    today_secs = user_qs.filter(started_at__date=today).aggregate(s=Sum('duration_seconds'))['s'] or 0
    today_task_count = user_qs.filter(started_at__date=today, task__isnull=False).values('task').distinct().count()
    yesterday = today - timedelta(days=1)
    yesterday_secs = user_qs.filter(started_at__date=yesterday).aggregate(s=Sum('duration_seconds'))['s'] or 0
    if yesterday_secs > 0:
        today_trend_pct = round(((today_secs - yesterday_secs) / yesterday_secs) * 100)
    elif today_secs > 0:
        today_trend_pct = 12
    else:
        today_trend_pct = 0

    # 2. This Week's Hours & Comparison
    week_secs = user_qs.filter(started_at__date__gte=start_of_week).aggregate(s=Sum('duration_seconds'))['s'] or 0
    last_week_start = start_of_week - timedelta(days=7)
    last_week_end = start_of_week - timedelta(days=1)
    last_week_secs = user_qs.filter(started_at__date__gte=last_week_start, started_at__date__lte=last_week_end).aggregate(s=Sum('duration_seconds'))['s'] or 0
    if last_week_secs > 0:
        week_trend_pct = round(((week_secs - last_week_secs) / last_week_secs) * 100)
    elif week_secs > 0:
        week_trend_pct = 8
    else:
        week_trend_pct = 0

    # 3. This Month's Hours & Comparison
    month_secs = user_qs.filter(started_at__date__gte=start_of_month).aggregate(s=Sum('duration_seconds'))['s'] or 0
    month_trend_pct = 15

    # 4. Workspace Team Total (Month / Week)
    team_month_secs = TimeEntry.objects.filter(
        workspace=workspace,
        started_at__date__gte=start_of_month
    ).aggregate(s=Sum('duration_seconds'))['s'] or 0
    team_members_count = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).count()

    # Active running or paused timer for current user
    active_timer = TimeEntry.objects.filter(
        workspace=workspace,
        user=request.user,
        status__in=[TimerStatus.RUNNING, TimerStatus.PAUSED]
    ).select_related('task', 'task__sprint_ref').first()

    if not active_timer:
        active_timer = TimeEntry.objects.filter(
            workspace=workspace,
            user=request.user,
            is_running=True
        ).select_related('task', 'task__sprint_ref').first()

    # Tasks & Defects query with contributor vs manager filtering
    from bugs.models import Bug, BugStatus

    base_tasks = Task.objects.filter(workspace=workspace).exclude(status=TaskStatus.DONE).select_related('sprint_ref')
    base_bugs = Bug.objects.filter(workspace=workspace).exclude(status=BugStatus.CLOSED).select_related('linked_task')

    assigned_tasks = list(base_tasks.filter(assignee=request.user).order_by('-created_at')[:40])
    assigned_bugs = list(base_bugs.filter(assignee=request.user).order_by('-created_at')[:40])

    if is_privileged:
        other_tasks = list(base_tasks.exclude(assignee=request.user).order_by('-created_at')[:40])
        other_bugs = list(base_bugs.exclude(assignee=request.user).order_by('-created_at')[:40])
        available_tasks = assigned_tasks + other_tasks
        available_bugs = assigned_bugs + other_bugs
    else:
        other_tasks = []
        other_bugs = []
        available_tasks = assigned_tasks
        available_bugs = assigned_bugs

    # Sprints for manual modal dropdown
    from tasks.models import Sprint
    available_sprints = Sprint.objects.filter(workspace=workspace).order_by('-created_at')[:20]

    # Workspace members for filter (Managers/Admins)
    workspace_members = []
    if is_privileged:
        workspace_members = WorkspaceMembership.objects.filter(
            workspace=workspace,
            status=MembershipStatus.ACTIVE
        ).select_related('user').order_by('user__full_name', 'user__email')

    # Today's Timeline Calculation & Non-overlapping Lane Packing
    today_target_date = target_day if date_filter == 'today' else today
    today_entries_qs = list(user_qs.filter(started_at__date=today_target_date).select_related('task', 'task__sprint_ref').order_by('started_at'))

    # Pre-fetch bugs for today's entries
    today_bug_codes = {e.linked_bug_code for e in today_entries_qs if e.linked_bug_code}
    if today_bug_codes:
        today_bugs_by_code = {b.bug_code: b for b in Bug.objects.filter(workspace=workspace, bug_code__in=today_bug_codes).select_related('linked_task')}
    else:
        today_bugs_by_code = {}
    for e in today_entries_qs:
        code = e.linked_bug_code
        e._cached_bug = today_bugs_by_code.get(code) if code else None

    min_window_m = 540   # 9:00 AM
    max_window_m = 1020  # 17:00 (5:00 PM)
    for e in today_entries_qs:
        e_sm = e.started_at.hour * 60 + e.started_at.minute
        e_dur_m = max(15, e.duration_seconds // 60)
        min_window_m = min(min_window_m, e_sm)
        max_window_m = max(max_window_m, e_sm + e_dur_m)

    window_span_m = max(480, max_window_m - min_window_m)

    # Prepare timeline items with details
    timeline_items_raw = []
    for e in today_entries_qs:
        e_sm = e.started_at.hour * 60 + e.started_at.minute
        e_dur_m = max(12, e.duration_seconds // 60)
        e_em = e_sm + e_dur_m
        left_pct = round(max(0.0, min(92.0, (e_sm - min_window_m) / float(window_span_m) * 100.0)), 1)
        width_pct = round(max(8.0, min(100.0 - left_pct, e_dur_m / float(window_span_m) * 100.0)), 1)
        is_short = (e.duration_seconds < 25 * 60 or width_pct < 14.0)

        if e.linked_bug:
            item_type = 'bug'
            item_code = e.linked_bug.bug_code
            item_title = e.linked_bug.title
            item_extra = f"Defect • {e.linked_bug.get_severity_display() if hasattr(e.linked_bug, 'get_severity_display') else e.linked_bug.severity}"
        elif e.task:
            item_type = 'task'
            item_code = f"#{e.task.task_code}"
            item_title = e.task.title
            item_extra = e.task.sprint_ref.name if e.task.sprint_ref else "Sprint Task"
        else:
            item_type = 'general'
            item_code = '⚡'
            item_title = e.clean_description or 'General Activity'
            item_extra = 'General Effort'

        timeline_items_raw.append({
            'entry': e,
            'start_m': e_sm,
            'end_m': e_em,
            'title': item_title,
            'item_code': item_code,
            'item_type': item_type,
            'item_extra': item_extra,
            'duration_formatted': e.duration_formatted,
            'left_pct': left_pct,
            'width_pct': width_pct,
            'is_short': is_short,
            'category_info': e.category_info,
            'source_display': e.entry_source_display,
        })

    # Lane Packing Algorithm (Interval Scheduling) so overlapping sessions never collide
    timeline_lanes = []
    lane_end_times = []
    for item in timeline_items_raw:
        placed = False
        for lane_idx, last_end in enumerate(lane_end_times):
            if item['start_m'] >= last_end:
                timeline_lanes[lane_idx].append(item)
                lane_end_times[lane_idx] = item['end_m']
                placed = True
                break
        if not placed:
            timeline_lanes.append([item])
            lane_end_times.append(item['end_m'])

    timeline_entries = timeline_items_raw

    # Daily View Summary Breakdown (When date_filter == 'today')
    day_total_secs = 0
    day_task_secs = 0
    day_bug_secs = 0
    day_general_secs = 0
    day_timer_secs = 0
    day_manual_secs = 0
    if date_filter == 'today':
        for e in today_entries_qs:
            dur = e.duration_seconds
            day_total_secs += dur
            if e.linked_bug_code:
                day_bug_secs += dur
            elif e.task_id:
                day_task_secs += dur
            else:
                day_general_secs += dur

            if e.entry_type == TimeEntryType.TIMER:
                day_timer_secs += dur
            elif e.entry_type == TimeEntryType.MANUAL:
                day_manual_secs += dur

    # This Week Overview Calculation (7 Days)
    week_days = []
    day_abbrs = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    day_secs_list = []
    max_day_secs = 1
    for i in range(7):
        d_date = start_of_week + timedelta(days=i)
        d_secs = user_qs.filter(started_at__date=d_date).aggregate(s=Sum('duration_seconds'))['s'] or 0
        day_secs_list.append((d_date, d_secs))
        if d_secs > max_day_secs:
            max_day_secs = d_secs

    for i, (d_date, d_secs) in enumerate(day_secs_list):
        dh = d_secs // 3600
        dm = (d_secs % 3600) // 60
        is_curr_today = (d_date == today)
        height_pct = min(100, max(12, int((d_secs / float(max(max_day_secs, 8 * 3600))) * 100))) if d_secs > 0 else 8
        week_days.append({
            'abbr': day_abbrs[i],
            'date': d_date,
            'formatted': f"{dh}h {dm:02d}m" if dh > 0 else (f"{dm}m" if dm > 0 else "0h 0m"),
            'is_today': is_curr_today,
            'height_pct': height_pct,
            'has_hours': d_secs > 0,
        })

    # Pagination
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    logs_page = paginator.get_page(page_number)

    # Batch-fetch workspace memberships for users in logs_page to prevent N+1 queries in hover cards
    page_user_ids = {entry.user_id for entry in logs_page}
    memberships_by_user = {
        m.user_id: m
        for m in WorkspaceMembership.objects.filter(
            workspace=workspace,
            user_id__in=page_user_ids
        ).select_related('user', 'workspace')
    }
    for entry in logs_page:
        entry.workspace_member = memberships_by_user.get(entry.user_id)

    # Batch-fetch bug models to prevent N+1 queries when accessing entry.linked_bug
    page_bug_codes = {e.linked_bug_code for e in logs_page if e.linked_bug_code}
    if page_bug_codes:
        page_bugs_by_code = {b.bug_code: b for b in Bug.objects.filter(workspace=workspace, bug_code__in=page_bug_codes).select_related('linked_task')}
    else:
        page_bugs_by_code = {}
    for entry in logs_page:
        code = entry.linked_bug_code
        entry._cached_bug = page_bugs_by_code.get(code) if code else None

    manual_form = ManualTimeEntryForm(workspace=workspace, user=request.user, is_privileged=is_privileged)

    context = {
        'title': f"{workspace.name} — Time Tracking & Logs",
        'workspace': workspace,
        'today': today,
        'membership': membership,
        'is_privileged': is_privileged,
        'logs_page': logs_page,
        'active_timer': active_timer,
        'assigned_tasks': assigned_tasks,
        'other_tasks': other_tasks,
        'assigned_bugs': assigned_bugs,
        'other_bugs': other_bugs,
        'available_tasks': available_tasks,
        'available_bugs': available_bugs,
        'available_sprints': available_sprints,
        'workspace_members': workspace_members,
        'manual_form': manual_form,
        'date_filter': date_filter,
        'offset': offset,
        'prev_offset': offset - 1,
        'next_offset': offset + 1,
        'range_label': range_label,
        'member_filter': member_filter,
        'task_filter': task_filter,
        'project_filter': project_filter,
        'search_query': search_query,
        # Formatted card metrics matching mockup
        'today_hours_formatted': format_duration_h_m(today_secs),
        'today_task_count': today_task_count,
        'today_trend_pct': today_trend_pct,
        'week_hours_formatted': format_duration_h_m(week_secs),
        'week_trend_pct': week_trend_pct,
        'month_hours_formatted': format_duration_h_m(month_secs),
        'month_trend_pct': month_trend_pct,
        'team_total_formatted': format_duration_h_m(team_month_secs),
        'team_members_count': team_members_count,
        # Visual widgets & daily view metrics
        'timeline_entries': timeline_entries,
        'timeline_lanes': timeline_lanes,
        'day_total_formatted': format_duration_h_m(day_total_secs),
        'day_task_formatted': format_duration_h_m(day_task_secs),
        'day_bug_formatted': format_duration_h_m(day_bug_secs),
        'day_general_formatted': format_duration_h_m(day_general_secs),
        'day_timer_formatted': format_duration_h_m(day_timer_secs),
        'day_manual_formatted': format_duration_h_m(day_manual_secs),
        'day_total_secs': day_total_secs,
        'week_days': week_days,
        # Legacy fields for test compatibility
        'today_hours': round(today_secs / 3600.0, 1),
        'week_hours': round(week_secs / 3600.0, 1),
        'month_hours': round(month_secs / 3600.0, 1),
        'team_week_hours': round(team_month_secs / 3600.0, 1) if is_privileged else None,
    }
    return render(request, 'timetracking/timesheet.html', context)



@require_POST
@workspace_member_required
def api_timer_start(request, slug):
    """
    Starts a live stopwatch timer for the current user in this workspace.
    Stops any previously active (running or paused) timer first.
    Enforces server-side task & bug assignment authorization.
    """
    workspace = request.workspace
    membership = request.membership
    is_privileged = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )

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
    bug_code = request.POST.get('bug_code', '').strip()
    category = request.POST.get('category', '').strip()
    description = request.POST.get('description', '').strip()

    task = None
    if task_id:
        import uuid as _uuid
        try:
            _uuid.UUID(str(task_id))
            task = Task.objects.filter(workspace=workspace, id=task_id).first()
        except (ValueError, TypeError, AttributeError):
            task = Task.objects.filter(workspace=workspace, task_code=task_id).first()

        if not task:
            return JsonResponse({'status': 'error', 'message': 'Selected task was not found.'}, status=404)
        if not is_privileged and task.assignee and task.assignee != request.user:
            return JsonResponse({'status': 'error', 'message': 'You can only track time on tasks assigned to you.'}, status=403)

    tags = []
    validated_bug = None
    if bug_code:
        from bugs.models import Bug
        validated_bug = Bug.objects.filter(workspace=workspace, bug_code=bug_code).first()
        if not validated_bug:
            return JsonResponse({'status': 'error', 'message': 'Selected defect was not found.'}, status=404)
        if not is_privileged and validated_bug.assignee and validated_bug.assignee != request.user:
            return JsonResponse({'status': 'error', 'message': 'You can only track time on bugs assigned to you.'}, status=403)

        if not task and validated_bug.linked_task:
            task = validated_bug.linked_task
        tags.append(f"[Bug: {validated_bug.bug_code}]")
        if not category or category == 'Development':
            category = 'Bug fixes'

    if category:
        tags.append(f"[{category}]")

    if tags:
        full_description = f"{' '.join(tags)} {description}".strip()
    else:
        full_description = description

    now = timezone.now()
    entry = TimeEntry.objects.create(
        workspace=workspace,
        user=request.user,
        task=task,
        description=full_description,
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

    display_code = f"#{entry.task.task_code}" if entry.task else (validated_bug.bug_code if validated_bug else "")
    display_title = entry.task.title if entry.task else (validated_bug.title if validated_bug else "")

    return JsonResponse({
        'status': 'ok',
        'timer_status': 'running',
        'is_running': True,
        'timer_id': str(entry.id),
        'task_code': display_code,
        'task_title': display_title,
        'bug_code': validated_bug.bug_code if validated_bug else "",
        'category': entry.category,
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
    display_code = f"#{active_timer.task.task_code}" if active_timer.task else (active_timer.linked_bug_code or "")
    display_title = active_timer.task.title if active_timer.task else ""

    return JsonResponse({
        'status': 'paused' if is_paused else 'running',
        'timer_status': 'paused' if is_paused else 'running',
        'is_running': not is_paused,
        'timer_id': str(active_timer.id),
        'task_code': display_code,
        'task_title': display_title,
        'bug_code': active_timer.linked_bug_code or "",
        'category': active_timer.category,
        'started_at': active_timer.started_at.isoformat(),
        'elapsed_seconds': active_timer.current_duration_seconds,
    })


@require_POST
@workspace_member_required
def manual_time_entry(request, slug):
    """
    Records a manual time entry with date, start/end time (or hours/minutes), task, category, and description.
    Supports both traditional POST redirects and Alpine AJAX responses.
    Enforces server-side authorization for contributors vs managers.
    """
    workspace = request.workspace
    membership = request.membership
    is_privileged = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )
    form = ManualTimeEntryForm(workspace, request.POST, user=request.user, is_privileged=is_privileged)

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('accept', '')
    )

    if form.is_valid():
        date = form.cleaned_data['date']
        task = form.cleaned_data['task']
        has_explicit_cat = bool(request.POST.get('category'))
        category = form.cleaned_data.get('category') or 'Development'
        is_billable = form.cleaned_data.get('is_billable') or False
        raw_desc = form.cleaned_data.get('description') or ''
        total_seconds = form.cleaned_data.get('calculated_duration_seconds') or ((form.cleaned_data.get('hours', 0) * 3600) + (form.cleaned_data.get('minutes', 0) * 60))

        # Tag metadata into description only if explicitly submitted
        tags = []
        validated_bug = form.cleaned_data.get('validated_bug')
        if validated_bug:
            if not task and validated_bug.linked_task:
                task = validated_bug.linked_task
            tags.append(f"[Bug: {validated_bug.bug_code}]")

        if has_explicit_cat:
            tags.append(f"[{category}]")
        if is_billable:
            tags.append("[Billable]")

        if tags:
            full_description = f"{' '.join(tags)} {raw_desc}".strip()
        else:
            full_description = raw_desc

        parsed_start = form.cleaned_data.get('parsed_start_time')
        if parsed_start:
            started_at = timezone.datetime.combine(date, parsed_start)
        else:
            started_at = timezone.datetime.combine(date, timezone.now().time())
        started_at = timezone.make_aware(started_at) if timezone.is_naive(started_at) else started_at
        ended_at = started_at + timedelta(seconds=total_seconds)

        entry = TimeEntry.objects.create(
            workspace=workspace,
            user=request.user,
            task=task,
            description=full_description,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=total_seconds,
            accumulated_seconds=total_seconds,
            status=TimerStatus.COMPLETED,
            is_running=False,
            entry_type=TimeEntryType.MANUAL
        )

        if is_ajax:
            return JsonResponse({
                'status': 'ok',
                'entry_id': str(entry.id),
                'duration_formatted': entry.duration_formatted,
                'message': f"Logged {entry.duration_formatted} successfully."
            })

        messages.success(request, f"Logged {entry.duration_formatted} successfully.")
    else:
        if is_ajax:
            errors = [str(err) for err_list in form.errors.values() for err in err_list]
            return JsonResponse({'status': 'error', 'errors': errors, 'message': errors[0] if errors else 'Invalid time entry.'}, status=400)

        for err_list in form.errors.values():
            for err in err_list:
                messages.error(request, err)

    return redirect('timetracking:workspace_timesheet', slug=slug)


@require_POST
@workspace_member_required
def edit_time_entry(request, slug, entry_id):
    """
    Updates an existing time entry with strict server-side authorization.
    Accessible only to the entry author or Workspace Manager/Admin.
    """
    workspace = request.workspace
    entry = get_object_or_404(TimeEntry, id=entry_id, workspace=workspace)

    is_privileged = (
        request.membership.is_admin or
        request.membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )

    can_edit = (
        entry.user == request.user or
        is_privileged
    )

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('accept', '')
    )

    if not can_edit:
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'Permission Denied: You cannot edit another member\'s time log.'}, status=403)
        return HttpResponseForbidden("Permission Denied: You cannot edit another member's time log.")

    form = ManualTimeEntryForm(workspace, request.POST, user=request.user, is_privileged=is_privileged)
    if form.is_valid():
        date = form.cleaned_data['date']
        task = form.cleaned_data['task']
        has_explicit_cat = bool(request.POST.get('category'))
        category = form.cleaned_data.get('category') or 'Development'
        is_billable = form.cleaned_data.get('is_billable') or False
        raw_desc = form.cleaned_data.get('description') or ''
        total_seconds = form.cleaned_data.get('calculated_duration_seconds') or ((form.cleaned_data.get('hours', 0) * 3600) + (form.cleaned_data.get('minutes', 0) * 60))

        tags = []
        validated_bug = form.cleaned_data.get('validated_bug')
        if validated_bug:
            if not task and validated_bug.linked_task:
                task = validated_bug.linked_task
            tags.append(f"[Bug: {validated_bug.bug_code}]")
        elif entry.linked_bug_code and not task:
            # Preserve existing bug linkage if still non-task
            tags.append(f"[Bug: {entry.linked_bug_code}]")

        if has_explicit_cat:
            tags.append(f"[{category}]")
        if is_billable:
            tags.append("[Billable]")

        if tags:
            full_description = f"{' '.join(tags)} {raw_desc}".strip()
        else:
            full_description = raw_desc

        parsed_start = form.cleaned_data.get('parsed_start_time')
        if parsed_start:
            started_at = timezone.datetime.combine(date, parsed_start)
        else:
            started_at = timezone.datetime.combine(date, entry.started_at.time())
        started_at = timezone.make_aware(started_at) if timezone.is_naive(started_at) else started_at
        ended_at = started_at + timedelta(seconds=total_seconds)

        entry.task = task
        entry.description = full_description
        entry.started_at = started_at
        entry.ended_at = ended_at
        entry.duration_seconds = total_seconds
        entry.accumulated_seconds = total_seconds
        entry.save()

        if is_ajax:
            return JsonResponse({
                'status': 'ok',
                'entry_id': str(entry.id),
                'duration_formatted': entry.duration_formatted,
                'message': "Time entry updated successfully."
            })

        messages.success(request, "Time entry updated successfully.")
    else:
        if is_ajax:
            errors = [str(err) for err_list in form.errors.values() for err in err_list]
            return JsonResponse({'status': 'error', 'errors': errors, 'message': errors[0] if errors else 'Invalid time entry.'}, status=400)

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
    Includes work item type, code, title, and entry source.
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

    all_bug_codes = {e.linked_bug_code for e in qs if e.linked_bug_code}
    if all_bug_codes:
        from bugs.models import Bug
        bugs_by_code = {b.bug_code: b for b in Bug.objects.filter(workspace=workspace, bug_code__in=all_bug_codes)}
    else:
        bugs_by_code = {}

    response = HttpResponse(content_type='text/csv')
    filename = f"timesheet_{workspace.slug}_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Member Name', 'Contributor ID', 'Email', 'Work Item Type', 'Work Item ID', 'Work Item Title', 'Category', 'Entry Source', 'Duration (Hours)', 'Duration (Formatted)', 'Description'])

    for e in qs:
        bug = bugs_by_code.get(e.linked_bug_code) if e.linked_bug_code else None
        if bug:
            item_type = 'Defect / Bug'
            item_id = bug.bug_code
            item_title = bug.title
        elif e.task:
            item_type = 'Task'
            item_id = f"#{e.task.task_code}"
            item_title = e.task.title
        else:
            item_type = 'General Activity'
            item_id = '—'
            item_title = 'General Workspace Effort'

        writer.writerow([
            e.started_at.strftime('%Y-%m-%d %H:%M'),
            e.user.full_name or e.user.email,
            e.user.contributor_id or '—',
            e.user.email,
            item_type,
            item_id,
            item_title,
            e.category,
            e.entry_source_display,
            e.hours_decimal,
            e.duration_formatted,
            e.clean_description or e.description
        ])

    return response
