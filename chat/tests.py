import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

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
