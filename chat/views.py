import json
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db.models import Q, Max, Count
from django.utils import timezone
from django.contrib.auth import get_user_model

from django.core.exceptions import PermissionDenied
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole
from workspaces.permissions import workspace_member_required
from .models import (
    Channel, ChannelMembership, ChannelRole, PostingPermission,
    DirectMessageConversation, Message, MessageAttachment, MessageReaction
)
from .forms import ChannelForm, MessageForm
from .services import (
    ensure_default_channels, get_or_create_dm_conversation,
    post_channel_message, post_direct_message,
    toggle_pin_message, toggle_reaction, mark_channel_as_read
)

User = get_user_model()


def get_chat_sidebar_context(workspace, user):
    """
    Common sidebar context for all chat views: channels list, DM threads, active team members.
    """
    ensure_default_channels(workspace, creator=user)

    # User's accessible channels
    membership = workspace.get_user_membership(user)
    is_privileged = membership and (membership.is_admin or membership.is_manager)

    if is_privileged:
        channels = workspace.channels.all().order_by('name')
    else:
        channels = workspace.channels.filter(
            Q(is_private=False) | Q(memberships__user=user)
        ).distinct().order_by('name')

    # DM Conversations involving user
    dm_conversations = DirectMessageConversation.objects.filter(
        workspace=workspace
    ).filter(
        Q(participant1=user) | Q(participant2=user)
    ).select_related('participant1', 'participant2').prefetch_related('messages').order_by('-updated_at')

    # Process DM items with other participant
    formatted_dms = []
    for dm in dm_conversations:
        other_user = dm.get_other_participant(user)
        last_msg = dm.messages.order_by('-created_at').first()
        formatted_dms.append({
            'conversation': dm,
            'other_user': other_user,
            'last_message': last_msg,
        })

    # Workspace team members for New DM modal
    active_members = workspace.memberships.filter(
        status=MembershipStatus.ACTIVE
    ).exclude(user=user).select_related('user')

    # All registered database users (excluding current user) for direct message discovery
    workspace_member_ids = set(active_members.values_list('user_id', flat=True))
    all_db_users = User.objects.exclude(id=user.id).order_by('full_name', 'email')[:30]
    formatted_db_users = []
    for u in all_db_users:
        formatted_db_users.append({
            'id': str(u.id),
            'name': u.full_name or u.email.split('@')[0],
            'email': u.email,
            'initial': (u.first_name[:1] if u.first_name else u.email[:1]).upper(),
            'is_member': u.id in workspace_member_ids,
            'role_display': 'Workspace Member' if u.id in workspace_member_ids else 'Direct Chat',
            'dm_url': f"/chat/w/{workspace.slug}/dm/{u.id}/"
        })

    return {
        'channels': channels,
        'formatted_dms': formatted_dms,
        'active_members': active_members,
        'formatted_db_users': formatted_db_users,
    }


@login_required
def chat_router(request):
    """
    Route /chat/ to active workspace's chat home or general channel.
    """
    workspace = getattr(request, 'workspace', None)
    if not workspace:
        first_membership = request.user.workspace_memberships.filter(status=MembershipStatus.ACTIVE).first()
        if first_membership:
            workspace = first_membership.workspace
        else:
            return redirect('workspaces:dashboard_router')

    return redirect('chat:chat_home', slug=workspace.slug)


@workspace_member_required
def chat_home_view(request, slug):
    """
    Chat Home Dashboard matching Panel 1 of mockup:
    - Welcome banner
    - 4 Metric cards (Total Channels, Total Members, Unread Messages, Mentions)
    - Recent Conversations table
    - Mentions card
    - Quick Actions (Start DM, Create Channel, Shared Files)
    """
    workspace = request.workspace
    user = request.user
    sidebar_ctx = get_chat_sidebar_context(workspace, user)

    # 4 Metric Cards
    total_channels = workspace.channels.count()
    total_members = workspace.memberships.filter(status=MembershipStatus.ACTIVE).count()
    unread_messages_count = 0  # Simplified clean count
    mentions_count = Message.objects.filter(
        workspace=workspace,
        content__icontains=f"@{user.first_name}" if user.first_name else f"@{user.email}"
    ).count()

    # Recent Conversations (active channels + DMs with messages)
    recent_channel_messages = Message.objects.filter(
        workspace=workspace,
        channel__isnull=False,
        is_deleted=False
    ).select_related('channel', 'sender').order_by('-created_at')[:8]

    # Recent Mentions
    recent_mentions = Message.objects.filter(
        workspace=workspace,
        content__icontains="@"
    ).select_related('sender', 'channel').order_by('-created_at')[:5]

    context = {
        'title': f"{workspace.name} — Chat Home — AetherSpace",
        'workspace': workspace,
        'membership': request.membership,
        'total_channels': total_channels,
        'total_members': total_members,
        'unread_messages_count': unread_messages_count,
        'mentions_count': mentions_count,
        'recent_channel_messages': recent_channel_messages,
        'recent_mentions': recent_mentions,
        **sidebar_ctx,
    }
    return render(request, 'chat/chat_home.html', context)


