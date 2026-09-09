from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils import timezone
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q

from workspaces.permissions import workspace_member_required
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus
from chat.models import Channel, DirectMessageConversation

from .models import Meeting, MeetingParticipant, MeetingInvite, MeetingType, MeetingStatus, ParticipantRole
from .forms import StartMeetingForm, ScheduleMeetingForm, JoinMeetingForm
from .services import (
    create_instant_meeting, create_chat_call, schedule_meeting,
    start_meeting, end_meeting, cancel_meeting,
    record_participant_join, record_participant_leave
)


@login_required
def meet_router(request):
    """
    Global entry point: redirects the authenticated user to their active workspace's Meet Hub.
    """
    active_slug = request.session.get('active_workspace_slug')
    if active_slug:
        ws = Workspace.objects.filter(
            slug=active_slug,
            memberships__user=request.user,
            memberships__status=MembershipStatus.ACTIVE
        ).first()
        if ws:
            return redirect('meetings:meet_hub', slug=ws.slug)

    first_membership = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE
    ).select_related('workspace').first()

    if first_membership:
        return redirect('meetings:meet_hub', slug=first_membership.workspace.slug)

    messages.info(request, "Please select or create a workspace to access Meet Hub.")
    return redirect('workspaces:create')


@workspace_member_required
def meet_hub_view(request, slug):
    """
    Primary Meet Hub dashboard: live active calls, scheduled conferences,
    metric cards, and quick start/join controls.
    """
    workspace = request.workspace
    membership = request.membership

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # 1. Live Meetings in this workspace
    live_meetings = Meeting.objects.filter(
        workspace=workspace,
        status=MeetingStatus.LIVE
    ).select_related('host').prefetch_related('participants__user')

    # 2. Scheduled Meetings for Today
    today_meetings = Meeting.objects.filter(
        workspace=workspace,
        status=MeetingStatus.SCHEDULED,
        scheduled_start__gte=today_start,
        scheduled_start__lt=today_end
    ).select_related('host').order_by('scheduled_start')

    # 3. Upcoming Meetings (Next 7 days)
    upcoming_meetings = Meeting.objects.filter(
        workspace=workspace,
        status=MeetingStatus.SCHEDULED,
        scheduled_start__gte=now,
        scheduled_start__lte=now + timedelta(days=7)
    ).select_related('host').order_by('scheduled_start')

    # 4. Recent Past Meetings
    recent_history = Meeting.objects.filter(
        workspace=workspace,
        status__in=[MeetingStatus.ENDED, MeetingStatus.LIVE]
    ).select_related('host').order_by('-created_at')[:4]

    # Metrics
    metrics = {
        'live_count': live_meetings.count(),
        'today_count': today_meetings.count(),
        'upcoming_count': upcoming_meetings.count(),
        'upcoming_week_count': upcoming_meetings.count(),
        'completed_count': Meeting.objects.filter(workspace=workspace, status=MeetingStatus.ENDED).count(),
        'total_meetings': Meeting.objects.filter(workspace=workspace).count(),
    }

    start_form = StartMeetingForm()
    join_form = JoinMeetingForm()

    context = {
        'workspace': workspace,
        'membership': membership,
        'live_meetings': live_meetings,
        'today_meetings': today_meetings,
        'upcoming_meetings': upcoming_meetings,
        'recent_history': recent_history,
        'recent_ended': recent_history,
        'metrics': metrics,
        'stats': metrics,
        'start_form': start_form,
        'join_form': join_form,
        'MeetingType': MeetingType,
    }
    return render(request, 'meetings/meet_hub.html', context)


@workspace_member_required
def meeting_start_view(request, slug):
    """
    Instant meeting launcher view.
    Creates an immediate LIVE meeting and redirects user directly to the room.
    """
    workspace = request.workspace

    if request.method == 'POST':
        form = StartMeetingForm(request.POST)
        if form.is_valid():
            title = form.cleaned_data['title']
            m_type = form.cleaned_data.get('meeting_type') or MeetingType.INSTANT
            is_audio_only = (request.POST.get('call_mode') == 'AUDIO') or form.cleaned_data.get('is_audio_only', False)

            meeting = create_instant_meeting(
                workspace=workspace,
                host=request.user,
                title=title,
                meeting_type=m_type,
                is_audio_only=is_audio_only
            )
            return redirect('meetings:meeting_room', slug=workspace.slug, meeting_code=meeting.meeting_code)
    else:
        initial_title = f"{request.user.first_name or request.user.email.split('@')[0]}'s Quick Meeting"
        form = StartMeetingForm(initial={'title': initial_title})

    context = {
        'workspace': workspace,
        'membership': request.membership,
        'form': form,
    }
    return render(request, 'meetings/meeting_start.html', context)


