import calendar as py_calendar
from datetime import datetime, date, time, timedelta
from django.utils import timezone
from django.urls import reverse
from django.db.models import Q

from tasks.models import Task, TaskStatus
from bugs.models import Bug, BugStatus
from meetings.models import Meeting, MeetingStatus
from .models import CalendarEvent, CalendarEventType, CalendarEventAttendee, EventStatus


def get_unified_schedule_items(workspace, start_date, end_date, categories=None, member_id=None):
    """
    Fetches and unifies schedule items across CalendarEvents, Tasks, Bugs, and Meetings
    for a given workspace and date range.
    """
    items = []
    current_tz = timezone.get_current_timezone()

    dt_start = timezone.make_aware(datetime.combine(start_date, time(0, 0, 0)), current_tz)
    dt_end = timezone.make_aware(datetime.combine(end_date, time(23, 59, 59)), current_tz)

    active_cats = categories if categories is not None else ['events', 'tasks', 'bugs', 'meetings', 'milestones']

    # 1. Calendar Events (Events & Milestones)
    if 'events' in active_cats or 'milestones' in active_cats:
        events_qs = CalendarEvent.objects.filter(
            workspace=workspace,
            start_at__lte=dt_end,
            end_at__gte=dt_start
        ).exclude(status=EventStatus.CANCELLED).select_related('created_by', 'linked_task', 'linked_bug', 'linked_meeting')

        if member_id:
            events_qs = events_qs.filter(Q(created_by_id=member_id) | Q(attendees__user_id=member_id)).distinct()

        for ev in events_qs:
            is_milestone = (ev.event_type == CalendarEventType.MILESTONE)
            if is_milestone and 'milestones' not in active_cats:
                continue
            if not is_milestone and 'events' not in active_cats:
                continue

            local_start = ev.start_at.astimezone(current_tz)
            local_end = ev.end_at.astimezone(current_tz)

            time_str = "All day" if ev.is_all_day else f"{local_start.strftime('%I:%M %p')} - {local_end.strftime('%I:%M %p')}"
            short_time = "All day" if ev.is_all_day else local_start.strftime('%I:%M %p')

            category = 'milestone' if is_milestone else 'event'
            color = 'amber' if is_milestone else 'blue'

            items.append({
                'id': f"event-{ev.id}",
                'raw_id': str(ev.id),
                'title': ev.title,
                'date': local_start.date(),
                'end_date': local_end.date(),
                'start_time': short_time,
                'time_display': time_str,
                'is_all_day': ev.is_all_day,
                'category': category,
                'category_label': 'Milestone' if is_milestone else 'Event',
                'color': color,
                'code': '',
                'priority': '',
                'status': ev.get_status_display(),
                'assignee_name': ev.created_by.get_full_name() or ev.created_by.username if ev.created_by else 'Workspace',
                'assignee_initials': (ev.created_by.get_full_name() or ev.created_by.username)[:2].upper() if ev.created_by else 'WS',
                'detail_url': reverse('calendars:event_detail', kwargs={'slug': workspace.slug, 'event_id': ev.id}),
                'model_obj': ev,
                'dt_sort': ev.start_at
            })

    # 2. Tasks with due dates
    if 'tasks' in active_cats:
        tasks_qs = Task.objects.filter(
            workspace=workspace,
            due_date__gte=start_date,
            due_date__lte=end_date
        ).select_related('assignee')

        if member_id:
            tasks_qs = tasks_qs.filter(assignee_id=member_id)

        for t in tasks_qs:
            items.append({
                'id': f"task-{t.id}",
                'raw_id': str(t.id),
                'title': t.title,
                'date': t.due_date,
                'end_date': t.due_date,
                'start_time': 'Due',
                'time_display': 'Due by End of Day',
                'is_all_day': True,
                'category': 'task',
                'category_label': 'Task',
                'color': 'emerald',
                'code': t.task_code,
                'priority': t.get_priority_display(),
                'status': t.get_status_display(),
                'assignee_name': t.assignee.get_full_name() or t.assignee.username if t.assignee else 'Unassigned',
                'assignee_initials': (t.assignee.get_full_name() or t.assignee.username)[:2].upper() if t.assignee else 'UN',
                'detail_url': reverse('tasks:task_detail', kwargs={'slug': workspace.slug, 'task_code': t.task_code}),
                'model_obj': t,
                'dt_sort': timezone.make_aware(datetime.combine(t.due_date, time(17, 0, 0)), current_tz)
            })

    # 3. Bugs with due dates
    if 'bugs' in active_cats:
        bugs_qs = Bug.objects.filter(
            workspace=workspace,
            due_date__gte=start_date,
            due_date__lte=end_date
        ).select_related('assignee')

        if member_id:
            bugs_qs = bugs_qs.filter(assignee_id=member_id)

        for b in bugs_qs:
            items.append({
                'id': f"bug-{b.id}",
                'raw_id': str(b.id),
                'title': b.title,
                'date': b.due_date,
                'end_date': b.due_date,
                'start_time': 'Due',
                'time_display': 'Due by End of Day',
                'is_all_day': True,
                'category': 'bug',
                'category_label': 'Bug',
                'color': 'rose',
                'code': b.bug_code,
                'priority': b.get_priority_display(),
                'status': b.get_status_display(),
                'assignee_name': b.assignee.get_full_name() or b.assignee.username if b.assignee else 'Unassigned',
                'assignee_initials': (b.assignee.get_full_name() or b.assignee.username)[:2].upper() if b.assignee else 'UN',
                'detail_url': reverse('bugs:bug_detail', kwargs={'slug': workspace.slug, 'bug_code': b.bug_code}),
                'model_obj': b,
                'dt_sort': timezone.make_aware(datetime.combine(b.due_date, time(17, 0, 0)), current_tz)
            })

    # 4. Meetings
    if 'meetings' in active_cats:
        meets_qs = Meeting.objects.filter(
            workspace=workspace,
            scheduled_start__lte=dt_end,
            scheduled_start__gte=dt_start
        ).exclude(status=MeetingStatus.CANCELLED).select_related('host')

        if member_id:
            meets_qs = meets_qs.filter(Q(host_id=member_id) | Q(participants__user_id=member_id)).distinct()

        for m in meets_qs:
            local_start = m.scheduled_start.astimezone(current_tz)
            local_end = m.scheduled_end.astimezone(current_tz) if m.scheduled_end else local_start + timedelta(minutes=30)
            time_str = f"{local_start.strftime('%I:%M %p')} - {local_end.strftime('%I:%M %p')}"
            short_time = local_start.strftime('%I:%M %p')

            items.append({
                'id': f"meeting-{m.id}",
                'raw_id': str(m.id),
                'title': m.title,
                'date': local_start.date(),
                'end_date': local_end.date(),
                'start_time': short_time,
                'time_display': time_str,
                'is_all_day': False,
                'category': 'meeting',
                'category_label': 'Meeting',
                'color': 'purple',
                'code': m.meeting_code,
                'priority': '',
                'status': m.get_status_display(),
                'assignee_name': m.host.get_full_name() or m.host.username if m.host else 'Host',
                'assignee_initials': (m.host.get_full_name() or m.host.username)[:2].upper() if m.host else 'MT',
                'detail_url': reverse('meetings:meeting_detail', kwargs={'slug': workspace.slug, 'meeting_code': m.meeting_code}),
                'model_obj': m,
                'dt_sort': m.scheduled_start
            })

    # Sort chronological
    items.sort(key=lambda x: x['dt_sort'])
    return items