@workspace_member_required
def channel_view(request, slug, channel_slug):
    """
    Channel View matching Panel 2 of mockup:
    - Channel topic and presence header
    - Live WebSocket + HTTP message stream with reactions & attachments
    - Message input box
    - Collapsible 'About Channel' right drawer
    """
    workspace = request.workspace
    user = request.user
    sidebar_ctx = get_chat_sidebar_context(workspace, user)

    channel = get_object_or_404(Channel, workspace=workspace, slug=channel_slug)
    if not channel.has_member(user):
        return HttpResponseForbidden("You do not have permission to view this channel.")

    # Mark channel read for this user
    mark_channel_as_read(channel, user)

    # Handle standard POST (WebSocket fallback & file uploads)
    if request.method == 'POST':
        content = request.POST.get('content', '')
        files = request.FILES.getlist('files')
        try:
            post_channel_message(channel, user, content=content, files=files)
            return redirect('chat:channel_view', slug=slug, channel_slug=channel_slug)
        except Exception as e:
            messages.error(request, str(e))

    # Fetch channel messages with attachments and reactions
    messages_qs = channel.messages.filter(is_deleted=False).select_related(
        'sender', 'pinned_by'
    ).prefetch_related(
        'attachments', 'reactions', 'reactions__user'
    ).order_by('created_at')

    context = {
        'title': f"#{channel.name} — {workspace.name} — AetherSpace",
        'workspace': workspace,
        'membership': request.membership,
        'channel': channel,
        'chat_messages': messages_qs,
        'can_post': channel.can_post(user),
        **sidebar_ctx,
    }
    return render(request, 'chat/channel_view.html', context)


@login_required
def direct_message_view(request, slug, user_id):
    """
    Direct Message View matching Panel 3 of mockup:
    - 1-on-1 private messaging stream
    - Other participant status & header actions
    - Live WebSocket + HTTP message posting
    - Does NOT auto-enroll external participants into the workspace membership
    """
    workspace = get_object_or_404(Workspace, slug=slug)
    current_user = request.user
    other_user = get_object_or_404(User, id=user_id)

    if other_user.id == current_user.id:
        messages.info(request, "You cannot start a direct message conversation with yourself.")
        return redirect('chat:chat_home', slug=slug)

    # Permission check: current_user must either be a workspace member
    # OR an existing participant of a DM with other_user in this workspace
    membership = workspace.get_user_membership(current_user)
    if not membership:
        has_dm = DirectMessageConversation.objects.filter(
            workspace=workspace
        ).filter(
            (Q(participant1=current_user) & Q(participant2=other_user)) |
            (Q(participant1=other_user) & Q(participant2=current_user))
        ).exists()
        if not has_dm:
            raise PermissionDenied(f"You do not have access to the '{workspace.name}' workspace.")

    sidebar_ctx = get_chat_sidebar_context(workspace, current_user)
    conversation = get_or_create_dm_conversation(workspace, current_user, other_user)

    # Handle standard POST (WebSocket fallback & file uploads)
    if request.method == 'POST':
        content = request.POST.get('content', '')
        files = request.FILES.getlist('files')
        try:
            post_direct_message(conversation, current_user, content=content, files=files)
            return redirect('chat:direct_message', slug=slug, user_id=user_id)
        except Exception as e:
            messages.error(request, str(e))

    messages_qs = conversation.messages.filter(is_deleted=False).select_related(
        'sender', 'recipient', 'pinned_by'
    ).prefetch_related(
        'attachments', 'reactions', 'reactions__user'
    ).order_by('created_at')

    context = {
        'title': f"{other_user.full_name or other_user.email} — Direct Message — AetherSpace",
        'workspace': workspace,
        'membership': membership,
        'conversation': conversation,
        'other_user': other_user,
        'chat_messages': messages_qs,
        **sidebar_ctx,
    }
    return render(request, 'chat/direct_message.html', context)