@workspace_member_required
def meeting_chat_call_view(request, slug, target_type=None, target_id=None, call_mode=None):
    """
    Endpoint for Google Chat style In-Chat Audio / Video Calls.
    Initiates an instant call bound to a Channel or Direct Message.
    Supports invocation via URL routes or POST body.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    mode = (call_mode or request.POST.get('call_type', 'video')).lower()
    is_audio_only = (mode == 'audio')

    channel_id = request.POST.get('channel_id')
    conversation_id = request.POST.get('conversation_id')

    if target_type == 'channel' and target_id:
        channel_id = target_id
    elif target_type == 'dm' and target_id:
        conversation_id = target_id

    channel = None
    conversation = None

    if channel_id:
        channel = get_object_or_404(Channel, id=channel_id, workspace=workspace)
        if not channel.has_member(request.user):
            return HttpResponseForbidden("You do not have access to this channel.")
    elif conversation_id:
        try:
            conversation = DirectMessageConversation.objects.get(id=conversation_id, workspace=workspace)
            if not conversation.has_participant(request.user):
                return HttpResponseForbidden("You do not have access to this conversation.")
        except (DirectMessageConversation.DoesNotExist, ValueError):
            # Might be other_user ID passed from chat header
            from django.contrib.auth import get_user_model
            other_user = get_object_or_404(get_user_model(), id=conversation_id)
            conversation = DirectMessageConversation.objects.filter(
                workspace=workspace
            ).filter(
                (Q(participant1=request.user) & Q(participant2=other_user)) |
                (Q(participant2=request.user) & Q(participant1=other_user))
            ).first()
            if not conversation:
                conversation = DirectMessageConversation.objects.create(
                    workspace=workspace,
                    participant1=request.user,
                    participant2=other_user
                )

    meeting = create_chat_call(
        workspace=workspace,
        host=request.user,
        channel=channel,
        conversation=conversation,
        is_audio_only=is_audio_only
    )

    return redirect('meetings:meeting_room', slug=workspace.slug, meeting_code=meeting.meeting_code)


@workspace_member_required
def meeting_join_view(request, slug):
    """
    Join meeting by human-facing meeting code (e.g. meet-k7xp-2m9q).
    """
    workspace = request.workspace
    error_message = None

    if request.method == 'POST':
        form = JoinMeetingForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['meeting_code']
            meeting = Meeting.objects.filter(workspace=workspace, meeting_code__iexact=code).first()
            if meeting:
                if meeting.status == MeetingStatus.CANCELLED:
                    error_message = f"Meeting '{meeting.title}' was cancelled by the host."
                else:
                    return redirect('meetings:meeting_room', slug=workspace.slug, meeting_code=meeting.meeting_code)
            else:
                error_message = f"No meeting found with code '{code}' in this workspace."
    else:
        raw_code = request.GET.get('code', '').strip().lower()
        if raw_code:
            form = JoinMeetingForm(initial={'meeting_code': raw_code})
            meeting = Meeting.objects.filter(workspace=workspace, meeting_code__iexact=raw_code).first()
            if meeting and meeting.status != MeetingStatus.CANCELLED:
                return redirect('meetings:meeting_room', slug=workspace.slug, meeting_code=meeting.meeting_code)
            elif meeting and meeting.status == MeetingStatus.CANCELLED:
                error_message = f"Meeting '{meeting.title}' was cancelled."
            else:
                error_message = f"No meeting found with code '{raw_code}'."
        else:
            form = JoinMeetingForm()

    context = {
        'workspace': workspace,
        'membership': request.membership,
        'form': form,
        'error_message': error_message,
        'recent_meetings': Meeting.objects.filter(workspace=workspace, status__in=[MeetingStatus.LIVE, MeetingStatus.SCHEDULED]).order_by('-created_at')[:3]
    }
    return render(request, 'meetings/meeting_join.html', context)


@workspace_member_required
def meeting_room_view(request, slug, meeting_code):
    """
    Active Video/Audio Meeting Room with Jitsi Meet External API integration
    and local WebRTC room controls.
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = meeting_code.strip().lower()
    meeting = get_object_or_404(
        Meeting.objects.select_related('workspace', 'host').prefetch_related('participants__user'),
        workspace=workspace,
        meeting_code__iexact=clean_code
    )

    # If meeting was cancelled, render cancelled notice
    if meeting.status == MeetingStatus.CANCELLED:
        return render(request, 'meetings/meeting_room_status.html', {
            'workspace': workspace,
            'meeting': meeting,
            'status_heading': 'Meeting Cancelled',
            'status_message': 'This meeting was cancelled by the host and cannot be joined.',
            'can_reopen': False
        })

    # If meeting was ended, check if user can re-open or view details
    if meeting.status == MeetingStatus.ENDED:
        is_host = (meeting.host == request.user or membership.can_manage_content)
        return render(request, 'meetings/meeting_room_status.html', {
            'workspace': workspace,
            'meeting': meeting,
            'status_heading': 'Meeting Ended',
            'status_message': f"This meeting ended at {meeting.actual_end.strftime('%I:%M %p') if meeting.actual_end else 'an earlier time'}.",
            'can_reopen': is_host
        })

    # Auto-record join session
    record_participant_join(meeting, request.user)

    is_host = (meeting.host == request.user or membership.can_manage_content)
    jitsi_domain = getattr(settings, 'JITSI_DOMAIN', 'meet.jit.si')

    context = {
        'workspace': workspace,
        'membership': membership,
        'meeting': meeting,
        'is_host': is_host,
        'jitsi_domain': jitsi_domain,
        'jitsi_room_name': meeting.jitsi_room_name,
        'user_display_name': request.user.full_name or request.user.email.split('@')[0],
        'user_email': request.user.email,
        'user_avatar': request.user.avatar if hasattr(request.user, 'avatar') and request.user.avatar else '',
        'shareable_url': request.build_absolute_uri(reverse('meetings:meeting_room', kwargs={'slug': workspace.slug, 'meeting_code': meeting.meeting_code})),
    }
    return render(request, 'meetings/meeting_room.html', context)