def build_month_calendar_matrix(workspace, year, month, categories=None, member_id=None):
    """
    Builds a 7-column grid matrix for Sunday to Saturday with all padding days
    and attached schedule items.
    """
    today = timezone.localdate()

    # Determine first day and number of days in the month
    # py_calendar.monthrange returns (weekday_of_first_day, number_of_days)
    # Note: in Python calendar, Monday is 0, Sunday is 6.
    first_weekday, num_days = py_calendar.monthrange(year, month)
    # Convert to Sunday = 0
    first_sunday_col = (first_weekday + 1) % 7

    # Calculate grid boundaries
    first_date_of_month = date(year, month, 1)
    last_date_of_month = date(year, month, num_days)

    grid_start_date = first_date_of_month - timedelta(days=first_sunday_col)

    # 42 days total (6 rows of 7 days) to ensure consistent card heights
    total_cells = 42
    grid_end_date = grid_start_date + timedelta(days=total_cells - 1)

    # Fetch all items across this grid range
    all_items = get_unified_schedule_items(
        workspace=workspace,
        start_date=grid_start_date,
        end_date=grid_end_date,
        categories=categories,
        member_id=member_id
    )

    # Map items by date for fast lookup
    items_by_date = {}
    for item in all_items:
        d = item['date']
        items_by_date.setdefault(d, []).append(item)

    # Construct calendar day objects
    matrix = []
    curr_date = grid_start_date
    while curr_date <= grid_end_date:
        matrix.append({
            'date': curr_date,
            'day_number': curr_date.day,
            'is_current_month': (curr_date.month == month),
            'is_today': (curr_date == today),
            'is_past': (curr_date < today),
            'items': items_by_date.get(curr_date, [])
        })
        curr_date += timedelta(days=1)

    # Chunk into rows of 7 days
    weeks = [matrix[i:i + 7] for i in range(0, len(matrix), 7)]

    # Mini calendar for left sidebar (current month view)
    mini_calendar = {
        'year': year,
        'month': month,
        'month_name': py_calendar.month_name[month],
        'weeks': weeks,
    }

    return {
        'year': year,
        'month': month,
        'month_name': py_calendar.month_name[month],
        'weeks': weeks,
        'grid_start': grid_start_date,
        'grid_end': grid_end_date,
        'total_items_count': len(all_items),
        'mini_calendar': mini_calendar
    }


