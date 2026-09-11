import calendar as py_calendar
from datetime import datetime, date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils import timezone

from workspaces.permissions import workspace_member_required
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus
from .models import CalendarEvent, CalendarEventType, CalendarCategory, EventStatus, CalendarEventAttendee
from .forms import CalendarEventForm
from .services import (
    build_month_calendar_matrix, build_agenda_stream,
    build_upcoming_deadlines, create_calendar_event
)
from meetings.services import generate_unique_meeting_code



@login_required
def calendar_router(request):
    """
    Global entry router: redirects user to their active workspace's calendar.
    """
    active_slug = request.session.get('active_workspace_slug')
    if active_slug:
        ws = Workspace.objects.filter(
            slug=active_slug,
            memberships__user=request.user,
            memberships__status=MembershipStatus.ACTIVE
        ).first()
        if ws:
            return redirect('calendars:calendar_view', slug=ws.slug)

    first_membership = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE
    ).select_related('workspace').first()

    if first_membership:
        return redirect('calendars:calendar_view', slug=first_membership.workspace.slug)

    messages.info(request, "Please select or join a workspace to access the Calendar.")
    return redirect('workspaces:workspace_list')


@workspace_member_required
def calendar_view(request, slug):
    """
    Main Calendar Dashboard (Month / Week / Day view) with mini-calendar picker,
    multi-category filters (Events, Tasks, Bugs, Meetings, Milestones),
    and quick add shortcuts matching Screen 1.
    """
    workspace = request.workspace
    membership = request.membership

    today = timezone.localdate()

    # Parse target month and year
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
        if not (1 <= month <= 12):
            year, month = today.year, today.month
    except (ValueError, TypeError):
        year, month = today.year, today.month

    # Active view switcher: month, week, day, agenda
    active_view = request.GET.get('view', 'month').lower()
    if active_view == 'agenda':
        return redirect(f"{reverse('calendars:agenda_view', kwargs={'slug': workspace.slug})}?date={year}-{month:02d}-01")

    # Categories filter
    cats_param = request.GET.get('cats')
    if cats_param is not None:
        active_cats = [c.strip().lower() for c in cats_param.split(',') if c.strip()]
    else:
        active_cats = ['events', 'tasks', 'bugs', 'meetings', 'milestones']

    # Member filter
    member_id = request.GET.get('member')
    if member_id in ['', 'all', None]:
        member_id = None

    calendar_data = build_month_calendar_matrix(
        workspace=workspace,
        year=year,
        month=month,
        categories=active_cats,
        member_id=member_id
    )

    # Compute prev and next month
    if month == 1:
        prev_month, prev_year = 12, year - 1
        next_month, next_year = 2, year
    elif month == 12:
        prev_month, prev_year = 11, year
        next_month, next_year = 1, year + 1
    else:
        prev_month, prev_year = month - 1, year
        next_month, next_year = month + 1, year

    workspace_members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user').order_by('user__first_name', 'user__username')

    context = {
        'workspace': workspace,
        'membership': membership,
        'year': year,
        'month': month,
        'month_name': py_calendar.month_name[month],
        'weeks': calendar_data['weeks'],
        'mini_calendar': calendar_data['mini_calendar'],
        'total_items_count': calendar_data['total_items_count'],
        'active_view': active_view,
        'active_cats': active_cats,
        'selected_member': member_id,
        'workspace_members': workspace_members,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'today': today,
    }
    return render(request, 'calendars/calendar_view.html', context)


@workspace_member_required
def agenda_view(request, slug):
    """
    Chronological Agenda timeline stream grouped by date with category filters,
    Today's Summary metric chips, and Upcoming list matching Screen 2.
    """
    workspace = request.workspace
    membership = request.membership

    today = timezone.localdate()

    # Parse target date
    date_str = request.GET.get('date', '').strip()
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = today
    else:
        target_date = today

    # Category filter: all, tasks, bugs, meetings, milestones, events
    cat_filter = request.GET.get('cat', 'all').lower()
    if cat_filter != 'all':
        active_cats = [cat_filter]
    else:
        active_cats = ['events', 'tasks', 'bugs', 'meetings', 'milestones']

    member_id = request.GET.get('member')
    if member_id in ['', 'all', None]:
        member_id = None

    agenda_data = build_agenda_stream(
        workspace=workspace,
        target_date=target_date,
        categories=active_cats,
        member_id=member_id,
        days_ahead=21
    )

    prev_day = target_date - timedelta(days=1)
    next_day = target_date + timedelta(days=1)

    context = {
        'workspace': workspace,
        'membership': membership,
        'target_date': target_date,
        'prev_day': prev_day,
        'next_day': next_day,
        'today': today,
        'cat_filter': cat_filter,
        'date_groups': agenda_data['date_groups'],
        'today_summary': agenda_data['today_summary'],
        'upcoming_items': agenda_data['upcoming_items'],
        'total_count': agenda_data['total_count'],
    }
    return render(request, 'calendars/agenda_view.html', context)