@workspace_member_required
def meeting_schedule_view(request, slug):
    """
    Schedule a future meeting with date/time picker, agenda, and invitees.
    """
    workspace = request.workspace
    membership = request.membership

    if request.method == 'POST':
        form = ScheduleMeetingForm(request.POST, workspace=workspace)
        if form.is_valid():
            scheduled_start = form.cleaned_data['scheduled_start']
            duration = int(form.cleaned_data['duration_minutes'])
            scheduled_end = scheduled_start + timedelta(minutes=duration)

            meeting = schedule_meeting(
                workspace=workspace,
                host=request.user,
                title=form.cleaned_data['title'],
                scheduled_start=scheduled_start,
                duration_minutes=duration,
                scheduled_end=scheduled_end,
                meeting_type=form.cleaned_data['meeting_type'],
                description=form.cleaned_data.get('description', ''),
                invitees=form.cleaned_data.get('invitees'),
                is_audio_only=form.cleaned_data.get('is_audio_only', False)
            )
            messages.success(request, f"Meeting '{meeting.title}' scheduled for {scheduled_start.strftime('%b %d, %Y at %I:%M %p')}.")
            return redirect('meetings:meeting_detail', slug=workspace.slug, meeting_code=meeting.meeting_code)
    else:
        # Default to next hour
        now = timezone.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        form = ScheduleMeetingForm(
            workspace=workspace,
            initial={
                'scheduled_date': next_hour.date(),
                'scheduled_time': next_hour.time().strftime('%H:%M'),
                'duration_minutes': 30,
                'meeting_type': MeetingType.GENERAL
            }
        )

    context = {
        'workspace': workspace,
        'membership': membership,
        'form': form,
    }
    return render(request, 'meetings/meeting_schedule.html', context)


@workspace_member_required
def meeting_detail_view(request, slug, meeting_code):
    """
    Comprehensive meeting information: host, scheduled time, participant roster,
    duration, and meeting actions.
    """
    workspace = request.workspace
    clean_code = meeting_code.strip().lower()
    meeting = get_object_or_404(
        Meeting.objects.select_related('workspace', 'host').prefetch_related('participants__user', 'invites__user'),
        workspace=workspace,
        meeting_code__iexact=clean_code
    )

    participants = meeting.participants.select_related('user').order_by('joined_at')
    invites = meeting.invites.select_related('user').all()
    is_host = (meeting.host == request.user or request.membership.can_manage_content)

    context = {
        'workspace': workspace,
        'membership': request.membership,
        'meeting': meeting,
        'participants': participants,
        'invites': invites,
        'is_host': is_host,
    }
    return render(request, 'meetings/meeting_detail.html', context)