@workspace_member_required
def channel_create_view(request, slug):
    """
    Create Channel View matching Panel 4 of mockup:
    - Channel Name, Topic, Description
    - Channel Type: Public vs Private
    - Posting permissions selector
    """
    workspace = request.workspace
    user = request.user
    sidebar_ctx = get_chat_sidebar_context(workspace, user)

    if request.method == 'POST':
        form = ChannelForm(request.POST, workspace=workspace)
        if form.is_valid():
            channel = form.save(commit=False)
            channel.workspace = workspace
            channel.created_by = user
            channel.save()

            # Add creator as Owner of the channel
            ChannelMembership.objects.create(
                channel=channel,
                user=user,
                role=ChannelRole.OWNER
            )
            messages.success(request, f"Channel #{channel.name} created successfully!")
            return redirect('chat:channel_view', slug=slug, channel_slug=channel.slug)
    else:
        form = ChannelForm(workspace=workspace)

    context = {
        'title': f"Create Channel — {workspace.name} — AetherSpace",
        'workspace': workspace,
        'membership': request.membership,
        'form': form,
        **sidebar_ctx,
    }
    return render(request, 'chat/channel_create.html', context)


@workspace_member_required
def channel_details_view(request, slug, channel_slug):
    """
    Channel Details View matching Panel 5 of mockup:
    - Tabs: Overview, Members, Pinned, Files, Settings
    - Channel Info sidebar
    """
    workspace = request.workspace
    user = request.user
    sidebar_ctx = get_chat_sidebar_context(workspace, user)

    channel = get_object_or_404(Channel, workspace=workspace, slug=channel_slug)
    if not channel.has_member(user):
        return HttpResponseForbidden("You do not have permission to view this channel.")

    # Members list
    memberships = channel.memberships.select_related('user').order_by('-role', 'joined_at')

    # Pinned messages in channel
    pinned_messages = channel.messages.filter(is_pinned=True, is_deleted=False).select_related('sender', 'pinned_by')

    # Files in channel
    files = MessageAttachment.objects.filter(message__channel=channel, message__is_deleted=False).select_related('message', 'message__sender')

    context = {
        'title': f"#{channel.name} Details — {workspace.name} — AetherSpace",
        'workspace': workspace,
        'membership': request.membership,
        'channel': channel,
        'memberships': memberships,
        'pinned_messages': pinned_messages,
        'files': files,
        **sidebar_ctx,
    }
    return render(request, 'chat/channel_details.html', context)


@workspace_member_required
def pinned_assets_view(request, slug):
    """
    Pinned Assets View matching Panel 6 of mockup:
    - Filter tabs: All, Messages, Files, Links
    - Cards with pinned items, pin dates, and quick unpin actions
    """
    workspace = request.workspace
    user = request.user
    sidebar_ctx = get_chat_sidebar_context(workspace, user)

    tab = request.GET.get('tab', 'all').lower()

    pinned_messages = Message.objects.filter(
        workspace=workspace,
        is_pinned=True,
        is_deleted=False
    ).select_related('sender', 'pinned_by', 'channel', 'conversation').prefetch_related('attachments').order_by('-pinned_at')

    # Filter by user access
    visible_pinned = [m for m in pinned_messages if (
        (m.channel and m.channel.has_member(user)) or
        (m.conversation and m.conversation.has_participant(user))
    )]

    # Separate into messages, files, and links
    pinned_files = []
    pinned_links = []
    pure_messages = []

    link_regex = re.compile(r'(https?://[^\s]+)')

    for m in visible_pinned:
        has_file = m.attachments.exists()
        links = link_regex.findall(m.content)

        if has_file:
            pinned_files.append(m)
        if links:
            pinned_links.append({'message': m, 'links': links})
        if not has_file and not links:
            pure_messages.append(m)

    context = {
        'title': f"Pinned Assets — {workspace.name} — AetherSpace",
        'workspace': workspace,
        'membership': request.membership,
        'tab': tab,
        'visible_pinned': visible_pinned,
        'pinned_files': pinned_files,
        'pinned_links': pinned_links,
        'pure_messages': pure_messages,
        **sidebar_ctx,
    }
    return render(request, 'chat/pinned_assets.html', context)