@workspace_member_required
def upcoming_deadlines_view(request, slug):
    """
    Unified Upcoming Deadlines dashboard with filter pills, timeframe filter,
    overdue item tracking, and summary cards matching Screen 5.
    """
    workspace = request.workspace
    membership = request.membership

    cat_filter = request.GET.get('cat', 'all').lower()
    try:
        timeframe_days = int(request.GET.get('days', 30))
    except (ValueError, TypeError):
        timeframe_days = 30

    deadlines_data = build_upcoming_deadlines(
        workspace=workspace,
        timeframe_days=timeframe_days,
        category_filter=cat_filter
    )

    context = {
        'workspace': workspace,
        'membership': membership,
        'cat_filter': cat_filter,
        'timeframe_days': timeframe_days,
        'today_items': deadlines_data['today'],
        'tomorrow_items': deadlines_data['tomorrow'],
        'next_7_items': deadlines_data['next_7_days'],
        'later_items': deadlines_data['later'],
        'overdue_items': deadlines_data['overdue_items'],
        'deadline_summary': deadlines_data['deadline_summary'],
        'total_deadlines': deadlines_data['total_deadlines'],
    }
    return render(request, 'calendars/upcoming_deadlines.html', context)


@workspace_member_required
def event_create_view(request, slug):
    """
    2-Column Create New Event page matching Screen 3:
    Left: Title, type, start/end dates, all day, repeat, location, description
    Right: Connect with Tasks/Bugs/Milestones and Invite People
    """
    workspace = request.workspace
    membership = request.membership

    today = timezone.localdate()
    now = timezone.now()
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    auto_meet_code = generate_unique_meeting_code()

    if request.method == 'POST':
        form = CalendarEventForm(request.POST, workspace=workspace)
        if form.is_valid():
            invitees = form.cleaned_data.get('invitees')
            event = create_calendar_event(
                workspace=workspace,
                user=request.user,
                data=form.cleaned_data,
                invitees=invitees
            )
            messages.success(request, f"Event '{event.title}' scheduled successfully.")
            return redirect('calendars:event_detail', slug=workspace.slug, event_id=event.id)
    else:
        # Check pre-filled date or type from query params
        pre_date_str = request.GET.get('date')
        if pre_date_str:
            try:
                pre_date = datetime.strptime(pre_date_str, '%Y-%m-%d').date()
            except ValueError:
                pre_date = today
        else:
            pre_date = today

        pre_type = request.GET.get('type', CalendarEventType.GENERAL).upper()
        if pre_type not in CalendarEventType.values:
            pre_type = CalendarEventType.GENERAL

        form = CalendarEventForm(
            workspace=workspace,
            initial={
                'start_date': pre_date,
                'start_time': next_hour.time().strftime('%H:%M'),
                'end_date': pre_date,
                'end_time': (next_hour + timedelta(hours=1)).time().strftime('%H:%M'),
                'event_type': pre_type,
                'calendar_category': CalendarCategory.WORKSPACE
            }
        )

    workspace_members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user').order_by('user__first_name', 'user__username')

    context = {
        'workspace': workspace,
        'membership': membership,
        'form': form,
        'workspace_members': workspace_members,
        'today': today,
        'auto_meet_code': auto_meet_code,
    }
    return render(request, 'calendars/event_create.html', context)


@workspace_member_required
def event_detail_view(request, slug, event_id):
    """
    Event Details Page matching Screen 4:
    Hero card, status badges, summary mini-table, tabs (Overview, People, Connected Items, Activity),
    and bottom action buttons.
    """
    workspace = request.workspace
    membership = request.membership

    event = get_object_or_404(
        CalendarEvent.objects.select_related(
            'workspace', 'created_by', 'linked_task', 'linked_bug', 'linked_meeting'
        ).prefetch_related('attendees__user'),
        workspace=workspace,
        id=event_id
    )

    attendees = event.attendees.select_related('user').all()
    can_manage = (event.created_by == request.user or membership.can_manage_content)

    context = {
        'workspace': workspace,
        'membership': membership,
        'event': event,
        'attendees': attendees,
        'attendee_count': attendees.count(),
        'can_manage': can_manage,
    }
    return render(request, 'calendars/event_detail.html', context)