def build_agenda_stream(workspace, target_date, categories=None, member_id=None, days_ahead=14):
    """
    Builds a chronological agenda stream grouped by date starting from target_date.
    """
    end_date = target_date + timedelta(days=days_ahead)
    items = get_unified_schedule_items(
        workspace=workspace,
        start_date=target_date,
        end_date=end_date,
        categories=categories,
        member_id=member_id
    )

    today = timezone.localdate()

    # Group by date
    grouped = {}
    for it in items:
        d = it['date']
        grouped.setdefault(d, []).append(it)

    date_groups = []
    for d, group_items in sorted(grouped.items()):
        if d == today:
            group_label = f"Today, {d.strftime('%A, %b %d, %Y')}"
        elif d == today + timedelta(days=1):
            group_label = f"Tomorrow, {d.strftime('%A, %b %d, %Y')}"
        else:
            group_label = d.strftime('%A, %B %d, %Y')

        date_groups.append({
            'date': d,
            'label': group_label,
            'is_today': (d == today),
            'items': group_items
        })

    # Compute Today's summary counts
    today_items = [it for it in items if it['date'] == today]
    today_summary = {
        'tasks': sum(1 for it in today_items if it['category'] == 'task'),
        'bugs': sum(1 for it in today_items if it['category'] == 'bug'),
        'meetings': sum(1 for it in today_items if it['category'] == 'meeting'),
        'milestones': sum(1 for it in today_items if it['category'] == 'milestone'),
        'events': sum(1 for it in today_items if it['category'] == 'event'),
    }

    upcoming_items = [it for it in items if it['date'] >= today][:6]

    return {
        'date_groups': date_groups,
        'today_summary': today_summary,
        'upcoming_items': upcoming_items,
        'total_count': len(items),
    }