@workspace_member_required
def shared_files_view(request, slug):
    """
    Shared Files Gallery matching Panel 7 of mockup:
    - Filters: All Files, Images, Documents, Archive, Others
    - File cards with icon, file name, uploader, size, download button
    """
    workspace = request.workspace
    user = request.user
    sidebar_ctx = get_chat_sidebar_context(workspace, user)

    filter_type = request.GET.get('type', 'all').lower()

    # Query all attachments from accessible channels or DMs
    attachments = MessageAttachment.objects.filter(
        message__workspace=workspace,
        message__is_deleted=False
    ).select_related('message', 'message__sender', 'message__channel', 'message__conversation').order_by('-uploaded_at')

    # Enforce access boundaries
    visible_attachments = []
    for att in attachments:
        msg = att.message
        if msg.channel and msg.channel.has_member(user):
            visible_attachments.append(att)
        elif msg.conversation and msg.conversation.has_participant(user):
            visible_attachments.append(att)

    # Filter by category
    if filter_type == 'images':
        visible_attachments = [a for a in visible_attachments if a.is_image or any(a.file_name.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'])]
    elif filter_type == 'documents':
        visible_attachments = [a for a in visible_attachments if any(a.file_name.lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.txt', '.xlsx', '.csv', '.ppt', '.pptx'])]
    elif filter_type == 'archive':
        visible_attachments = [a for a in visible_attachments if any(a.file_name.lower().endswith(ext) for ext in ['.zip', '.tar', '.gz', '.7z', '.rar'])]

    context = {
        'title': f"Shared Files — {workspace.name} — AetherSpace",
        'workspace': workspace,
        'membership': request.membership,
        'filter_type': filter_type,
        'attachments': visible_attachments,
        **sidebar_ctx,
    }
    return render(request, 'chat/shared_files.html', context)


# ==========================================
# REST / AJAX API Endpoints
# ==========================================

@require_POST
@workspace_member_required
def api_toggle_pin(request, slug, message_id):
    """API endpoint to toggle pin status on a message."""
    message = get_object_or_404(Message, id=message_id, workspace=request.workspace)
    try:
        is_pinned = toggle_pin_message(message, request.user)
        return JsonResponse({'status': 'ok', 'is_pinned': is_pinned})
    except PermissionDenied as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=403)


@require_POST
@workspace_member_required
def api_toggle_reaction(request, slug, message_id):
    """API endpoint to toggle an emoji reaction on a message."""
    message = get_object_or_404(Message, id=message_id, workspace=request.workspace)
    emoji = request.POST.get('emoji', '').strip()
    if not emoji:
        return JsonResponse({'status': 'error', 'message': 'Emoji is required.'}, status=400)

    try:
        added, count = toggle_reaction(message, request.user, emoji)
        return JsonResponse({'status': 'ok', 'emoji': emoji, 'added': added, 'count': count})
    except PermissionDenied as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=403)


@workspace_member_required
def api_channel_messages(request, slug, channel_slug):
    """
    JSON endpoint for message polling fallback if WebSocket is not supported.
    """
    channel = get_object_or_404(Channel, workspace=request.workspace, slug=channel_slug)
    if not channel.has_member(request.user):
        return JsonResponse({'status': 'error', 'message': 'Forbidden'}, status=403)

    since_id = request.GET.get('since')
    qs = channel.messages.filter(is_deleted=False).select_related('sender').prefetch_related('attachments', 'reactions')
    if since_id:
        try:
            since_msg = Message.objects.get(id=since_id)
            qs = qs.filter(created_at__gt=since_msg.created_at)
        except Message.DoesNotExist:
            pass

    msgs_data = []
    for m in qs.order_by('created_at')[:50]:
        sender_initial = (m.sender.full_name or m.sender.email)[:1].upper()
        msgs_data.append({
            'id': str(m.id),
            'content': m.content,
            'sender_id': str(m.sender.id),
            'sender_name': m.sender.full_name or m.sender.email,
            'sender_initial': sender_initial,
            'created_at': m.created_at.strftime("%I:%M %p"),
            'is_pinned': m.is_pinned,
            'attachments': [
                {
                    'id': str(a.id),
                    'file_name': a.file_name,
                    'file_url': a.file.url if a.file else '#',
                    'formatted_size': a.formatted_size,
                    'is_image': a.is_image
                } for a in m.attachments.all()
            ],
            'reactions': [
                {'emoji': r.emoji, 'count': 1} for r in m.reactions.all()
            ]
        })

    return JsonResponse({'status': 'ok', 'messages': msgs_data})


@login_required
def api_direct_messages(request, slug, user_id):
    """
    JSON endpoint for direct message polling fallback if WebSocket is not supported.
    """
    workspace = get_object_or_404(Workspace, slug=slug)
    current_user = request.user
    other_user = get_object_or_404(User, id=user_id)

    membership = workspace.get_user_membership(current_user)
    conversation = DirectMessageConversation.objects.filter(
        workspace=workspace
    ).filter(
        (Q(participant1=current_user) & Q(participant2=other_user)) |
        (Q(participant1=other_user) & Q(participant2=current_user))
    ).first()

    if not conversation:
        if membership:
            return JsonResponse({'status': 'ok', 'messages': []})
        raise PermissionDenied("You do not have access to this conversation.")

    since_id = request.GET.get('since')
    qs = conversation.messages.filter(is_deleted=False).select_related('sender').prefetch_related('attachments', 'reactions')
    if since_id:
        try:
            since_msg = Message.objects.get(id=since_id)
            qs = qs.filter(created_at__gt=since_msg.created_at)
        except Message.DoesNotExist:
            pass

    msgs_data = []
    for m in qs.order_by('created_at')[:50]:
        sender_initial = (m.sender.full_name or m.sender.email)[:1].upper()
        msgs_data.append({
            'id': str(m.id),
            'content': m.content,
            'sender_id': str(m.sender.id),
            'sender_name': m.sender.full_name or m.sender.email,
            'sender_initial': sender_initial,
            'created_at': m.created_at.strftime("%I:%M %p"),
            'is_pinned': m.is_pinned,
            'attachments': [
                {
                    'id': str(a.id),
                    'file_name': a.file_name,
                    'file_url': a.file.url if a.file else '#',
                    'formatted_size': a.formatted_size,
                    'is_image': a.is_image
                } for a in m.attachments.all()
            ],
            'reactions': [
                {'emoji': r.emoji, 'count': 1} for r in m.reactions.all()
            ]
        })

    return JsonResponse({'status': 'ok', 'messages': msgs_data})


@workspace_member_required
def api_search_users(request, slug):
    """
    Real-time database user search for direct messaging.
    Searches all registered users in the database by name, email, or username.
    """
    q = request.GET.get('q', '').strip()
    workspace = request.workspace
    current_user = request.user

    users_qs = User.objects.exclude(id=current_user.id)
    if q:
        users_qs = users_qs.filter(
            Q(full_name__icontains=q) |
            Q(email__icontains=q) |
            Q(username__icontains=q)
        )

    users_list = users_qs.order_by('full_name', 'email')[:25]
    workspace_memberships = {
        m.user_id: m for m in WorkspaceMembership.objects.filter(
            workspace=workspace,
            user__in=users_list,
            status=MembershipStatus.ACTIVE
        )
    }

    results = []
    for u in users_list:
        mem = workspace_memberships.get(u.id)
        results.append({
            'id': str(u.id),
            'name': u.full_name or u.email.split('@')[0],
            'email': u.email,
            'initial': (u.first_name[:1] if u.first_name else u.email[:1]).upper(),
            'is_member': mem is not None,
            'role_display': 'Workspace Member' if mem else 'Direct Chat',
            'dm_url': f"/chat/w/{workspace.slug}/dm/{u.id}/"
        })

    return JsonResponse({'status': 'ok', 'users': results})