@workspace_member_required
def event_edit_view(request, slug, event_id):
    """
    Edit existing event details with RBAC authorization check.
    """
    workspace = request.workspace
    membership = request.membership

    event = get_object_or_404(CalendarEvent, workspace=workspace, id=event_id)

    # Permission check: creator or workspace manager/admin only
    if event.created_by != request.user and not membership.can_manage_content:
        return HttpResponseForbidden("You do not have permission to edit this event.")

    if request.method == 'POST':
        form = CalendarEventForm(request.POST, instance=event, workspace=workspace)
        if form.is_valid():
            event = form.save(commit=False)
            event.start_at = form.cleaned_data['computed_start_at']
            event.end_at = form.cleaned_data['computed_end_at']
            event.save()

            # Sync attendees
            invitees = form.cleaned_data.get('invitees')
            if invitees is not None:
                current_user_ids = set(invitees.values_list('id', flat=True))
                current_user_ids.add(event.created_by_id)
                # Remove unselected
                CalendarEventAttendee.objects.filter(event=event).exclude(user_id__in=current_user_ids).delete()
                # Add new
                for u in invitees:
                    CalendarEventAttendee.objects.get_or_create(
                        event=event,
                        user=u,
                        defaults={'status': 'INVITED'}
                    )

            messages.success(request, f"Event '{event.title}' updated successfully.")
            return redirect('calendars:event_detail', slug=workspace.slug, event_id=event.id)
    else:
        form = CalendarEventForm(instance=event, workspace=workspace)

    workspace_members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user').order_by('user__first_name', 'user__username')

    if event.linked_meeting:
        auto_meet_code = event.linked_meeting.meeting_code
    elif event.meeting_link and 'meet-' in event.meeting_link:
        import re
        m_code = re.search(r'meet-[a-z0-9]{4}-[a-z0-9]{4}', event.meeting_link)
        auto_meet_code = m_code.group(0) if m_code else generate_unique_meeting_code()
    else:
        auto_meet_code = generate_unique_meeting_code()

    context = {
        'workspace': workspace,
        'membership': membership,
        'event': event,
        'form': form,
        'workspace_members': workspace_members,
        'auto_meet_code': auto_meet_code,
    }
    return render(request, 'calendars/event_edit.html', context)


@workspace_member_required
def event_delete_view(request, slug, event_id):
    """
    Delete event with RBAC authorization check.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    membership = request.membership

    event = get_object_or_404(CalendarEvent, workspace=workspace, id=event_id)

    # Permission check: creator or workspace manager/admin only
    if event.created_by != request.user and not membership.can_manage_content:
        return HttpResponseForbidden("You do not have permission to delete this event.")

    title = event.title
    event.delete()
    messages.success(request, f"Event '{title}' was deleted.")
    return redirect('calendars:calendar_view', slug=workspace.slug)


@workspace_member_required
def calendar_feed_api(request, slug):
    """
    JSON feed endpoint for asynchronous calendar loading or client mini-calendars.
    """
    workspace = request.workspace
    today = timezone.localdate()

    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    data = build_month_calendar_matrix(workspace, year, month)
    # Strip non-serializable objects
    simplified_weeks = []
    for week in data['weeks']:
        simplified_days = []
        for day in week:
            simplified_days.append({
                'date': day['date'].isoformat(),
                'day_number': day['day_number'],
                'is_current_month': day['is_current_month'],
                'is_today': day['is_today'],
                'items_count': len(day['items']),
                'items': [{
                    'id': it['id'],
                    'title': it['title'],
                    'category': it['category'],
                    'color': it['color'],
                    'start_time': it['start_time'],
                    'detail_url': it['detail_url']
                } for it in day['items'][:5]]
            })
        simplified_weeks.append(simplified_days)

    return JsonResponse({
        'year': year,
        'month': month,
        'month_name': data['month_name'],
        'weeks': simplified_weeks,
        'total_items': data['total_items_count']
    })
