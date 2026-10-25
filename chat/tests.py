import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.utils import timezone

from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from chat.models import (
    Channel, ChannelMembership, ChannelRole, PostingPermission,
    DirectMessageConversation, Message, MessageAttachment, MessageReaction
)
from chat.services import (
    ensure_default_channels, get_or_create_dm_conversation,
    post_channel_message, post_direct_message,
    toggle_pin_message, toggle_reaction, mark_channel_as_read
)

User = get_user_model()


class ChatModuleTests(TestCase):
    """
    Comprehensive test suite covering Phase 7 Chat Module:
    - Default channel provisioning (#general, #project-updates)
    - Channel creation, naming, and slug generation
    - Workspace boundary isolation & multi-tenancy
    - Server-side RBAC & Channel posting permissions
    - Direct Messaging canonical conversations & isolation
    - Message pinning & unpinning
    - Emoji reactions
    - Shared files and attachments
    - All 7 UI panels and AJAX endpoints
    """

    def setUp(self):
        self.client = Client()

        # Admin user
        self.admin = User.objects.create_user(
            email='admin@aetherspace.dev',
            password='AdminPassword123!',
            full_name='Admin User',
            approval_status='APPROVED',
        )

        # Manager user
        self.manager = User.objects.create_user(
            email='manager@aetherspace.dev',
            password='ManagerPassword123!',
            full_name='Manager User',
            approval_status='APPROVED',
        )

        # Contributor user
        self.contributor = User.objects.create_user(
            email='dev@aetherspace.dev',
            password='DevPassword123!',
            full_name='Dev Contributor',
            approval_status='APPROVED',
        )

        # Second Contributor
        self.contributor2 = User.objects.create_user(
            email='designer@aetherspace.dev',
            password='DesignerPassword123!',
            full_name='Designer Contributor',
            approval_status='APPROVED',
        )

        # Outsider user (belongs to a different workspace)
        self.outsider = User.objects.create_user(
            email='outsider@external.dev',
            password='OutsiderPassword123!',
            full_name='Outsider User',
            approval_status='APPROVED',
        )

        # Primary Workspace
        self.workspace = Workspace.objects.create(
            name='Alpha Team',
            slug='alpha-team',
            owner=self.admin
        )

        # Workspace Memberships
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.manager,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor2,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Secondary Workspace for multi-tenant tests
        self.other_workspace = Workspace.objects.create(
            name='Beta Team',
            slug='beta-team',
            owner=self.outsider
        )
        WorkspaceMembership.objects.create(
            workspace=self.other_workspace,
            user=self.outsider,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    # -------------------------------------------------------------
    # 1. Models & Services Tests
    # -------------------------------------------------------------

    def test_default_channels_provisioning(self):
        """Default channels (#general, #project-updates) should be auto-created."""
        channels = ensure_default_channels(self.workspace, creator=self.admin)
        self.assertGreaterEqual(len(channels), 2)

        general = Channel.objects.get(workspace=self.workspace, slug='general')
        self.assertEqual(general.name, 'general')
        self.assertFalse(general.is_private)
        self.assertEqual(general.who_can_post, PostingPermission.ALL)

        updates = Channel.objects.get(workspace=self.workspace, slug='project-updates')
        self.assertEqual(updates.name, 'project-updates')
        self.assertEqual(updates.who_can_post, PostingPermission.ADMIN_ONLY)

    def test_direct_message_canonical_ordering(self):
        """Conversations should have deterministic ordering regardless of who initiates."""
        conv1 = get_or_create_dm_conversation(self.workspace, self.admin, self.contributor)
        conv2 = get_or_create_dm_conversation(self.workspace, self.contributor, self.admin)
        self.assertEqual(conv1.id, conv2.id)
        self.assertTrue(conv1.has_participant(self.admin))
        self.assertTrue(conv1.has_participant(self.contributor))
        self.assertFalse(conv1.has_participant(self.outsider))

    def test_channel_posting_permission_rules(self):
        """Verify can_post method on Channel reflects role & who_can_post correctly."""
        ensure_default_channels(self.workspace, creator=self.admin)
        general = Channel.objects.get(workspace=self.workspace, slug='general')
        updates = Channel.objects.get(workspace=self.workspace, slug='project-updates')

        # General is open to all members
        self.assertTrue(general.can_post(self.admin))
        self.assertTrue(general.can_post(self.contributor))

        # Project updates is restricted to Admin & Manager
        self.assertTrue(updates.can_post(self.admin))
        self.assertTrue(updates.can_post(self.manager))
        self.assertFalse(updates.can_post(self.contributor))

    def test_post_channel_message_and_pin(self):
        """Messages can be posted, retrieved, and pinned/unpinned."""
        ensure_default_channels(self.workspace, creator=self.admin)
        general = Channel.objects.get(workspace=self.workspace, slug='general')

        msg = post_channel_message(general, self.admin, content="Welcome everyone to Phase 7!")
        self.assertEqual(msg.content, "Welcome everyone to Phase 7!")
        self.assertFalse(msg.is_pinned)

        # Pin message
        is_pinned = toggle_pin_message(msg, self.admin)
        self.assertTrue(is_pinned)
        msg.refresh_from_db()
        self.assertTrue(msg.is_pinned)
        self.assertEqual(msg.pinned_by, self.admin)

        # Unpin message
        is_pinned_after = toggle_pin_message(msg, self.admin)
        self.assertFalse(is_pinned_after)
        msg.refresh_from_db()
        self.assertFalse(msg.is_pinned)

    def test_message_emoji_reactions(self):
        """Users can toggle emoji reactions on a message."""
        ensure_default_channels(self.workspace, creator=self.admin)
        general = Channel.objects.get(workspace=self.workspace, slug='general')
        msg = post_channel_message(general, self.contributor, content="Great progress today!")

        # Add reaction 👍
        added, count = toggle_reaction(msg, self.admin, "👍")
        self.assertTrue(added)
        self.assertEqual(count, 1)

        # Toggle reaction 👍 again removes it
        added_again, count_after = toggle_reaction(msg, self.admin, "👍")
        self.assertFalse(added_again)
        self.assertEqual(count_after, 0)

    # -------------------------------------------------------------
    # 2. View & Panel Tests
    # -------------------------------------------------------------

    def test_chat_router_redirects(self):
        """chat_router redirects logged in user to active workspace chat home."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('chat:chat_router'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/chat/w/{self.workspace.slug}/", response.url)

    def test_chat_home_panel_1(self):
        """Chat home renders Panel 1 with metrics, recent conversations, and quick links."""
        self.client.force_login(self.contributor)
        response = self.client.get(reverse('chat:chat_home', kwargs={'slug': self.workspace.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/chat_home.html')
        self.assertContains(response, "Team Chat & Collaboration")
        self.assertContains(response, "Total Channels")
        self.assertContains(response, "Workspace Members")

    def test_channel_view_panel_2(self):
        """Channel view renders Panel 2 with message stream and message input."""
        ensure_default_channels(self.workspace, creator=self.admin)
        self.client.force_login(self.contributor)
        response = self.client.get(reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': 'general'
        }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/channel_view.html')
        self.assertContains(response, "#general")
        self.assertContains(response, "About #general")

    def test_channel_post_message_http_fallback(self):
        """Channel view accepts standard POST form submissions (fallback & attachments)."""
        ensure_default_channels(self.workspace, creator=self.admin)
        self.client.force_login(self.contributor)
        url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': 'general'
        })
        response = self.client.post(url, {'content': 'Hello from HTTP fallback!'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hello from HTTP fallback!')

    def test_direct_message_panel_3(self):
        """Direct message view renders Panel 3 with 1-on-1 discussion stream."""
        self.client.force_login(self.admin)
        url = reverse('chat:direct_message', kwargs={
            'slug': self.workspace.slug,
            'user_id': self.contributor.id
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/direct_message.html')
        self.assertContains(response, self.contributor.full_name)

        # Post message in DM
        post_resp = self.client.post(url, {'content': 'Direct message text here!'}, follow=True)
        self.assertEqual(post_resp.status_code, 200)
        self.assertContains(post_resp, 'Direct message text here!')

    def test_channel_create_panel_4(self):
        """Create channel view renders Panel 4 and creates a new channel."""
        self.client.force_login(self.admin)
        url = reverse('chat:channel_create', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/channel_create.html')

        post_data = {
            'name': 'frontend-team',
            'topic': 'UI/UX and frontend engineering',
            'description': 'Discussion of design system and templates',
            'who_can_post': PostingPermission.ALL,
        }
        create_resp = self.client.post(url, post_data, follow=True)
        self.assertEqual(create_resp.status_code, 200)
        self.assertTrue(Channel.objects.filter(workspace=self.workspace, slug='frontend-team').exists())

    def test_channel_details_panel_5(self):
        """Channel details view renders Panel 5 with tabs: Overview, Members, Pinned, Files."""
        ensure_default_channels(self.workspace, creator=self.admin)
        self.client.force_login(self.admin)
        url = reverse('chat:channel_details', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': 'general'
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/channel_details.html')
        self.assertContains(response, "Channel Metadata")
        self.assertContains(response, "Members")

    def test_pinned_assets_panel_6(self):
        """Pinned assets view renders Panel 6 with pinned items list."""
        ensure_default_channels(self.workspace, creator=self.admin)
        general = Channel.objects.get(workspace=self.workspace, slug='general')
        msg = post_channel_message(general, self.admin, content="Important roadmap update pinned here!")
        toggle_pin_message(msg, self.admin)

        self.client.force_login(self.contributor)
        url = reverse('chat:pinned_assets', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/pinned_assets.html')
        self.assertContains(response, "Pinned Assets")
        self.assertContains(response, "Important roadmap update pinned here!")

    def test_shared_files_panel_7(self):
        """Shared files view renders Panel 7 with attachments gallery."""
        ensure_default_channels(self.workspace, creator=self.admin)
        general = Channel.objects.get(workspace=self.workspace, slug='general')

        fake_file = SimpleUploadedFile("architecture.pdf", b"PDF file mock content", content_type="application/pdf")
        post_channel_message(general, self.admin, content="Architecture diagram", files=[fake_file])

        self.client.force_login(self.contributor)
        url = reverse('chat:shared_files', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/shared_files.html')
        self.assertContains(response, "Shared Files")
        self.assertContains(response, "architecture.pdf")

    # -------------------------------------------------------------
    # 3. RBAC & Multi-Tenant Boundary Tests
    # -------------------------------------------------------------

    def test_outsider_cannot_access_workspace_chat(self):
        """Users outside the workspace receive 403 or redirect to access request."""
        self.client.force_login(self.outsider)
        url = reverse('chat:chat_home', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        # workspace_member_required redirects non-members to request_access
        self.assertIn(response.status_code, [302, 403])

    def test_private_channel_isolation(self):
        """Non-members cannot view or post to a private channel."""
        private_ch = Channel.objects.create(
            workspace=self.workspace,
            name='leadership-confidential',
            slug='leadership-confidential',
            is_private=True,
            created_by=self.admin
        )
        # Add admin only
        ChannelMembership.objects.create(
            channel=private_ch,
            user=self.admin,
            role=ChannelRole.OWNER
        )

        # Contributor is not a member of this private channel
        self.client.force_login(self.contributor)
        url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': private_ch.slug
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_direct_message_third_party_isolation(self):
        """A user cannot access DM conversation between two other users."""
        dm = get_or_create_dm_conversation(self.workspace, self.admin, self.manager)

        # Contributor tries to access DM of manager and admin
        self.client.force_login(self.contributor)
        url = reverse('chat:direct_message', kwargs={
            'slug': self.workspace.slug,
            'user_id': self.manager.id
        })
        # This will load contributor's own DM with manager, NOT admin's DM with manager
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Context conversation must NOT be dm between admin and manager
        self.assertNotEqual(response.context['conversation'].id, dm.id)

    # -------------------------------------------------------------
    # 4. AJAX / REST API Endpoints Tests
    # -------------------------------------------------------------

    def test_api_toggle_pin(self):
        """API toggle pin endpoint works via POST."""
        ensure_default_channels(self.workspace, creator=self.admin)
        general = Channel.objects.get(workspace=self.workspace, slug='general')
        msg = post_channel_message(general, self.admin, content="Pin me via API")

        self.client.force_login(self.admin)
        url = reverse('chat:api_toggle_pin', kwargs={
            'slug': self.workspace.slug,
            'message_id': msg.id
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['is_pinned'])

    def test_api_toggle_reaction(self):
        """API toggle reaction endpoint works via POST."""
        ensure_default_channels(self.workspace, creator=self.admin)
        general = Channel.objects.get(workspace=self.workspace, slug='general')
        msg = post_channel_message(general, self.admin, content="React to me via API")

        self.client.force_login(self.contributor)
        url = reverse('chat:api_toggle_reaction', kwargs={
            'slug': self.workspace.slug,
            'message_id': msg.id
        })
        response = self.client.post(url, {'emoji': '🚀'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['emoji'], '🚀')
        self.assertTrue(data['added'])
        self.assertEqual(data['count'], 1)

    def test_api_channel_messages_polling(self):
        """API channel messages endpoint returns messages as JSON."""
        ensure_default_channels(self.workspace, creator=self.admin)
        general = Channel.objects.get(workspace=self.workspace, slug='general')
        post_channel_message(general, self.admin, content="Live message polling test")

        self.client.force_login(self.contributor)
        url = reverse('chat:api_channel_messages', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': 'general'
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'ok')
        self.assertGreaterEqual(len(data['messages']), 1)
        self.assertIn("Live message polling test", [m['content'] for m in data['messages']])

    def test_api_search_users(self):
        """API user search finds registered users across the database."""
        self.client.force_login(self.admin)
        url = reverse('chat:api_search_users', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url, {'q': 'outsider'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(any(u['email'] == self.outsider.email for u in data['users']))

    def test_direct_message_allows_chatting_without_workspace_enrollment(self):
        """Starting a DM with a user in the DB who is not in this workspace allows chatting without enrolling them as workspace members."""
        self.assertFalse(self.workspace.has_user(self.outsider))
        self.client.force_login(self.admin)
        url = reverse('chat:direct_message', kwargs={
            'slug': self.workspace.slug,
            'user_id': self.outsider.id
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Verified: external participant is NOT added to workspace membership roster
        self.assertFalse(self.workspace.has_user(self.outsider))

        # Verified: DM can receive messages
        post_resp = self.client.post(url, {'content': 'Hello external user!'}, follow=True)
        self.assertEqual(post_resp.status_code, 200)
        self.assertContains(post_resp, 'Hello external user!')
        self.assertFalse(self.workspace.has_user(self.outsider))

    def test_channel_add_and_remove_member(self):
        """Authorized user can add and remove members from a channel."""
        channel = Channel.objects.create(
            workspace=self.workspace,
            name='private-space',
            slug='private-space',
            is_private=True,
            created_by=self.admin
        )
        ChannelMembership.objects.create(channel=channel, user=self.admin, role=ChannelRole.OWNER)

        # Contributor is not in channel
        self.assertFalse(channel.memberships.filter(user=self.contributor).exists())

        # Admin adds contributor
        self.client.force_login(self.admin)
        add_url = reverse('chat:channel_add_members', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': channel.slug
        })
        resp = self.client.post(add_url, {'user_ids': [str(self.contributor.id)], 'role': 'MEMBER'}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(channel.memberships.filter(user=self.contributor).exists())

        # Admin removes contributor
        remove_url = reverse('chat:channel_remove_member', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': channel.slug,
            'user_id': self.contributor.id
        })
        resp = self.client.post(remove_url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(channel.memberships.filter(user=self.contributor).exists())

    def test_channel_creator_cannot_be_removed(self):
        """Channel creator cannot be removed from the channel."""
        channel = Channel.objects.create(
            workspace=self.workspace,
            name='design-sprint',
            slug='design-sprint',
            created_by=self.admin
        )
        ChannelMembership.objects.create(channel=channel, user=self.admin, role=ChannelRole.OWNER)

        self.client.force_login(self.manager)
        remove_url = reverse('chat:channel_remove_member', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': channel.slug,
            'user_id': self.admin.id
        })
        resp = self.client.post(remove_url, follow=True)
        self.assertEqual(resp.status_code, 200)
        # Still a member because creator cannot be removed
        self.assertTrue(channel.memberships.filter(user=self.admin).exists())

    def test_channel_leave_space(self):
        """Members can voluntarily leave a non-default space."""
        channel = Channel.objects.create(
            workspace=self.workspace,
            name='random-ideas',
            slug='random-ideas',
            created_by=self.admin
        )
        ChannelMembership.objects.create(channel=channel, user=self.admin, role=ChannelRole.OWNER)
        ChannelMembership.objects.create(channel=channel, user=self.contributor, role=ChannelRole.MEMBER)

        self.client.force_login(self.contributor)
        leave_url = reverse('chat:channel_leave', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': channel.slug
        })
        resp = self.client.post(leave_url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(channel.memberships.filter(user=self.contributor).exists())

    def test_channel_delete_space_and_protection(self):
        """Custom spaces can be deleted by authorized users; default channels cannot be deleted."""
        ensure_default_channels(self.workspace, creator=self.admin)
        general = Channel.objects.get(workspace=self.workspace, slug='general')

        self.client.force_login(self.admin)
        # Attempting to delete #general is disallowed
        gen_delete_url = reverse('chat:channel_delete', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': general.slug
        })
        resp = self.client.post(gen_delete_url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Channel.objects.filter(workspace=self.workspace, slug='general').exists())

        # Deleting a custom channel succeeds
        custom_channel = Channel.objects.create(
            workspace=self.workspace,
            name='temp-space',
            slug='temp-space',
            created_by=self.admin
        )
        ChannelMembership.objects.create(channel=custom_channel, user=self.admin, role=ChannelRole.OWNER)
        custom_delete_url = reverse('chat:channel_delete', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': custom_channel.slug
        })
        resp = self.client.post(custom_delete_url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Channel.objects.filter(workspace=self.workspace, slug='temp-space').exists())


class ChatSecurityXSSHardeningTests(TestCase):
    """
    Security regression tests for Batch 1: DOM XSS and Reaction Input Hardening.
    """
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='security.chat@aetherspace.dev',
            password='StrongPassword123!',
            full_name='Security Chat User',
            approval_status='APPROVED'
        )
        self.workspace = Workspace.objects.create(
            name='Chat Security Team',
            slug='chat-sec-team',
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        self.channel = Channel.objects.create(
            workspace=self.workspace,
            name='security-test',
            slug='security-test',
            created_by=self.user
        )
        ChannelMembership.objects.create(
            channel=self.channel,
            user=self.user,
            role=ChannelRole.OWNER
        )
        self.message = post_channel_message(
            channel=self.channel,
            sender=self.user,
            content="Security test message"
        )
        self.client.force_login(self.user)
        self.toggle_url = reverse('chat:api_toggle_reaction', kwargs={
            'slug': self.workspace.slug,
            'message_id': self.message.id
        })

    def test_valid_unicode_emojis_accepted(self):
        """Ensure standard and multi-codepoint Unicode emojis are supported."""
        for emoji in ['👍', '❤️', '🚀', '😂', '👍🏽']:
            added, count = toggle_reaction(self.message, self.user, emoji)
            self.assertTrue(added)
            self.assertEqual(count, 1)
            # Toggle off
            added, count = toggle_reaction(self.message, self.user, emoji)
            self.assertFalse(added)
            self.assertEqual(count, 0)

    def test_empty_and_whitespace_emoji_rejected(self):
        """Ensure empty strings or whitespace-only emoji reactions are rejected."""
        with self.assertRaises(ValidationError):
            toggle_reaction(self.message, self.user, "")

        with self.assertRaises(ValidationError):
            toggle_reaction(self.message, self.user, "   ")

        with self.assertRaises(ValidationError):
            toggle_reaction(self.message, self.user, None)

        # Test API endpoint response
        resp = self.client.post(self.toggle_url, json.dumps({'emoji': ''}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get('status'), 'error')

    def test_oversized_emoji_payload_rejected(self):
        """Ensure oversized emoji reaction payloads are rejected."""
        oversized = "👍" * 33
        with self.assertRaises(ValidationError):
            toggle_reaction(self.message, self.user, oversized)

        oversized_str = "A" * 35
        with self.assertRaises(ValidationError):
            toggle_reaction(self.message, self.user, oversized_str)

        resp = self.client.post(self.toggle_url, json.dumps({'emoji': oversized}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get('status'), 'error')

    def test_templates_do_not_contain_unsafe_emoji_innerhtml(self):
        """Static regression test: verify chat templates do not interpolate emoji into innerHTML."""
        import os
        from django.conf import settings
        template_files = [
            os.path.join(settings.BASE_DIR, 'templates', 'chat', 'direct_message.html'),
            os.path.join(settings.BASE_DIR, 'templates', 'chat', 'channel_view.html'),
        ]
        unsafe_patterns = [
            'innerHTML = `<span>${emoji}</span>`',
            'innerHTML = `<span>${rData.emoji}</span>',
            'innerHTML = `<span>${rData.emoji}</span>${rData.total_count',
            'innerHTML = `<span>${emoji}</span>${totalCount',
        ]
        for template_path in template_files:
            self.assertTrue(os.path.exists(template_path), f"Template missing: {template_path}")
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
            for pattern in unsafe_patterns:
                self.assertNotIn(
                    pattern,
                    content,
                    f"Found unsafe innerHTML pattern '{pattern}' in {template_path}"
                )


class ChatSecurityRequestForgeryHardeningTests(TestCase):
    """
    Security regression tests for Batch 2: Client-side Request Forgery Hardening.
    Ensures reaction endpoint is fixed/server-generated, message IDs are safely sent
    and validated in request bodies, CSRF is strictly enforced, and cross-workspace access is prevented.
    """
    def setUp(self):
        import uuid
        self.client = Client()
        self.user = User.objects.create_user(
            email='rf.security@aetherspace.dev',
            password='StrongPassword123!',
            full_name='RF Security User',
            approval_status='APPROVED'
        )
        self.workspace = Workspace.objects.create(
            name='RF Security Workspace',
            slug='rf-sec-ws',
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        self.channel = Channel.objects.create(
            workspace=self.workspace,
            name='rf-sec-channel',
            slug='rf-sec-channel',
            created_by=self.user
        )
        ChannelMembership.objects.create(
            channel=self.channel,
            user=self.user,
            role=ChannelRole.OWNER
        )
        self.message = post_channel_message(
            channel=self.channel,
            sender=self.user,
            content="Message for request forgery security tests"
        )
        self.client.force_login(self.user)
        self.fixed_reaction_url = reverse('chat:api_toggle_reaction', kwargs={
            'slug': self.workspace.slug
        })

    def test_normal_reaction_via_body_parameter(self):
        """A legitimate authenticated workspace member can react successfully sending message_id in body."""
        # 1. Add reaction
        resp = self.client.post(self.fixed_reaction_url, {
            'message_id': str(self.message.id),
            'emoji': '🚀'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertTrue(data.get('added'))
        self.assertEqual(data.get('count'), 1)
        self.assertTrue(MessageReaction.objects.filter(
            message=self.message,
            user=self.user,
            emoji='🚀'
        ).exists())

        # 2. Toggle off
        resp2 = self.client.post(self.fixed_reaction_url, {
            'message_id': str(self.message.id),
            'emoji': '🚀'
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2.get('status'), 'ok')
        self.assertFalse(data2.get('added'))
        self.assertEqual(data2.get('count'), 0)
        self.assertFalse(MessageReaction.objects.filter(
            message=self.message,
            user=self.user,
            emoji='🚀'
        ).exists())

    def test_reaction_csrf_enforcement(self):
        """Verify POST requests without CSRF protection are rejected with 403."""
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        resp = csrf_client.post(self.fixed_reaction_url, {
            'message_id': str(self.message.id),
            'emoji': '👍'
        })
        self.assertEqual(resp.status_code, 403)

    def test_cross_workspace_isolation(self):
        """Ensure cross-workspace reaction attempts are strictly blocked."""
        user2 = User.objects.create_user(
            email='other.workspace.user@aetherspace.dev',
            password='StrongPassword123!',
            full_name='Other User',
            approval_status='APPROVED'
        )
        workspace2 = Workspace.objects.create(
            name='Isolated Workspace 2',
            slug='isolated-ws-2',
            owner=user2
        )
        WorkspaceMembership.objects.create(
            workspace=workspace2,
            user=user2,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        channel2 = Channel.objects.create(
            workspace=workspace2,
            name='channel2',
            slug='channel2',
            created_by=user2
        )
        ChannelMembership.objects.create(
            channel=channel2,
            user=user2,
            role=ChannelRole.OWNER
        )
        message2 = post_channel_message(
            channel=channel2,
            sender=user2,
            content="Workspace 2 isolated message"
        )

        # Attempt A: user2 tries to POST to workspace 1 endpoint -> 403 PermissionDenied
        client2 = Client()
        client2.force_login(user2)
        resp_a = client2.post(self.fixed_reaction_url, {
            'message_id': str(self.message.id),
            'emoji': '👍'
        })
        self.assertEqual(resp_a.status_code, 403)

        # Attempt B: self.user (Workspace 1 member) tries to react to message2 (Workspace 2) via workspace 1 endpoint -> 404 Not Found
        resp_b = self.client.post(self.fixed_reaction_url, {
            'message_id': str(message2.id),
            'emoji': '👍'
        })
        self.assertEqual(resp_b.status_code, 404)
        self.assertEqual(resp_b.json().get('status'), 'error')
        self.assertFalse(MessageReaction.objects.filter(message=message2).exists())

    def test_invalid_message_ids_return_safe_4xx(self):
        """Verify malformed and nonexistent message IDs return safe 4xx responses without unhandled crashes."""
        import uuid
        # Malformed path traversal string
        resp1 = self.client.post(self.fixed_reaction_url, {
            'message_id': '../../admin/auth/user/',
            'emoji': '👍'
        })
        self.assertEqual(resp1.status_code, 400)
        self.assertEqual(resp1.json().get('message'), 'Invalid message ID.')

        # Missing message_id
        resp2 = self.client.post(self.fixed_reaction_url, {
            'emoji': '👍'
        })
        self.assertEqual(resp2.status_code, 400)
        self.assertEqual(resp2.json().get('message'), 'Message ID is required.')

        # Non-existent UUID
        random_uuid = str(uuid.uuid4())
        resp3 = self.client.post(self.fixed_reaction_url, {
            'message_id': random_uuid,
            'emoji': '👍'
        })
        self.assertEqual(resp3.status_code, 404)
        self.assertEqual(resp3.json().get('message'), 'Message not found.')

    def test_reaction_validation_preserved_batch1(self):
        """Verify Batch 1 emoji validations remain active on the fixed endpoint."""
        # Empty emoji
        resp_empty = self.client.post(self.fixed_reaction_url, {
            'message_id': str(self.message.id),
            'emoji': ''
        })
        self.assertEqual(resp_empty.status_code, 400)

        # Whitespace emoji
        resp_ws = self.client.post(self.fixed_reaction_url, {
            'message_id': str(self.message.id),
            'emoji': '   '
        })
        self.assertEqual(resp_ws.status_code, 400)

        # Oversized emoji (> 32 chars)
        resp_over = self.client.post(self.fixed_reaction_url, {
            'message_id': str(self.message.id),
            'emoji': '🚀' * 33
        })
        self.assertEqual(resp_over.status_code, 400)

        # Multi-codepoint Unicode emojis supported
        for em in ['❤️', '👍🏽', '👨‍💻']:
            resp_em = self.client.post(self.fixed_reaction_url, {
                'message_id': str(self.message.id),
                'emoji': em
            })
            self.assertEqual(resp_em.status_code, 200)
            self.assertEqual(resp_em.json().get('status'), 'ok')

    def test_client_side_templates_use_trusted_static_endpoint(self):
        """Verify chat templates do not construct reaction fetch URLs from dynamic messageId."""
        import os
        from django.conf import settings
        template_files = [
            os.path.join(settings.BASE_DIR, 'templates', 'chat', 'direct_message.html'),
            os.path.join(settings.BASE_DIR, 'templates', 'chat', 'channel_view.html'),
        ]
        forbidden_patterns = [
            '/api/react/${messageId}',
            'api/react/${',
        ]
        for template_path in template_files:
            self.assertTrue(os.path.exists(template_path), f"Template missing: {template_path}")
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()

            for pattern in forbidden_patterns:
                self.assertNotIn(
                    pattern,
                    content,
                    f"Template {template_path} still contains untrusted URL construction '{pattern}'"
                )

            # Ensure reactionEndpoint configuration is passed
            self.assertIn("reactionEndpoint: '{% url 'chat:api_toggle_reaction' slug=workspace.slug %}'", content)
            # Ensure message_id is appended to FormData
            self.assertIn("formData.append('message_id', String(messageId));", content)

    def test_legacy_url_pattern_backward_compatibility(self):
        """Verify legacy parameterized route continues to work for existing integrations."""
        legacy_url = reverse('chat:api_toggle_reaction', kwargs={
            'slug': self.workspace.slug,
            'message_id': self.message.id
        })
        resp = self.client.post(legacy_url, {'emoji': '🎉'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get('status'), 'ok')


class ChatRichTextAndComposerTests(TestCase):
    """
    Focused tests for Chat Rich-Text Editing, Rendering, Sanitization, and Composer Behavior:
    - Formatting (bold, italic, strikethrough, bulleted/numbered lists, inline code, code blocks, blockquotes, hyperlinks)
    - Rejection of dangerous URL protocols (javascript:, data:, vbscript:)
    - Strict XSS sanitization and script stripping
    - Mention pills and code block protection
    - WebSocket server-rendered payload parity with HTTP initial load
    - Consecutive message grouping logic (is_consecutive)
    - Legacy plain-text and markdown message backward compatibility
    - Channel and Direct Message authorization and message submission
    """

    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(
            email='alice@aetherspace.dev',
            password='Password123!',
            full_name='Alice Smith',
            contributor_id='10001A',
            approval_status='APPROVED',
        )
        self.user2 = User.objects.create_user(
            email='bob@aetherspace.dev',
            password='Password123!',
            full_name='Bob Jones',
            contributor_id='10002B',
            approval_status='APPROVED',
        )
        self.outsider = User.objects.create_user(
            email='eve@outsider.dev',
            password='Password123!',
            full_name='Eve Outsider',
            approval_status='APPROVED',
        )

        self.workspace = Workspace.objects.create(
            name='Orion Space',
            slug='orion-space',
            owner=self.user1
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user1,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user2,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        self.channel = Channel.objects.create(
            workspace=self.workspace,
            name='engineering',
            slug='engineering',
            created_by=self.user1,
            who_can_post=PostingPermission.ALL
        )
        ChannelMembership.objects.create(
            channel=self.channel,
            user=self.user1,
            role=ChannelRole.OWNER
        )
        ChannelMembership.objects.create(
            channel=self.channel,
            user=self.user2,
            role=ChannelRole.MEMBER
        )

        self.dm_conv = get_or_create_dm_conversation(self.workspace, self.user1, self.user2)

    def test_formatting_elements(self):
        """Rich-text elements (bold, italic, strikethrough, lists, code, blockquotes, links) render accurately."""
        from core.templatetags.rich_text import render_rich_text

        # Bold
        html_bold = str(render_rich_text("**Bold Text**"))
        self.assertIn("<strong>Bold Text</strong>", html_bold)

        # Italic
        html_italic = str(render_rich_text("*Italic Text*"))
        self.assertIn("<em>Italic Text</em>", html_italic)

        # Strikethrough
        html_strike = str(render_rich_text("~~Strike Text~~"))
        self.assertIn("<del>Strike Text</del>", html_strike)

        # Bulleted List
        html_ul = str(render_rich_text("- Item 1\n- Item 2"))
        self.assertIn("<ul>", html_ul)
        self.assertIn("<li>Item 1</li>", html_ul)
        self.assertIn("<li>Item 2</li>", html_ul)

        # Numbered List
        html_ol = str(render_rich_text("1. First item\n2. Second item"))
        self.assertIn("<ol>", html_ol)
        self.assertIn("<li>First item</li>", html_ol)
        self.assertIn("<li>Second item</li>", html_ol)

        # Inline Code
        html_code = str(render_rich_text("`const x = 42;`"))
        self.assertIn("<code>const x = 42;</code>", html_code)

        # Code Block
        html_codeblock = str(render_rich_text("```\nfunction hello() {\n  return true;\n}\n```"))
        self.assertIn("<pre><code>", html_codeblock)
        self.assertIn("function hello()", html_codeblock)

        # Blockquote
        html_quote = str(render_rich_text("> This is a team quotation"))
        self.assertIn("<blockquote>", html_quote)
        self.assertIn("This is a team quotation", html_quote)

        # Valid Hyperlink
        html_link = str(render_rich_text("[AetherSpace](https://aetherspace.dev)"))
        self.assertIn('href="https://aetherspace.dev"', html_link)
        self.assertIn('target="_blank"', html_link)
        self.assertIn('rel="noopener noreferrer"', html_link)
        self.assertIn('AetherSpace', html_link)

    def test_dangerous_url_protocols_rejected(self):
        """Dangerous protocols (javascript:, data:, vbscript:) must never be rendered as clickable links."""
        from core.templatetags.rich_text import render_rich_text

        # javascript: link
        html_js = str(render_rich_text("[Click Me](javascript:alert('pwned'))"))
        self.assertNotIn('href="javascript:', html_js)

        # data: link
        html_data = str(render_rich_text("[Bad Data](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)"))
        self.assertNotIn('href="data:', html_data)

        # vbscript: link
        html_vbs = str(render_rich_text("[Bad VBS](vbscript:msgbox(1))"))
        self.assertNotIn('href="vbscript:', html_vbs)

    def test_xss_script_tags_stripped(self):
        """Script tags and malicious inline handlers must be completely stripped by sanitization."""
        from core.templatetags.rich_text import render_rich_text

        # Raw <script> tag is stripped completely so script never executes
        html_script = str(render_rich_text("<script>alert('xss')</script>"))
        self.assertNotIn("<script>", html_script)
        self.assertNotIn("</script>", html_script)

        # Malicious <img> onerror handler
        html_img = str(render_rich_text('<img src="x" onerror="alert(1)">'))
        self.assertNotIn('onerror', html_img)

        # Malicious event handler on allowed tag
        html_event = str(render_rich_text('<div onclick="alert(1)">Clickable</div>'))
        self.assertNotIn('onclick', html_event)

    def test_mentions_inside_prose_and_code_block_protection(self):
        """Mentions in prose transform to pills, but occurrences inside code blocks are preserved as literal text."""
        from core.templatetags.rich_text import render_rich_text

        # Formatted mention: @[Name](ID)
        html_mention1 = str(render_rich_text("Please check with @[Alice Smith](10001A) on this."))
        self.assertIn("aether-mention", html_mention1)
        self.assertIn('data-user-id="10001A"', html_mention1)
        self.assertIn("@Alice Smith", html_mention1)

        # Contributor ID mention: @10002B
        html_mention2 = str(render_rich_text("Handled by @10002B in sprint 4."))
        self.assertIn("aether-mention", html_mention2)
        self.assertIn('data-contributor-id="10002B"', html_mention2)

        # Name mention: @Alice
        html_mention3 = str(render_rich_text("Thanks @Alice for the review."))
        self.assertIn("aether-mention", html_mention3)

        # Protected inside code block: @login_required should NOT become a mention pill
        html_code_mention = str(render_rich_text("Use `@login_required` decorator above view."))
        self.assertIn("<code>@login_required</code>", html_code_mention)
        self.assertNotIn('class="aether-mention', html_code_mention)

    def test_websocket_save_message_parity_with_server_render(self):
        """ChatConsumer.save_message produces rendered_content matching server render_rich_text."""
        from chat.consumers import ChatConsumer
        from core.templatetags.rich_text import render_rich_text
        from asgiref.sync import async_to_sync

        consumer = ChatConsumer()
        consumer.channel_id = str(self.channel.id)
        consumer.conversation_id = None
        consumer.user = self.user1

        text = "Hello team, **v2.0 is live** with [Docs](https://aetherspace.dev/docs)"
        result = async_to_sync(consumer.save_message)(text)

        self.assertEqual(result["content"], text)
        expected_rendered = str(render_rich_text(text))
        self.assertEqual(result["rendered_content"], expected_rendered)
        self.assertIn("<strong>v2.0 is live</strong>", result["rendered_content"])
        self.assertIn("https://aetherspace.dev/docs", result["rendered_content"])

    def test_consecutive_message_grouping_logic(self):
        """Consecutive messages from the same sender within 5 minutes are flagged is_consecutive=True."""
        import datetime
        from django.utils import timezone
        now = timezone.now()

        # Message 1
        m1 = post_channel_message(self.channel, self.user1, content="Message 1")
        m1.created_at = now
        m1.save()

        # Message 2 from same sender 1 minute later -> should be consecutive
        m2 = post_channel_message(self.channel, self.user1, content="Message 2")
        m2.created_at = now + datetime.timedelta(minutes=1)
        m2.save()

        # Message 3 from different sender 2 minutes later -> not consecutive
        m3 = post_channel_message(self.channel, self.user2, content="Message 3")
        m3.created_at = now + datetime.timedelta(minutes=2)
        m3.save()

        # Message 4 from user2 10 minutes later -> not consecutive (> 5 minutes gap)
        m4 = post_channel_message(self.channel, self.user2, content="Message 4")
        m4.created_at = now + datetime.timedelta(minutes=12)
        m4.save()

        # Call invite message -> never grouped as consecutive
        m5 = post_channel_message(self.channel, self.user2, content="CALL_INVITE:meet-1234-5678:VIDEO:Standup")
        m5.created_at = now + datetime.timedelta(minutes=13)
        m5.save()

        self.client.force_login(self.user1)
        resp = self.client.get(reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        }))
        self.assertEqual(resp.status_code, 200)

        # Inspect chat_messages in context
        ctx_messages = {m.content: m for m in resp.context['chat_messages']}
        self.assertFalse(ctx_messages["Message 1"].is_consecutive)
        self.assertTrue(ctx_messages["Message 2"].is_consecutive)
        self.assertFalse(ctx_messages["Message 3"].is_consecutive)
        self.assertFalse(ctx_messages["Message 4"].is_consecutive)
        self.assertFalse(ctx_messages["CALL_INVITE:meet-1234-5678:VIDEO:Standup"].is_consecutive)

    def test_legacy_messages_backward_compatibility(self):
        """Legacy plain-text and markdown messages render cleanly without breaking."""
        from core.templatetags.rich_text import render_rich_text

        # Plain text
        plain_text = "This is a simple plain text message from before rich-text editor."
        res_plain = str(render_rich_text(plain_text))
        self.assertEqual(res_plain, plain_text)

        # Multiline plain text
        multiline = "Line 1\nLine 2\nLine 3"
        res_multi = str(render_rich_text(multiline))
        self.assertIn("Line 1", res_multi)
        self.assertIn("Line 2", res_multi)
        self.assertIn("Line 3", res_multi)

    def test_channel_view_http_post_and_rich_text_render(self):
        """Users can post CommonMark messages via HTTP form fallback and view them rendered."""
        self.client.force_login(self.user1)
        channel_url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })

        # Post rich-text content
        post_resp = self.client.post(channel_url, {
            'content': '**Sprint Update**:\n- Feature A completed\n- Reviewing PR #42'
        })
        self.assertEqual(post_resp.status_code, 302)

        # View channel
        get_resp = self.client.get(channel_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, "<strong>Sprint Update</strong>")
        self.assertContains(get_resp, "Feature A completed")

    def test_direct_message_view_http_post_and_rich_text_render(self):
        """Users can post CommonMark direct messages via HTTP form fallback and view them rendered."""
        self.client.force_login(self.user1)
        dm_url = reverse('chat:direct_message', kwargs={
            'slug': self.workspace.slug,
            'user_id': self.user2.id
        })

        # Post rich-text DM
        post_resp = self.client.post(dm_url, {
            'content': 'Hey @Bob Jones, check out [Project Board](https://aetherspace.dev/board)!'
        })
        self.assertEqual(post_resp.status_code, 302)

        # View DM
        get_resp = self.client.get(dm_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, "aether-mention")
        self.assertContains(get_resp, "href=\"https://aetherspace.dev/board\"")

    def test_unauthorized_user_cannot_access_channel_or_dm(self):
        """Non-workspace members cannot view or post to channels or direct messages."""
        self.client.force_login(self.outsider)

        # Try to view channel
        channel_url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        resp_channel = self.client.get(channel_url)
        self.assertEqual(resp_channel.status_code, 403)

        # Try to view DM
        dm_url = reverse('chat:direct_message', kwargs={
            'slug': self.workspace.slug,
            'user_id': self.user1.id
        })
        resp_dm = self.client.get(dm_url)
        self.assertEqual(resp_dm.status_code, 403)

    def test_bulleted_list_rendering_and_sanitization(self):
        """Single and multi-item bulleted lists render as <ul><li> and survive Bleach sanitization."""
        from core.templatetags.rich_text import render_rich_text

        # Single item
        html_single = str(render_rich_text("- Single item"))
        self.assertIn("<ul>", html_single)
        self.assertIn("<li>Single item</li>", html_single)
        self.assertIn("</ul>", html_single)

        # Multi-item list
        html_multi = str(render_rich_text("- Item 1\n- Item 2\n- Item 3"))
        self.assertIn("<ul>", html_multi)
        self.assertIn("<li>Item 1</li>", html_multi)
        self.assertIn("<li>Item 2</li>", html_multi)
        self.assertIn("<li>Item 3</li>", html_multi)
        self.assertIn("</ul>", html_multi)

    def test_numbered_list_rendering_and_sanitization(self):
        """Numbered lists render as <ol><li> with preserved order and survive Bleach sanitization."""
        from core.templatetags.rich_text import render_rich_text

        html_ol = str(render_rich_text("1. First step\n2. Second step\n3. Third step"))
        self.assertIn("<ol>", html_ol)
        self.assertIn("<li>First step</li>", html_ol)
        self.assertIn("<li>Second step</li>", html_ol)
        self.assertIn("<li>Third step</li>", html_ol)
        self.assertIn("</ol>", html_ol)
        # Order check
        pos1 = html_ol.index("First step")
        pos2 = html_ol.index("Second step")
        pos3 = html_ol.index("Third step")
        self.assertTrue(pos1 < pos2 < pos3)

    def test_nested_lists_normalization_and_rendering(self):
        """Nested lists serialize and render correctly with both 4-space and 2-space indentation."""
        from core.templatetags.rich_text import render_rich_text

        # 4-space nested list
        nested_4sp = "- Parent\n    - Child 1\n    - Child 2"
        html_4sp = str(render_rich_text(nested_4sp))
        self.assertIn("<ul>", html_4sp)
        self.assertIn("<li>Parent", html_4sp)
        self.assertIn("<li>Child 1</li>", html_4sp)
        self.assertIn("<li>Child 2</li>", html_4sp)

        # 2-space nested list normalized to 4 spaces
        nested_2sp = "- Parent\n  - Sub 1\n  - Sub 2"
        html_2sp = str(render_rich_text(nested_2sp))
        self.assertIn("<ul>", html_2sp)
        self.assertIn("<li>Parent", html_2sp)
        self.assertIn("<li>Sub 1</li>", html_2sp)
        self.assertIn("<li>Sub 2</li>", html_2sp)

        # Mixed ordered list with nested unordered list
        mixed_list = "1. Section One\n    - Subsection A\n    - Subsection B\n2. Section Two"
        html_mixed = str(render_rich_text(mixed_list))
        self.assertIn("<ol>", html_mixed)
        self.assertIn("<li>Section One", html_mixed)
        self.assertIn("<ul>", html_mixed)
        self.assertIn("<li>Subsection A</li>", html_mixed)
        self.assertIn("<li>Section Two</li>", html_mixed)

    def test_formatted_content_inside_list_items(self):
        """Bold, italic, inline code, link, and mention formatting survive inside list items."""
        from core.templatetags.rich_text import render_rich_text

        md = (
            "- **Sprint Goal**: Ship feature\n"
            "- *Critical*: Must test edge cases\n"
            "- Run `python manage.py test` locally\n"
            "- Reference: [Doc Link](https://aetherspace.dev/docs)\n"
            "- Assigned to @[Alice Smith](10001A)\n"
            "- ~~Deprecated task~~"
        )
        html = str(render_rich_text(md))
        self.assertIn("<strong>Sprint Goal</strong>: Ship feature", html)
        self.assertIn("<em>Critical</em>: Must test edge cases", html)
        self.assertIn("<code>python manage.py test</code>", html)
        self.assertIn('href="https://aetherspace.dev/docs"', html)
        self.assertIn('class="aether-mention', html)
        self.assertIn('@Alice Smith', html)
        self.assertIn('<del>Deprecated task</del>', html)

    def test_list_followed_by_paragraph_clean_separation(self):
        """A list immediately followed by plain text without blank line separates cleanly."""
        from core.templatetags.rich_text import render_rich_text

        md = "- Item 1\n- Item 2\nFollowing paragraph text"
        html = str(render_rich_text(md))
        self.assertIn("<ul>", html)
        self.assertIn("<li>Item 1</li>", html)
        self.assertIn("<li>Item 2</li>", html)
        self.assertIn("</ul>", html)
        self.assertIn("Following paragraph text", html)

    def test_channel_view_list_message_post_and_rendering(self):
        """Posting a list message to a channel saves properly and renders within .aether-message-content."""
        self.client.force_login(self.user1)
        channel_url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })

        list_content = "- Requirement 1\n- Requirement 2\n- Requirement 3"
        post_resp = self.client.post(channel_url, {'content': list_content})
        self.assertEqual(post_resp.status_code, 302)

        get_resp = self.client.get(channel_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, 'aether-message-content')
        self.assertContains(get_resp, '<ul>')
        self.assertContains(get_resp, '<li>Requirement 1</li>')
        self.assertContains(get_resp, '<li>Requirement 2</li>')
        self.assertContains(get_resp, '<li>Requirement 3</li>')

    def test_direct_message_list_message_post_and_rendering(self):
        """Posting a list message to direct messages saves and renders within .aether-message-content."""
        self.client.force_login(self.user1)
        dm_url = reverse('chat:direct_message', kwargs={
            'slug': self.workspace.slug,
            'user_id': self.user2.id
        })

        numbered_content = "1. Setup project\n2. Run migrations\n3. Launch devserver"
        post_resp = self.client.post(dm_url, {'content': numbered_content})
        self.assertEqual(post_resp.status_code, 302)

        get_resp = self.client.get(dm_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, 'aether-message-content')
        self.assertContains(get_resp, '<ol>')
        self.assertContains(get_resp, '<li>Setup project</li>')
        self.assertContains(get_resp, '<li>Run migrations</li>')
        self.assertContains(get_resp, '<li>Launch devserver</li>')

    def test_websocket_list_message_parity(self):
        """ChatConsumer.save_message formats bulleted and numbered lists with full parity."""
        from chat.consumers import ChatConsumer
        from core.templatetags.rich_text import render_rich_text
        from asgiref.sync import async_to_sync

        consumer = ChatConsumer()
        consumer.channel_id = str(self.channel.id)
        consumer.conversation_id = None
        consumer.user = self.user1

        text = "- Feature Alpha\n- Feature Beta\n1. First task\n2. Second task"
        result = async_to_sync(consumer.save_message)(text)

        self.assertEqual(result["content"], text)
        expected_rendered = str(render_rich_text(text))
        self.assertEqual(result["rendered_content"], expected_rendered)
        self.assertIn("<ul>", result["rendered_content"])
        self.assertIn("<li>Feature Alpha</li>", result["rendered_content"])
        self.assertIn("<ol>", result["rendered_content"])
        self.assertIn("<li>First task</li>", result["rendered_content"])

    def test_scoped_list_css_in_chat_template(self):
        """base_chat.html includes scoped list styling ensuring list markers are not suppressed by preflight."""
        self.client.force_login(self.user1)
        channel_url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        resp = self.client.get(channel_url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        self.assertIn('.aether-chat-editor ul', content)
        self.assertIn('.aether-chat-editor ol', content)
        self.assertIn('.aether-message-content ul', content)
        self.assertIn('.aether-message-content ol', content)
        self.assertIn('list-style-type: disc !important', content)
        self.assertIn('list-style-type: decimal !important', content)

    def test_emoji_insertion_and_persistence(self):
        """Emojis at beginning, middle, end, and combined with formatting remain intact throughout rendering."""
        from core.templatetags.rich_text import render_rich_text

        # 1. Beginning of message
        md1 = "🚀 Launching our new feature today!"
        html1 = str(render_rich_text(md1))
        self.assertIn("🚀 Launching our new feature today!", html1)

        # 2. Middle of message
        md2 = "Great work team ❤️ keep it going"
        html2 = str(render_rich_text(md2))
        self.assertIn("Great work team ❤️ keep it going", html2)

        # 3. End of message
        md3 = "Everything is deployed and tested ✅"
        html3 = str(render_rich_text(md3))
        self.assertIn("Everything is deployed and tested ✅", html3)

        # 4. Combined with bold and lists
        md4 = "- **Feature:** Auth system 🔒\n- **Status:** In progress ⏳\n- **Reviewer:** Approved 👍"
        html4 = str(render_rich_text(md4))
        self.assertIn("🔒", html4)
        self.assertIn("⏳", html4)
        self.assertIn("👍", html4)
        self.assertIn("<strong>Feature:</strong>", html4)

    def test_inline_code_rendering_and_escaping(self):
        """Inline code preserves literal characters and never interprets mentions or HTML."""
        from core.templatetags.rich_text import render_rich_text

        # Literal code characters <, >, &, *, _
        md = "Run `def check(a < 5 && b > 2): return a * b_val` in the console."
        html = str(render_rich_text(md))
        self.assertIn("<code>", html)
        self.assertIn("def check(a &lt; 5 &amp;&amp; b &gt; 2): return a * b_val", html)

        # Mentions inside inline code must remain literal text, NOT become mention pills
        md_mention = "Use the `@login_required` decorator on your view function."
        html_mention = str(render_rich_text(md_mention))
        self.assertIn("<code>@login_required</code>", html_mention)
        self.assertNotIn("aether-mention", html_mention)

    def test_inline_code_embedded_backticks(self):
        """Inline code with embedded backticks serializes and renders using multi-backtick spans."""
        from core.templatetags.rich_text import render_rich_text

        md = "Use ``foo`bar`` or `code` here."
        html = str(render_rich_text(md))
        self.assertIn("<code>foo`bar</code>", html)
        self.assertIn("<code>code</code>", html)

    def test_code_block_multiline_and_indentation(self):
        """Code blocks preserve line breaks, 4-space indentation, and monospace formatting."""
        from core.templatetags.rich_text import render_rich_text

        md = (
            "```python\n"
            "def calculate_total(items):\n"
            "    total = 0\n"
            "    for item in items:\n"
            "        total += item.price\n"
            "    return total\n"
            "```"
        )
        html = str(render_rich_text(md))
        self.assertIn("<pre>", html)
        self.assertIn("<code", html)
        self.assertIn("def calculate_total(items):", html)
        self.assertIn("    total = 0", html)
        self.assertIn("        total += item.price", html)
        self.assertIn("</code></pre>", html)

    def test_code_block_prevents_mentions_and_xss(self):
        """Code blocks safely escape HTML/script tags and do not convert @annotations to mention pills."""
        from core.templatetags.rich_text import render_rich_text

        md = (
            "```javascript\n"
            "@api_view(['POST'])\n"
            "const el = '<script>alert(\"xss\")</script>';\n"
            "```"
        )
        html = str(render_rich_text(md))
        self.assertIn("<pre>", html)
        self.assertIn("<code", html)
        self.assertIn("@api_view(['POST'])", html)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("aether-mention", html)

    def test_code_block_variable_backtick_fence(self):
        """Code block containing 3 backticks does not prematurely terminate when fenced with 4 backticks."""
        from core.templatetags.rich_text import render_rich_text

        md = (
            "````markdown\n"
            "Here is how to write a code block in markdown:\n"
            "```\n"
            "print('hello')\n"
            "```\n"
            "````"
        )
        html = str(render_rich_text(md))
        self.assertIn("<pre>", html)
        self.assertIn("<code", html)
        self.assertIn("print('hello')", html)

    def test_channel_view_code_and_emoji_lifecycle(self):
        """Posting a message with emojis, inline code, and code block persists and renders on refresh."""
        self.client.force_login(self.user1)
        channel_url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })

        content = (
            "Deployment status: 🚀 SUCCESS!\n\n"
            "Run `python manage.py check` before deploying.\n\n"
            "```python\n"
            "def test_app():\n"
            "    assert True\n"
            "```"
        )
        post_resp = self.client.post(channel_url, {'content': content})
        self.assertEqual(post_resp.status_code, 302)

        get_resp = self.client.get(channel_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, '🚀 SUCCESS!')
        self.assertContains(get_resp, '<code>python manage.py check</code>')
        self.assertContains(get_resp, '<pre>')
        self.assertContains(get_resp, 'def test_app():')

    def test_direct_message_code_and_emoji_lifecycle(self):
        """Posting a DM with emojis, inline code, and code block persists across page refresh."""
        self.client.force_login(self.user1)
        dm_url = reverse('chat:direct_message', kwargs={
            'slug': self.workspace.slug,
            'user_id': self.user2.id
        })

        dm_content = (
            "Hi team 👋 here is the patch:\n\n"
            "Check `config.py`:\n"
            "```python\n"
            "DEBUG = False\n"
            "```\n"
            "LGTM! 🎉"
        )
        post_resp = self.client.post(dm_url, {'content': dm_content})
        self.assertEqual(post_resp.status_code, 302)

        get_resp = self.client.get(dm_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, 'Hi team 👋 here is the patch:')
        self.assertContains(get_resp, '<code>config.py</code>')
        self.assertContains(get_resp, '<pre>')
        self.assertContains(get_resp, 'DEBUG = False')
        self.assertContains(get_resp, 'LGTM! 🎉')

    def test_websocket_code_and_emoji_parity(self):
        """WebSocket save_message delivers emojis, inline code, and code blocks with full HTTP parity."""
        from chat.consumers import ChatConsumer
        from core.templatetags.rich_text import render_rich_text
        from asgiref.sync import async_to_sync

        consumer = ChatConsumer()
        consumer.channel_id = str(self.channel.id)
        consumer.conversation_id = None
        consumer.user = self.user1

        text = (
            "Build update 🛠️:\n"
            "Install with `pip install -r requirements.txt`.\n\n"
            "```bash\n"
            "npm run build\n"
            "```"
        )
        result = async_to_sync(consumer.save_message)(text)

        self.assertEqual(result["content"], text)
        expected_rendered = str(render_rich_text(text))
        self.assertEqual(result["rendered_content"], expected_rendered)
        self.assertIn("🛠️", result["rendered_content"])
        self.assertIn("<code>pip install -r requirements.txt</code>", result["rendered_content"])
        self.assertIn("<pre>", result["rendered_content"])
        self.assertIn("npm run build", result["rendered_content"])

    def test_scoped_code_css_in_chat_template(self):
        """base_chat.html includes scoped code and pre styling ensuring proper monospace and dark pre block."""
        self.client.force_login(self.user1)
        channel_url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        resp = self.client.get(channel_url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        self.assertIn('.aether-chat-editor code', content)
        self.assertIn('.aether-message-content code', content)
        self.assertIn('.aether-chat-editor pre', content)
        self.assertIn('.aether-message-content pre', content)
        self.assertIn('overflow-x: auto !important', content)
        self.assertIn('white-space: pre !important', content)

    def test_hyperlink_rendering_and_safety(self):
        """Hyperlinks render with accessible styling, target=_blank, and unsafe schemes are blocked."""
        from core.templatetags.rich_text import render_rich_text

        # 1. Valid https link
        md_https = "Check out [Aether Documentation](https://docs.aetherspace.dev/intro/)."
        html_https = str(render_rich_text(md_https))
        self.assertIn('<a target="_blank" rel="noopener noreferrer" href="https://docs.aetherspace.dev/intro/">Aether Documentation</a>', html_https)

        # 2. Valid mailto link
        md_mail = "Contact us at [Support](mailto:support@aetherspace.dev)."
        html_mail = str(render_rich_text(md_mail))
        self.assertIn('<a target="_blank" rel="noopener noreferrer" href="mailto:support@aetherspace.dev">Support</a>', html_mail)

        # 3. Dangerous javascript: scheme blocked by bleach
        md_bad = "Click [Free Prize](javascript:alert('pwned'))"
        html_bad = str(render_rich_text(md_bad))
        self.assertNotIn('href="javascript:', html_bad)
        self.assertNotIn("alert('pwned')", html_bad)

        # 4. Dangerous data: scheme blocked by bleach
        md_data = "Click [Payload](data:text/html,<script>alert(1)</script>)"
        html_data = str(render_rich_text(md_data))
        self.assertNotIn('href="data:', html_data)
        self.assertNotIn('<script>', html_data)

        # 5. Long URL wrapping
        long_url = "https://example.com/" + "verylongpath/" * 10
        md_long = f"Visit [Long Link]({long_url})"
        html_long = str(render_rich_text(md_long))
        self.assertIn(long_url, html_long)

    def test_emoji_multi_column_grid_and_tabs(self):
        """Emoji picker markup includes responsive multi-column grid classes, accessible tabs, and button sizing."""
        self.client.force_login(self.user1)
        channel_url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        resp = self.client.get(channel_url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        self.assertIn('aether-emoji-picker', content)
        self.assertIn('aether-emoji-header', content)
        self.assertIn('aether-emoji-grid', content)
        self.assertIn('aether-emoji-btn', content)
        self.assertIn('role="tablist"', content)
        self.assertIn('role="grid"', content)
        self.assertIn('role="gridcell"', content)

    def test_mention_pill_rendering_and_code_isolation(self):
        """Mentions render as distinct pills with data attributes, and are never converted inside code."""
        from core.templatetags.rich_text import render_rich_text

        # 1. Complex mention: @[Full Name](UUID)
        user_uuid = str(self.user2.id)
        md_complex = f"Hey @[Bob Member]({user_uuid}), please review this."
        html_complex = str(render_rich_text(md_complex))
        self.assertIn('class="aether-mention', html_complex)
        self.assertIn(f'data-user-id="{user_uuid}"', html_complex)
        self.assertIn('data-user-name="Bob Member"', html_complex)
        self.assertIn('@Bob Member', html_complex)

        # 2. Contributor ID mention: @76044C
        md_cid = "Assigned to @76044C for QA verification."
        html_cid = str(render_rich_text(md_cid))
        self.assertIn('class="aether-mention font-mono font-bold', html_cid)
        self.assertIn('data-contributor-id="76044C"', html_cid)
        self.assertIn('@76044C', html_cid)

        # 3. Isolation: mention inside inline code must NOT be converted
        md_inline_code = "Use the `@classmethod` or `@property` decorator."
        html_inline_code = str(render_rich_text(md_inline_code))
        self.assertIn('<code>@classmethod</code>', html_inline_code)
        self.assertIn('<code>@property</code>', html_inline_code)
        self.assertNotIn('aether-mention', html_inline_code)

        # 4. Isolation: mention inside code block must NOT be converted
        md_code_block = (
            "```python\n"
            "@login_required\n"
            "def secure_view(request):\n"
            "    return True\n"
            "```"
        )
        html_code_block = str(render_rich_text(md_code_block))
        self.assertIn('@login_required', html_code_block)
        self.assertNotIn('aether-mention', html_code_block)

    def test_scoped_chat_css_links_emojis_mentions(self):
        """base_chat.html includes scoped CSS for links, emoji 8-column grid, and high-contrast mention pills."""
        self.client.force_login(self.user1)
        channel_url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        resp = self.client.get(channel_url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Link styling
        self.assertIn('.aether-chat-editor a', content)
        self.assertIn('.aether-message-content a', content)
        self.assertIn('text-decoration: underline !important', content)
        self.assertIn('word-break: break-all !important', content)

        # Emoji grid styling
        self.assertIn('.aether-emoji-grid', content)
        self.assertIn('grid-template-columns: repeat(8, minmax(0, 1fr)) !important', content)
        self.assertIn('.aether-emoji-btn', content)

        # Mention pill styling
        self.assertIn('.aether-mention', content)
        self.assertIn('border-radius: 9999px !important', content)


class ChatHomeRedesignAndIdentityTests(TestCase):
    """
    Automated verification of Chat Home Redesign & Identity Enhancements:
    1. Hero banner: "Team Chat & Collaboration", "Create Channel", "Start Direct Message", workspace pill
    2. Real metrics cards: Total Channels, Workspace Members, Unread Messages, Mentions
    3. Quick Actions panel: 4 functional cards (Create Channel, Direct Message, Pinned Assets, Shared Files)
    4. Mandatory removal of Recent Mentions panel (confirm no 'Recent Mentions' or empty state in DOM)
    5. Mentions system preservation: user mentions still trigger notifications and mention count works
    6. Recent Channel Activity: only shows accessible channel messages, never leaks private channels
    7. Channel Identity: built-in icon selection, image upload (2MB limit, format validation), default fallback
    8. Workspace Identity: built-in icon selection, logo handling, RBAC permissions
    """

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email='admin.id@aetherspace.dev',
            password='AdminPassword123!',
            full_name='Admin Identity',
            approval_status='APPROVED'
        )
        self.contributor = User.objects.create_user(
            email='contrib.id@aetherspace.dev',
            password='ContribPassword123!',
            full_name='Contrib Identity',
            approval_status='APPROVED'
        )
        self.outsider = User.objects.create_user(
            email='outsider.id@aetherspace.dev',
            password='OutsiderPassword123!',
            full_name='Outsider User',
            approval_status='APPROVED'
        )
        self.workspace = Workspace.objects.create(
            name='AetherSpace Core',
            slug='aetherspace-core-id',
            owner=self.admin
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        ensure_default_channels(self.workspace, creator=self.admin)
        self.general = Channel.objects.get(workspace=self.workspace, slug='general')

    def test_chat_home_hero_banner_and_quick_actions(self):
        """Chat Home renders the approved hero banner, workspace name, and 4 quick actions."""
        self.client.force_login(self.admin)
        url = reverse('chat:chat_home', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # Hero Banner
        self.assertContains(resp, "Team Chat & Collaboration")
        self.assertContains(resp, "Connect, collaborate, and coordinate with your team")
        self.assertContains(resp, self.workspace.name)
        self.assertContains(resp, "Create Channel")
        self.assertContains(resp, "Start Direct Message")

        # Quick Actions
        self.assertContains(resp, "Quick Actions")
        self.assertContains(resp, "Direct Message")
        self.assertContains(resp, "Pinned Assets")
        self.assertContains(resp, "Shared Files")

    def test_recent_mentions_section_is_completely_absent(self):
        """Recent Mentions panel, cards, and empty state are completely absent from Chat Home."""
        self.client.force_login(self.contributor)
        url = reverse('chat:chat_home', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # Ensure the entire Recent Mentions panel is removed
        self.assertNotContains(resp, "Recent Mentions")
        self.assertNotContains(resp, "No recent mentions found")
        self.assertNotContains(resp, "You haven't been mentioned in any channel or conversation yet.")

    def test_metrics_cards_display_real_data(self):
        """Statistics cards display real authorized counts for channels, members, unread, and mentions."""
        # Enroll contributor in general channel with past last_read_at
        ChannelMembership.objects.create(
            channel=self.general,
            user=self.contributor,
            last_read_at=timezone.now() - timezone.timedelta(days=1)
        )

        # Post a message that mentions contributor
        post_channel_message(self.general, self.admin, content="Hello @contrib.id please check this")

        self.client.force_login(self.contributor)
        url = reverse('chat:chat_home', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # Context counts
        self.assertEqual(resp.context['total_channels'], 2)  # #general and #project-updates
        self.assertEqual(resp.context['total_members'], 2)  # admin and contributor
        self.assertEqual(resp.context['unread_messages_count'], 1)  # 1 unread message in #general
        self.assertEqual(resp.context['mentions_count'], 1)  # 1 mention

        # DOM rendered labels
        self.assertContains(resp, "Total Channels")
        self.assertContains(resp, "Workspace Members")
        self.assertContains(resp, "Unread Messages")
        self.assertContains(resp, "Mentions")

    def test_recent_channel_activity_respects_permissions_and_ordering(self):
        """Recent Channel Activity displays public channel messages and excludes private channels for non-members."""
        # 1. Message in public channel
        post_channel_message(self.general, self.admin, content="Public announcement for all team members")

        # 2. Private channel created by admin
        secret_ch = Channel.objects.create(
            workspace=self.workspace,
            name='leadership-confidential',
            slug='leadership-confidential',
            is_private=True,
            created_by=self.admin
        )
        post_channel_message(secret_ch, self.admin, content="Top secret executive discussion")

        # Contributor views Chat Home
        self.client.force_login(self.contributor)
        url = reverse('chat:chat_home', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # Public message is visible in activity
        self.assertContains(resp, "Public announcement for all team members")
        self.assertContains(resp, "#general")

        # Private message is strictly hidden from non-member contributor
        self.assertNotContains(resp, "Top secret executive discussion")
        self.assertNotContains(resp, "#leadership-confidential")

    def test_channel_identity_curated_icon_selection(self):
        """Channel supports selecting a curated icon and rendering it via identity_badge."""
        from chat.services import process_and_save_channel_avatar
        ch = Channel.objects.create(
            workspace=self.workspace,
            name='dev-ops',
            slug='dev-ops',
            created_by=self.admin
        )
        self.assertEqual(ch.identity_type, 'default')

        # Select curated icon 'rocket'
        success, msg = process_and_save_channel_avatar(ch, icon_key='rocket')
        self.assertTrue(success)
        ch.refresh_from_db()
        self.assertEqual(ch.icon, 'rocket')
        self.assertEqual(ch.icon_name, 'rocket')
        self.assertEqual(ch.identity_type, 'icon')

        # Test view rendering with identity_badge
        self.client.force_login(self.admin)
        url = reverse('chat:channel_view', kwargs={'slug': self.workspace.slug, 'channel_slug': ch.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-icon="rocket"')

    def test_channel_identity_image_upload_and_validation(self):
        """Channel avatar upload enforces 2MB size limit and valid image formats."""
        from chat.services import process_and_save_channel_avatar
        ch = Channel.objects.create(
            workspace=self.workspace,
            name='design-systems',
            slug='design-systems',
            created_by=self.admin
        )

        # 1. Invalid file extension rejected
        bad_file = SimpleUploadedFile("payload.exe", b"malicious binary executable content", content_type="application/octet-stream")
        success, msg = process_and_save_channel_avatar(ch, file_obj=bad_file)
        self.assertFalse(success)
        self.assertIn("Unsupported file format", msg)

        # 2. Oversized file (>2MB) rejected
        big_bytes = b"x" * (2 * 1024 * 1024 + 500)
        big_file = SimpleUploadedFile("massive_image.png", big_bytes, content_type="image/png")
        success, msg = process_and_save_channel_avatar(ch, file_obj=big_file)
        self.assertFalse(success)
        self.assertIn("exceeds the maximum allowed limit of 2 MB", msg)

        # 3. SVG with script tag rejected
        malicious_svg = SimpleUploadedFile("vector.svg", b'<svg><script>alert("xss")</script></svg>', content_type="image/svg+xml")
        success, msg = process_and_save_channel_avatar(ch, file_obj=malicious_svg)
        self.assertFalse(success)
        self.assertIn("SVG files containing scripts are rejected", msg)

        # 4. Valid tiny PNG accepted
        import io
        from PIL import Image as PilImage
        img_io = io.BytesIO()
        PilImage.new('RGBA', (64, 64), color=(0, 120, 255, 255)).save(img_io, format='PNG')
        img_io.seek(0)
        valid_png = SimpleUploadedFile("logo.png", img_io.read(), content_type="image/png")
        success, msg = process_and_save_channel_avatar(ch, file_obj=valid_png)
        self.assertTrue(success)
        ch.refresh_from_db()
        self.assertTrue(bool(ch.avatar))
        self.assertEqual(ch.identity_type, 'image')

        # 5. Remove avatar restores default
        success, msg = process_and_save_channel_avatar(ch, remove_avatar=True)
        self.assertTrue(success)
        ch.refresh_from_db()
        self.assertEqual(ch.avatar, '')
        self.assertEqual(ch.identity_type, 'default')

    def test_workspace_identity_curated_icon_and_rbac(self):
        """Workspace supports curated icon selection and restricts settings to admin/owner."""
        from workspaces.services import process_and_save_workspace_logo
        # 1. Admin sets curated icon 'terminal'
        success, msg = process_and_save_workspace_logo(self.workspace, icon_key='terminal')
        self.assertTrue(success)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.icon_name, 'terminal')
        self.assertEqual(self.workspace.identity_type, 'icon')

        # 2. Contributor cannot modify workspace settings (RBAC 403)
        self.client.force_login(self.contributor)
        settings_url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(settings_url, {'name': 'Hacked Workspace', 'selected_icon': 'bug'})
        self.assertEqual(resp.status_code, 403)

    def test_export_rendered_chat_home_for_visual_capture(self):
        """Populate rich data matching mockup and export rendered HTML for Playwright screenshot capture."""
        # Provision channels matching mockup
        design_ch = Channel.objects.create(workspace=self.workspace, name='design', slug='design', created_by=self.admin)
        dev_ch = Channel.objects.create(workspace=self.workspace, name='development', slug='development', created_by=self.admin)
        random_ch = Channel.objects.create(workspace=self.workspace, name='random', slug='random', created_by=self.admin)

        # Provision additional members to match mockup
        for i in range(10):
            u = User.objects.create_user(
                email=f'member{i}@aetherspace.dev',
                password='Password123!',
                full_name=f'Team Member {i+1}',
                approval_status='APPROVED'
            )
            WorkspaceMembership.objects.create(workspace=self.workspace, user=u, role=WorkspaceRole.CONTRIBUTOR, status=MembershipStatus.ACTIVE)

        # Create realistic channel activity
        post_channel_message(self.general, self.admin, content="Hi @contributor please find out the attachment")
        post_channel_message(self.general, self.contributor, content="let's sync tomorrow on this")
        post_channel_message(design_ch, self.admin, content="Shared a file: design-mockup.png")
        post_channel_message(dev_ch, self.contributor, content="Pushed new changes to the repository")

        self.client.force_login(self.admin)
        url = reverse('chat:chat_home', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        html = resp.content.decode('utf-8')
        # Inject absolute file URI for static CSS so browser can load styles offline
        import os
        css_path = os.path.abspath('static/css/dist/styles.css').replace('\\', '/')
        html = html.replace('/static/css/dist/styles.css', f'file:///{css_path}')

        out_path = r"C:\Users\M.Yaswanth\.gemini\antigravity-ide\brain\535e0b22-5b14-4eef-aa57-2b2ed1427168\chat_home_mockup.html"
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)
        self.assertTrue(os.path.exists(out_path))


class IdentityIconPersistenceAndSecurityTests(TestCase):
    """
    Automated verification of Visual Identity Persistence and Security Requirements:
    1. Valid built-in channel icon is persisted and preserved across reloads.
    2. Valid built-in workspace icon is persisted and preserved across reloads.
    3. Invalid icon identifiers are rejected safely without corrupting records.
    4. Unauthorized users cannot modify workspace identity (RBAC 403).
    5. Unauthorized users cannot modify channel identity (RBAC 403).
    6. Default reset restores default initials/emblem for channels and workspaces.
    7. Existing uploaded image identities remain fully functional.
    8. Saved icon identifiers are interpreted correctly by models and rendering helpers.
    """

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email='admin.identity@aetherspace.dev',
            password='AdminPassword123!',
            full_name='Admin Identity User',
            approval_status='APPROVED'
        )
        self.contributor = User.objects.create_user(
            email='contrib.identity@aetherspace.dev',
            password='ContribPassword123!',
            full_name='Contrib Identity User',
            approval_status='APPROVED'
        )
        self.workspace = Workspace.objects.create(
            name='AetherSpace Identity Team',
            slug='aetherspace-identity-team',
            owner=self.admin
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        ensure_default_channels(self.workspace, creator=self.admin)
        self.channel = Channel.objects.create(
            workspace=self.workspace,
            name='mobile-app',
            slug='mobile-app',
            created_by=self.admin
        )
        ChannelMembership.objects.create(
            channel=self.channel,
            user=self.admin,
            role=ChannelRole.OWNER
        )
        ChannelMembership.objects.create(
            channel=self.channel,
            user=self.contributor,
            role=ChannelRole.MEMBER
        )

    def test_1_valid_builtin_channel_icon_persisted_and_reloaded(self):
        """Selecting and saving a built-in channel icon persists and remains visible on reload."""
        self.client.force_login(self.admin)
        details_url = reverse('chat:channel_details', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })

        # Submit icon selection form
        resp = self.client.post(details_url, {
            'action': 'update_identity',
            'selected_icon': 'rocket',
            'remove_avatar': '0',
        })
        self.assertEqual(resp.status_code, 302)

        # Confirm database persistence
        self.channel.refresh_from_db()
        self.assertEqual(self.channel.icon, 'rocket')
        self.assertEqual(self.channel.icon_name, 'rocket')
        self.assertEqual(self.channel.identity_type, 'icon')
        self.assertEqual(self.channel.avatar, '')

        # Full page reload verification
        reload_resp = self.client.get(details_url)
        self.assertEqual(reload_resp.status_code, 200)
        self.assertContains(reload_resp, 'data-icon="rocket"')
        self.assertIn("selectedIcon: 'rocket'", reload_resp.content.decode('utf-8'))

        # Channel chat view renders the rocket icon badge
        view_url = reverse('chat:channel_view', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        view_resp = self.client.get(view_url)
        self.assertEqual(view_resp.status_code, 200)
        self.assertContains(view_resp, 'data-icon="rocket"')

    def test_2_valid_builtin_workspace_icon_persisted_and_reloaded(self):
        """Saving a built-in workspace icon persists icon:<name> and renders in sidebar and dashboard."""
        self.client.force_login(self.admin)
        settings_url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})

        # Save workspace settings with selected icon
        resp = self.client.post(settings_url, {
            'name': self.workspace.name,
            'description': self.workspace.description or '',
            'status': self.workspace.status,
            'max_seats': 15,
            'storage_quota_mb': 50,
            'selected_icon': 'sparkles',
            'remove_logo': '0',
        })
        self.assertEqual(resp.status_code, 302)

        # Confirm database persistence
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.logo, 'icon:sparkles')
        self.assertEqual(self.workspace.icon_name, 'sparkles')
        self.assertEqual(self.workspace.identity_type, 'icon')
        self.assertEqual(self.workspace.logo_url, '')

        # Full page reload of settings
        reload_resp = self.client.get(settings_url)
        self.assertEqual(reload_resp.status_code, 200)
        self.assertIn("selectedIcon: 'sparkles'", reload_resp.content.decode('utf-8'))

        # Workspace dashboard renders with sparkles badge
        dash_url = reverse('workspaces:workspace_dashboard', kwargs={'slug': self.workspace.slug})
        dash_resp = self.client.get(dash_url)
        self.assertEqual(dash_resp.status_code, 200)
        self.assertContains(dash_resp, 'data-icon="sparkles"')

    def test_3_invalid_icon_identifiers_rejected_safely(self):
        """Invalid icon identifiers are rejected safely with an error and without corrupting DB."""
        self.client.force_login(self.admin)

        # 1. Channel invalid icon
        details_url = reverse('chat:channel_details', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        resp = self.client.post(details_url, {
            'action': 'update_identity',
            'selected_icon': 'malicious_injection_icon',
            'remove_avatar': '0',
        })
        # Should re-render with error, NOT redirect to success
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid icon identifier")
        self.channel.refresh_from_db()
        self.assertNotEqual(self.channel.icon, 'malicious_injection_icon')

        # 2. Workspace invalid icon
        settings_url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})
        ws_resp = self.client.post(settings_url, {
            'name': self.workspace.name,
            'description': self.workspace.description or '',
            'status': self.workspace.status,
            'max_seats': 15,
            'storage_quota_mb': 50,
            'selected_icon': 'invalid_exploit_icon',
            'remove_logo': '0',
        })
        self.assertEqual(ws_resp.status_code, 200)
        self.assertContains(ws_resp, "Invalid icon identifier")
        self.workspace.refresh_from_db()
        self.assertNotEqual(self.workspace.logo, 'icon:invalid_exploit_icon')

    def test_4_unauthorized_user_cannot_modify_workspace_identity(self):
        """Contributors cannot modify workspace settings or identity (RBAC 403)."""
        self.client.force_login(self.contributor)
        settings_url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(settings_url, {
            'name': 'Hacked Name',
            'selected_icon': 'bug',
        })
        self.assertEqual(resp.status_code, 403)
        self.workspace.refresh_from_db()
        self.assertNotEqual(self.workspace.icon_name, 'bug')

    def test_5_unauthorized_user_cannot_modify_channel_identity(self):
        """Channel members without admin/owner rights cannot modify channel identity (RBAC 403)."""
        self.client.force_login(self.contributor)
        details_url = reverse('chat:channel_details', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        resp = self.client.post(details_url, {
            'action': 'update_identity',
            'selected_icon': 'bulb',
            'remove_avatar': '0',
        })
        self.assertEqual(resp.status_code, 403)
        self.channel.refresh_from_db()
        self.assertNotEqual(self.channel.icon, 'bulb')

    def test_6_default_reset_still_works(self):
        """Submitting default reset restores default initials/emblem for channels and workspaces."""
        self.client.force_login(self.admin)

        # 1. Set channel to rocket, then reset to default
        self.channel.icon = 'rocket'
        self.channel.save()
        details_url = reverse('chat:channel_details', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        resp = self.client.post(details_url, {
            'action': 'update_identity',
            'selected_icon': '',
            'remove_avatar': '1',
        })
        self.assertEqual(resp.status_code, 302)
        self.channel.refresh_from_db()
        self.assertEqual(self.channel.icon, '')
        self.assertEqual(self.channel.avatar, '')
        self.assertEqual(self.channel.identity_type, 'default')

        # 2. Set workspace to icon:briefcase, then reset to default
        self.workspace.logo = 'icon:briefcase'
        self.workspace.save()
        settings_url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})
        ws_resp = self.client.post(settings_url, {
            'name': self.workspace.name,
            'description': self.workspace.description or '',
            'status': self.workspace.status,
            'max_seats': 15,
            'storage_quota_mb': 50,
            'selected_icon': '',
            'remove_logo': '1',
        })
        self.assertEqual(ws_resp.status_code, 302)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.logo, '')
        self.assertEqual(self.workspace.identity_type, 'default')

    def test_7_existing_uploaded_image_identities_remain_functional(self):
        """Custom image upload remains fully functional for channels and workspaces."""
        import io
        from PIL import Image as PilImage
        from django.core.files.uploadedfile import SimpleUploadedFile

        img_io = io.BytesIO()
        PilImage.new('RGBA', (64, 64), color=(37, 99, 235, 255)).save(img_io, format='PNG')
        img_io.seek(0)
        img_file = SimpleUploadedFile("brand_avatar.png", img_io.read(), content_type="image/png")

        self.client.force_login(self.admin)
        details_url = reverse('chat:channel_details', kwargs={
            'slug': self.workspace.slug,
            'channel_slug': self.channel.slug
        })
        resp = self.client.post(details_url, {
            'action': 'update_identity',
            'avatar_file': img_file,
            'remove_avatar': '0',
        })
        self.assertEqual(resp.status_code, 302)
        self.channel.refresh_from_db()
        self.assertTrue(bool(self.channel.avatar))
        self.assertEqual(self.channel.icon, '')
        self.assertEqual(self.channel.identity_type, 'image')

        # Reloading page renders img element
        reload_resp = self.client.get(details_url)
        self.assertContains(reload_resp, self.channel.avatar_url)

    def test_8_saved_icon_identifiers_interpreted_correctly_by_rendering_helpers(self):
        """All 14 curated icons render properly without error and output correct data-icon attributes."""
        from django.template import Context, Template

        supported_icons = [
            'hash', 'terminal', 'rocket', 'sparkles', 'megaphone', 'chat',
            'briefcase', 'bulb', 'bug', 'folder', 'lock', 'globe', 'shield', 'cube'
        ]

        for icon_key in supported_icons:
            # Channel test
            self.channel.icon = icon_key
            self.channel.avatar = ''
            self.assertEqual(self.channel.icon_name, icon_key)
            self.assertEqual(self.channel.identity_type, 'icon')

            tmpl = Template("{% include 'components/identity_badge.html' with entity=channel is_channel=True %}")
            rendered = tmpl.render(Context({'channel': self.channel}))
            self.assertIn(f'data-icon="{icon_key}"', rendered)

            # Workspace test
            self.workspace.logo = f"icon:{icon_key}"
            self.assertEqual(self.workspace.icon_name, icon_key)
            self.assertEqual(self.workspace.identity_type, 'icon')
            self.assertEqual(self.workspace.logo_url, '')

            ws_tmpl = Template("{% include 'components/identity_badge.html' with entity=workspace %}")
            ws_rendered = ws_tmpl.render(Context({'workspace': self.workspace}))
            self.assertIn(f'data-icon="{icon_key}"', ws_rendered)