def build_upcoming_deadlines(workspace, timeframe_days=30, category_filter='all'):
    """
    Aggregates all deadlines and scheduled items into Today, Tomorrow, Next 7 Days,
    and Later sections with overdue calculation and summary chips.
    """
    today = timezone.localdate()
    end_date = today + timedelta(days=timeframe_days)

    cats = None
    if category_filter and category_filter != 'all':
        cats = [category_filter.lower()]

    items = get_unified_schedule_items(
        workspace=workspace,
        start_date=today,
        end_date=end_date,
        categories=cats
    )

    # Group into Today, Tomorrow, Next 7 Days, and Later
    group_today = []
    group_tomorrow = []
    group_next_7 = []
    group_later = []

    tomorrow = today + timedelta(days=1)
    day_7 = today + timedelta(days=7)

    for it in items:
        d = it['date']
        if d == today:
            group_today.append(it)
        elif d == tomorrow:
            group_tomorrow.append(it)
        elif today < d <= day_7:
            group_next_7.append(it)
        else:
            group_later.append(it)

    # Compute Overdue Items (Tasks and Bugs with due_date < today not yet resolved)
    overdue_items = []
    overdue_tasks = Task.objects.filter(
        workspace=workspace,
        due_date__lt=today
    ).exclude(status__in=[TaskStatus.DONE]).select_related('assignee').order_by('due_date')

    for t in overdue_tasks:
        days_overdue = (today - t.due_date).days
        overdue_items.append({
            'title': t.title,
            'code': t.task_code,
            'category': 'Task',
            'days_overdue': days_overdue,
            'overdue_label': f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue",
            'detail_url': reverse('tasks:task_detail', kwargs={'slug': workspace.slug, 'task_code': t.task_code}),
            'assignee': t.assignee
        })

    overdue_bugs = Bug.objects.filter(
        workspace=workspace,
        due_date__lt=today
    ).exclude(status__in=[BugStatus.RESOLVED, BugStatus.CLOSED]).select_related('assignee').order_by('due_date')

    for b in overdue_bugs:
        days_overdue = (today - b.due_date).days
        overdue_items.append({
            'title': b.title,
            'code': b.bug_code,
            'category': 'Bug',
            'days_overdue': days_overdue,
            'overdue_label': f"{days_overdue} day{'s' if days_overdue != 1 else ''} overdue",
            'detail_url': reverse('bugs:bug_detail', kwargs={'slug': workspace.slug, 'bug_code': b.bug_code}),
            'assignee': b.assignee
        })

    # Sort overdue most severe first
    overdue_items.sort(key=lambda x: x['days_overdue'], reverse=True)

    # Metric counts
    deadline_summary = {
        'tasks_due_soon': sum(1 for it in items if it['category'] == 'task'),
        'bugs_due_soon': sum(1 for it in items if it['category'] == 'bug'),
        'meetings_upcoming': sum(1 for it in items if it['category'] == 'meeting'),
        'milestones_upcoming': sum(1 for it in items if it['category'] == 'milestone'),
        'overdue_total': len(overdue_items)
    }

    return {
        'today': group_today,
        'tomorrow': group_tomorrow,
        'next_7_days': group_next_7,
        'later': group_later,
        'overdue_items': overdue_items,
        'deadline_summary': deadline_summary,
        'total_deadlines': len(items)
    }


def create_calendar_event(workspace, user, data, invitees=None):
    """
    Creates a new CalendarEvent and registers attendee relationships.
    """
    linked_meeting = data.get('linked_meeting')
    meeting_link = data.get('meeting_link', '')

    # Auto-link or create Meeting in Meet Hub if AetherSpace room is generated
    if meeting_link and '/meetings/w/' in meeting_link and not linked_meeting:
        import re
        code_match = re.search(r'meet-[a-z0-9]{4}-[a-z0-9]{4}', meeting_link)
        if code_match:
            meet_code = code_match.group(0)
            from meetings.models import Meeting, MeetingStatus, MeetingType, MeetingInvite
            existing_m = Meeting.objects.filter(workspace=workspace, meeting_code=meet_code).first()
            if not existing_m:
                existing_m = Meeting.objects.create(
                    workspace=workspace,
                    meeting_code=meet_code,
                    title=data['title'],
                    description=data.get('description', ''),
                    host=user,
                    meeting_type=MeetingType.GENERAL,
                    status=MeetingStatus.SCHEDULED,
                    scheduled_start=data['computed_start_at'],
                    scheduled_end=data['computed_end_at'],
                )
                if invitees:
                    for inv_u in invitees:
                        if inv_u != user:
                            MeetingInvite.objects.get_or_create(
                                meeting=existing_m,
                                user=inv_u,
                                defaults={'status': 'PENDING'}
                            )
            linked_meeting = existing_m

    event = CalendarEvent(
        workspace=workspace,
        title=data['title'],
        description=data.get('description', ''),
        event_type=data.get('event_type', CalendarEventType.GENERAL),
        calendar_category=data.get('calendar_category', 'WORKSPACE'),
        start_at=data['computed_start_at'],
        end_at=data['computed_end_at'],
        is_all_day=data.get('is_all_day', False),
        repeat=data.get('repeat') or 'NONE',
        location=data.get('location', ''),
        meeting_link=meeting_link,
        linked_task=data.get('linked_task'),
        linked_bug=data.get('linked_bug'),
        linked_meeting=linked_meeting,
        created_by=user
    )
    event.save()

    # Add creator as accepted attendee
    CalendarEventAttendee.objects.create(
        event=event,
        user=user,
        status='ACCEPTED'
    )

    # Add invited users
    if invitees:
        for u in invitees:
            if u != user:
                CalendarEventAttendee.objects.get_or_create(
                    event=event,
                    user=u,
                    defaults={'status': 'INVITED'}
                )

    return event
