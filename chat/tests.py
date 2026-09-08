import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

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
            full_name='Admin User'
        )

        # Manager user
        self.manager = User.objects.create_user(
            email='manager@aetherspace.dev',
            password='ManagerPassword123!',
            full_name='Manager User'
        )

        # Contributor user
        self.contributor = User.objects.create_user(
            email='dev@aetherspace.dev',
            password='DevPassword123!',
            full_name='Dev Contributor'
        )

        # Second Contributor
        self.contributor2 = User.objects.create_user(
            email='designer@aetherspace.dev',
            password='DesignerPassword123!',
            full_name='Designer Contributor'
        )

        # Outsider user (belongs to a different workspace)
        self.outsider = User.objects.create_user(
            email='outsider@external.dev',
            password='OutsiderPassword123!',
            full_name='Outsider User'
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
