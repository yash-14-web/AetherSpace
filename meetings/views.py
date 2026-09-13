import re
import json
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


def _clean_code(meeting_code):
    """Safely extracts a valid meeting code from URL, fragment, or raw input."""
    raw = (meeting_code or '').strip().lower()
    match = re.search(r'meet-[a-z0-9]{4}-[a-z0-9]{4}', raw)
    return match.group(0) if match else raw.split(':')[0].strip()



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


def cleanup_stale_meetings(workspace):
    """
    Auto-close live meetings that have no active participants or haven't received
    a heartbeat ping in over 90 seconds.
    """
    now = timezone.now()
    live_meetings = Meeting.objects.filter(workspace=workspace, status=MeetingStatus.LIVE)
    for m in live_meetings:
        no_active_participants = not m.participants.filter(left_at__isnull=True).exists()
        stale_heartbeat = (now - m.updated_at).total_seconds() > 90
        if no_active_participants or stale_heartbeat:
            m.status = MeetingStatus.ENDED
            m.actual_end = m.updated_at or now
            m.save(update_fields=['status', 'actual_end', 'updated_at'])
            m.participants.filter(left_at__isnull=True).update(left_at=m.actual_end)


@workspace_member_required
def meet_hub_view(request, slug):
    """
    Primary Meet Hub dashboard: live active calls, scheduled conferences,
    metric cards, and quick start/join controls matching Screen 1 reference design.
    """
    workspace = request.workspace
    membership = request.membership

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Auto-close stale or abandoned live meetings
    cleanup_stale_meetings(workspace)

    # 1. Live Meetings in this workspace
    live_meetings = Meeting.objects.filter(
        workspace=workspace,
        status=MeetingStatus.LIVE
    ).select_related('host').prefetch_related('participants__user', 'invites__user')

    # 2. Upcoming & Scheduled Meetings
    upcoming_qs = Meeting.objects.filter(
        workspace=workspace,
        status__in=[MeetingStatus.SCHEDULED, MeetingStatus.LIVE]
    ).select_related('host').prefetch_related('participants__user', 'invites__user').order_by('-status', 'scheduled_start', '-created_at')
    upcoming_meetings = upcoming_qs[:10]

    # 3. Scheduled Meetings for Today
    today_meetings = Meeting.objects.filter(
        workspace=workspace,
        status=MeetingStatus.SCHEDULED,
        scheduled_start__gte=today_start,
        scheduled_start__lt=today_end
    ).select_related('host').order_by('scheduled_start')

    # 4. Recent Completed Meetings
    recent_ended = Meeting.objects.filter(
        workspace=workspace,
        status=MeetingStatus.ENDED
    ).select_related('host').order_by('-actual_end', '-created_at')[:6]

    # Metrics
    metrics = {
        'live_count': live_meetings.count(),
        'today_count': today_meetings.count(),
        'upcoming_count': upcoming_qs.filter(status=MeetingStatus.SCHEDULED).count(),
        'completed_count': Meeting.objects.filter(workspace=workspace, status=MeetingStatus.ENDED).count(),
        'total_meetings': Meeting.objects.filter(workspace=workspace).count(),
    }

    start_form = StartMeetingForm()
    join_form = JoinMeetingForm()
    personal_link = f"meet.aetherspace.dev/{request.user.username}"

    context = {
        'workspace': workspace,
        'membership': membership,
        'live_meetings': live_meetings,
        'upcoming_meetings': upcoming_meetings,
        'upcoming_cards': upcoming_meetings,
        'today_meetings': today_meetings,
        'recent_ended': recent_ended,
        'recent_history': recent_ended,
        'recent_meetings_list': recent_ended,
        'metrics': metrics,
        'stats': metrics,
        'start_form': start_form,
        'join_form': join_form,
        'personal_link': personal_link,
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
        raw_input = request.POST.get('meeting_code', '').strip()
        # If user pasted a URL or link, extract the meeting code
        import re
        extracted = re.search(r'meet-[a-z0-9]{4}-[a-z0-9]{4}', raw_input.lower())
        code_to_check = extracted.group(0) if extracted else raw_input.strip()

        if code_to_check:
            meeting = Meeting.objects.filter(workspace=workspace, meeting_code__iexact=code_to_check).first()
            if meeting:
                if meeting.status == MeetingStatus.CANCELLED:
                    error_message = f"Meeting '{meeting.title}' was cancelled by the host."
                else:
                    return redirect('meetings:meeting_room', slug=workspace.slug, meeting_code=meeting.meeting_code)
            else:
                error_message = f"No meeting found with code '{code_to_check}' in this workspace."
        else:
            error_message = "Please enter a valid meeting code or link."
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

    clean_code = _clean_code(meeting_code)

    meeting = Meeting.objects.select_related('workspace', 'host').prefetch_related('participants__user').filter(
        workspace=workspace,
        meeting_code__iexact=clean_code
    ).first()

    if not meeting:
        messages.error(request, f"Meeting '{clean_code}' was not found in this workspace.")
        return redirect('meetings:meet_hub', slug=workspace.slug)

    # If meeting was cancelled, render cancelled notice
    if meeting.status == MeetingStatus.CANCELLED:
        return render(request, 'meetings/meeting_room_status.html', {
            'workspace': workspace,
            'meeting': meeting,
            'status_reason': 'cancelled',
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
            'status_reason': 'ended',
            'status_heading': 'Meeting Ended',
            'status_message': f"This meeting ended at {meeting.actual_end.strftime('%I:%M %p') if meeting.actual_end else 'an earlier time'}.",
            'can_reopen': is_host
        })

    # Auto-record join session
    record_participant_join(meeting, request.user)

    is_host = (meeting.host == request.user or membership.can_manage_content)
    jitsi_domain = getattr(settings, 'JITSI_DOMAIN', 'meet.jit.si')
    participants = meeting.participants.select_related('user').order_by('joined_at')
    workspace_members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user')

    # Build dynamic active participants list
    import json
    active_participants_qs = meeting.participants.filter(left_at__isnull=True).select_related('user').order_by('joined_at')
    active_participants_list = []
    has_self = False

    user_name = request.user.full_name or request.user.get_full_name() or request.user.username or request.user.email.split('@')[0]
    user_initials = ''.join([part[0].upper() for part in user_name.split()[:2]]) or user_name[:1].upper()
    user_role_label = 'Meeting host' if is_host else ('Manager' if getattr(membership, 'role', '') == 'manager' else 'Contributor')
    user_avatar_url = request.user.avatar if getattr(request.user, 'avatar', None) and not request.user.avatar.startswith('preset:') else ''

    for p in active_participants_qs:
        p_name = p.user.full_name or p.user.get_full_name() or p.user.username or p.user.email.split('@')[0]
        initials = ''.join([part[0].upper() for part in p_name.split()[:2]]) or p_name[:1].upper()
        is_self = (p.user == request.user)
        if is_self:
            has_self = True
        p_is_host = (p.role == ParticipantRole.HOST or p.user == meeting.host)
        p_role_label = 'Meeting host' if p_is_host else 'Contributor'
        p_avatar = p.user.avatar if getattr(p.user, 'avatar', None) and not p.user.avatar.startswith('preset:') else ''
        active_participants_list.append({
            'id': str(p.user.id),
            'name': p_name,
            'initials': initials,
            'email': p.user.email,
            'avatar': p_avatar,
            'role': p_role_label,
            'is_self': is_self,
        })

    if not has_self:
        active_participants_list.insert(0, {
            'id': str(request.user.id),
            'name': user_name,
            'initials': user_initials,
            'email': request.user.email,
            'avatar': user_avatar_url,
            'role': user_role_label,
            'is_self': True,
        })

    participants_json = json.dumps(active_participants_list)

    # Format meeting code like abc-defg-hij if matching 9+ alpha characters
    code_raw = meeting.meeting_code
    if len(code_raw) >= 9 and '-' not in code_raw:
        meeting_code_formatted = f"{code_raw[:3]}-{code_raw[3:7]}-{code_raw[7:]}".lower()
    else:
        meeting_code_formatted = code_raw.lower()

    context = {
        'workspace': workspace,
        'membership': membership,
        'meeting': meeting,
        'is_host': is_host,
        'user_role_label': user_role_label,
        'jitsi_domain': jitsi_domain,
        'jitsi_room_name': meeting.jitsi_room_name,
        'user_display_name': user_name,
        'user_initials': user_initials,
        'user_email': request.user.email,
        'user_avatar': user_avatar_url,
        'meeting_code_formatted': meeting_code_formatted,
        'participants': participants,
        'participants_json': participants_json,
        'workspace_members': workspace_members,
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

    workspace_members = workspace.memberships.select_related('user').filter(
        status='ACTIVE'
    ).order_by('user__first_name', 'user__username')

    context = {
        'workspace': workspace,
        'membership': membership,
        'form': form,
        'workspace_members': workspace_members,
    }
    return render(request, 'meetings/meeting_schedule.html', context)


@workspace_member_required
def meeting_detail_view(request, slug, meeting_code):
    """
    Comprehensive meeting information: host, scheduled time, participant roster,
    duration, and meeting actions.
    """
    workspace = request.workspace
    cleanup_stale_meetings(workspace)

    clean_code = _clean_code(meeting_code)
    meeting = Meeting.objects.select_related('workspace', 'host').prefetch_related('participants__user', 'invites__user').filter(
        workspace=workspace,
        meeting_code__iexact=clean_code
    ).first()

    if not meeting:
        messages.error(request, f"Meeting '{clean_code}' was not found in this workspace.")
        return redirect('meetings:meet_hub', slug=workspace.slug)

    participants = meeting.participants.select_related('user').order_by('joined_at')
    invites = meeting.invites.select_related('user').all()
    is_host = (meeting.host == request.user or request.membership.can_manage_content)

    context = {
        'workspace': workspace,
        'membership': request.membership,
        'meeting': meeting,
        'participants': participants,
        'total_participant_count': participants.count(),
        'invites': invites,
        'is_host': is_host,
        'can_manage': is_host,
    }
    return render(request, 'meetings/meeting_detail.html', context)


@workspace_member_required
def meeting_edit_view(request, slug, meeting_code):
    """
    Edit meeting details (Host or Admin/Manager only).
    """
    workspace = request.workspace
    clean_code = _clean_code(meeting_code)
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
    clean_code = _clean_code(meeting_code)
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
    return render(request, 'meetings/meeting_cancel.html', context)


@workspace_member_required
def meeting_history_view(request, slug):
    """
    Chronological meeting history view with search, meeting type filter, and pagination.
    """
    workspace = request.workspace
    membership = request.membership

    # Auto-close stale or abandoned live meetings first
    cleanup_stale_meetings(workspace)

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

    status_counts = {
        'all': Meeting.objects.filter(workspace=workspace).count(),
        'live': Meeting.objects.filter(workspace=workspace, status=MeetingStatus.LIVE).count(),
        'scheduled': Meeting.objects.filter(workspace=workspace, status=MeetingStatus.SCHEDULED).count(),
        'completed': Meeting.objects.filter(workspace=workspace, status=MeetingStatus.ENDED).count(),
        'cancelled': Meeting.objects.filter(workspace=workspace, status=MeetingStatus.CANCELLED).count(),
    }

    all_meetings = Meeting.objects.filter(workspace=workspace)
    total_count = all_meetings.count()
    completed_meetings = all_meetings.filter(status=MeetingStatus.ENDED)
    total_minutes = sum([m.duration_minutes or 30 for m in completed_meetings])
    total_hours = round(total_minutes / 60.0, 1) if total_minutes else 0.0
    avg_minutes = round(total_minutes / completed_meetings.count()) if completed_meetings.exists() else 0

    stats_summary = {
        'total_meetings': total_count,
        'total_hours': total_hours,
        'avg_duration': avg_minutes,
        'completed_count': completed_meetings.count(),
    }

    context = {
        'workspace': workspace,
        'membership': membership,
        'meetings': page_obj,
        'page_obj': page_obj,
        'total_meetings_count': total_count,
        'status_counts': status_counts,
        'stats_summary': stats_summary,
        'current_q': q,
        'current_type': m_type,
        'current_status': status_filter,
        'meeting_types': MeetingType.choices,
        'meeting_statuses': MeetingStatus.choices,
        'MeetingType': MeetingType,
        'MeetingStatus': MeetingStatus,
    }
    return render(request, 'meetings/meeting_history.html', context)


@workspace_member_required
def meeting_ping_api(request, slug, meeting_code):
    """
    Heartbeat and presence ping API from meeting room.
    Records active session or user departure, updates hand raise state,
    and checks if the participant has been ejected.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    clean_code = _clean_code(meeting_code)
    meeting = Meeting.objects.filter(workspace=workspace, meeting_code__iexact=clean_code).first()
    if not meeting:
        return JsonResponse({'success': False, 'error': 'Meeting not found', 'status': 'ended'})

    # Check if this user was removed by the host
    current_participant = MeetingParticipant.objects.filter(meeting=meeting, user=request.user).order_by('-joined_at').first()
    if current_participant and current_participant.is_removed:
        return JsonResponse({
            'success': False,
            'status': 'removed',
            'error': 'You have been removed from this meeting by the host.',
            'redirect_url': reverse('meetings:meet_hub', kwargs={'slug': workspace.slug})
        })

    import json
    action = 'ping'
    hand_raised = None
    if request.content_type == 'application/json' and request.body:
        try:
            payload = json.loads(request.body)
            action = payload.get('action', 'ping')
            if 'hand_raised' in payload:
                hand_raised = bool(payload['hand_raised'])
        except Exception:
            action = 'ping'
    else:
        action = request.POST.get('action') or 'ping'
        if 'hand_raised' in request.POST:
            hand_raised = request.POST.get('hand_raised') in ['true', '1', True]

    if action == 'leave':
        record_participant_leave(meeting, request.user)
        # If host left or no participants remain, mark ended
        if meeting.host == request.user or not meeting.participants.filter(left_at__isnull=True).exists():
            end_meeting(meeting, request.user)
    else:
        p = record_participant_join(meeting, request.user)
        # Handle hand raise actions
        if action == 'raise_hand':
            p.is_hand_raised = True
            p.save(update_fields=['is_hand_raised'])
        elif action == 'lower_hand':
            p.is_hand_raised = False
            p.save(update_fields=['is_hand_raised'])
        elif hand_raised is not None:
            p.is_hand_raised = hand_raised
            p.save(update_fields=['is_hand_raised'])

        # Touch meeting updated_at so heartbeat freshness is preserved
        meeting.save(update_fields=['updated_at'])

    active_participants = []
    for p in meeting.participants.filter(left_at__isnull=True, is_removed=False).select_related('user').order_by('joined_at'):
        p_name = p.user.full_name or p.user.get_full_name() or p.user.username or p.user.email.split('@')[0]
        initials = ''.join([part[0].upper() for part in p_name.split()[:2]]) or p_name[:1].upper()
        p_is_host = (p.role == ParticipantRole.HOST or p.user == meeting.host)
        p_role_label = 'Meeting host' if p_is_host else 'Contributor'
        p_avatar = p.user.avatar if getattr(p.user, 'avatar', None) and not p.user.avatar.startswith('preset:') else ''
        active_participants.append({
            'id': str(p.user.id),
            'name': p_name,
            'initials': initials,
            'email': p.user.email,
            'avatar': p_avatar,
            'role': p_role_label,
            'is_self': (p.user == request.user),
            'is_hand_raised': p.is_hand_raised,
        })

    return JsonResponse({
        'success': True,
        'status': meeting.status,
        'active_count': len(active_participants),
        'participants': active_participants,
        'duration_display': meeting.duration_display
    })


@workspace_member_required
def meeting_remove_participant_api(request, slug, meeting_code, user_id=None):
    """
    Host action to eject/remove an attendee from the active meeting.
    Accepts user_id from URL parameter, form POST, or JSON body.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    clean_code = _clean_code(meeting_code)
    meeting = Meeting.objects.filter(workspace=workspace, meeting_code__iexact=clean_code).first()
    if not meeting:
        return JsonResponse({'success': False, 'status': 'error', 'error': 'Meeting not found'}, status=404)

    is_host = (meeting.host == request.user or request.membership.can_manage_content)
    if not is_host:
        return JsonResponse({'success': False, 'status': 'error', 'error': 'Only the meeting host can remove participants.'}, status=403)

    target_user_id = user_id or request.POST.get('user_id')
    if not target_user_id:
        try:
            body = json.loads(request.body.decode('utf-8'))
            target_user_id = body.get('user_id')
        except Exception:
            pass

    if not target_user_id:
        return JsonResponse({'success': False, 'status': 'error', 'error': 'Missing user_id parameter.'}, status=400)

    target_participant = MeetingParticipant.objects.filter(
        meeting=meeting,
        user_id=target_user_id,
        left_at__isnull=True
    ).first()

    if target_participant:
        now = timezone.now()
        target_participant.is_removed = True
        target_participant.removed_at = now
        target_participant.left_at = now
        target_participant.is_hand_raised = False
        target_participant.save(update_fields=['is_removed', 'removed_at', 'left_at', 'is_hand_raised'])

    return JsonResponse({'success': True, 'status': 'ok', 'message': 'Participant removed from meeting.'})


@workspace_member_required
def meeting_end_api(request, slug, meeting_code):
    """
    Host action to end meeting for all, or attendee leave action.
    Immediately closes sessions and transitions state to ENDED.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    clean_code = _clean_code(meeting_code)
    meeting = Meeting.objects.filter(workspace=workspace, meeting_code__iexact=clean_code).first()
    if not meeting:
        redirect_url = reverse('meetings:meet_hub', kwargs={'slug': workspace.slug})
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'success': True, 'redirect_url': redirect_url, 'message': 'Meeting ended.'})
        return redirect(redirect_url)

    is_host_or_manager = (meeting.host == request.user or request.membership.can_manage_content)

    if is_host_or_manager:
        end_meeting(meeting, request.user)
        messages.success(request, f"Meeting '{meeting.title}' has ended.")
    else:
        record_participant_leave(meeting, request.user)
        # If no more participants remain, auto-end the meeting
        if not meeting.participants.filter(left_at__isnull=True).exists():
            end_meeting(meeting, request.user)
        messages.info(request, "You have left the meeting.")

    redirect_url = reverse('meetings:meet_hub', kwargs={'slug': workspace.slug})

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({
            'success': True,
            'redirect_url': redirect_url,
            'message': 'Meeting ended successfully.'
        })

    return redirect(redirect_url)