@workspace_member_required
def meeting_edit_view(request, slug, meeting_code):
    """
    Edit meeting details (Host or Admin/Manager only).
    """
    workspace = request.workspace
    clean_code = meeting_code.strip().lower()
    meeting = get_object_or_404(Meeting, workspace=workspace, meeting_code__iexact=clean_code)

    if meeting.host != request.user and not request.membership.can_manage_content:
        return HttpResponseForbidden("You do not have permission to edit this meeting.")

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        meeting_type = request.POST.get('meeting_type', meeting.meeting_type)

        if title:
            meeting.title = title
            meeting.description = description
            meeting.meeting_type = meeting_type
            meeting.save(update_fields=['title', 'description', 'meeting_type', 'updated_at'])
            messages.success(request, "Meeting updated successfully.")
            return redirect('meetings:meeting_detail', slug=workspace.slug, meeting_code=meeting.meeting_code)
        else:
            messages.error(request, "Meeting title cannot be empty.")

    context = {
        'workspace': workspace,
        'membership': request.membership,
        'meeting': meeting,
        'MeetingType': MeetingType,
    }
    return render(request, 'meetings/meeting_edit.html', context)


@workspace_member_required
def meeting_cancel_view(request, slug, meeting_code):
    """
    Cancel a scheduled meeting (Host or Admin/Manager only).
    """
    workspace = request.workspace
    clean_code = meeting_code.strip().lower()
    meeting = get_object_or_404(Meeting, workspace=workspace, meeting_code__iexact=clean_code)

    if meeting.host != request.user and not request.membership.can_manage_content:
        return HttpResponseForbidden("You do not have permission to cancel this meeting.")

    if request.method == 'POST':
        cancel_meeting(meeting, request.user)
        messages.success(request, f"Meeting '{meeting.title}' was cancelled.")
        return redirect('meetings:meet_hub', slug=workspace.slug)

    context = {
        'workspace': workspace,
        'membership': request.membership,
        'meeting': meeting,
    }
    return render(request, 'meetings/meeting_confirm_cancel.html', context)


@workspace_member_required
def meeting_history_view(request, slug):
    """
    Chronological meeting history view with search, meeting type filter, and pagination.
    """
    workspace = request.workspace
    membership = request.membership

    meetings_qs = Meeting.objects.filter(workspace=workspace).select_related('host').prefetch_related('participants__user')

    q = request.GET.get('q', '').strip()
    if q:
        meetings_qs = meetings_qs.filter(
            Q(title__icontains=q) |
            Q(meeting_code__icontains=q) |
            Q(description__icontains=q)
        )

    m_type = request.GET.get('type', '').strip()
    if m_type and m_type != 'all':
        meetings_qs = meetings_qs.filter(meeting_type=m_type)

    status_filter = request.GET.get('status', '').strip()
    if status_filter and status_filter != 'all':
        meetings_qs = meetings_qs.filter(status=status_filter)

    # Order newest first
    meetings_qs = meetings_qs.order_by('-created_at')

    paginator = Paginator(meetings_qs, 12)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    context = {
        'workspace': workspace,
        'membership': membership,
        'page_obj': page_obj,
        'current_q': q,
        'current_type': m_type,
        'current_status': status_filter,
        'MeetingType': MeetingType,
        'MeetingStatus': MeetingStatus,
    }
    return render(request, 'meetings/meeting_history.html', context)


@workspace_member_required
def meeting_ping_api(request, slug, meeting_code):
    """
    Heartbeat and presence ping API from meeting room.
    Records active session or user departure.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    clean_code = meeting_code.strip().lower()
    meeting = get_object_or_404(Meeting, workspace=workspace, meeting_code__iexact=clean_code)

    action = request.POST.get('action', 'ping')
    if action == 'leave':
        record_participant_leave(meeting, request.user)
    else:
        record_participant_join(meeting, request.user)

    return JsonResponse({
        'success': True,
        'status': meeting.status,
        'active_count': meeting.active_participants_count,
        'duration_display': meeting.duration_display
    })


@workspace_member_required
def meeting_end_api(request, slug, meeting_code):
    """
    Host action to end meeting for all participants.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    clean_code = meeting_code.strip().lower()
    meeting = get_object_or_404(Meeting, workspace=workspace, meeting_code__iexact=clean_code)

    if meeting.host != request.user and not request.membership.can_manage_content:
        return HttpResponseForbidden("Only the host or manager can end the meeting.")

    end_meeting(meeting, request.user)
    return JsonResponse({
        'success': True,
        'message': 'Meeting ended for all participants.'
    })
