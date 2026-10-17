import json
import time
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from channels.testing import WebsocketCommunicator
from aetherspace.asgi import application
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from accounts.models import UserProfile
from django.template.loader import render_to_string

User = get_user_model()


class PresenceSynchronizationTests(TestCase):
    """
    Test suite for AetherSpace truthful online presence and Channels synchronization:
    - Truthful availability_status (no hardcoded defaults)
    - Heartbeat cache verification and 300s expiration
    - WebSocket connect / disconnect presence transitions
    - Multi-tab/multi-session resilience (no false offline on single-tab close)
    - Workspace isolation of presence events
    - Standardized member card rendering
    """

    def setUp(self):
        cache.clear()
        self.user1 = User.objects.create_user(
            username="user1@example.com",
            email="user1@example.com",
            password="Password123!",
            first_name="Alice",
            last_name="Smith"
        )
        self.user2 = User.objects.create_user(
            username="user2@example.com",
            email="user2@example.com",
            password="Password123!",
            first_name="Bob",
            last_name="Jones"
        )
        self.user3 = User.objects.create_user(
            username="user3@example.com",
            email="user3@example.com",
            password="Password123!",
            first_name="Charlie",
            last_name="Brown"
        )

        self.workspace1 = Workspace.objects.create(
            name="Alpha Team",
            slug="alpha-team",
            owner=self.user1
        )
        self.workspace2 = Workspace.objects.create(
            name="Beta Team",
            slug="beta-team",
            owner=self.user3
        )

        self.prof1 = UserProfile.objects.create(user=self.user1)
        self.prof2 = UserProfile.objects.create(user=self.user2)
        self.prof3 = UserProfile.objects.create(user=self.user3)
        self.user1.profile = self.prof1
        self.user2.profile = self.prof2
        self.user3.profile = self.prof3

        self.mem1 = WorkspaceMembership.objects.create(
            workspace=self.workspace1,
            user=self.user1,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        self.mem2 = WorkspaceMembership.objects.create(
            workspace=self.workspace1,
            user=self.user2,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        self.mem3 = WorkspaceMembership.objects.create(
            workspace=self.workspace2,
            user=self.user3,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    def tearDown(self):
        cache.clear()

    def test_disconnected_user_shows_offline(self):
        """User without active cache heartbeat is always reported as offline."""
        self.assertEqual(self.user1.availability_status, 'offline')
        self.assertEqual(self.user2.availability_status, 'offline')

    def test_connected_user_with_heartbeat_shows_available(self):
        """When heartbeat signal is in cache, user status reflects their preference."""
        cache.set(f"user_last_seen_{self.user1.id}", timezone.now().timestamp(), 300)
        self.assertEqual(self.user1.availability_status, 'available')

    def test_custom_preference_respected_when_online(self):
        """Custom preference (e.g. away, busy, dnd) is respected only while online."""
        profile, _ = UserProfile.objects.get_or_create(user=self.user1)
        profile.preferences = {'status': 'busy'}
        profile.save()
        self.user1.profile = profile

        # Offline without heartbeat
        self.assertEqual(self.user1.availability_status, 'offline')

        # Online with heartbeat
        cache.set(f"user_last_seen_{self.user1.id}", timezone.now().timestamp(), 300)
        self.assertEqual(self.user1.availability_status, 'busy')

    def test_manual_offline_preference_always_offline(self):
        """If user manually set their preference to offline, they appear offline even with heartbeat."""
        profile, _ = UserProfile.objects.get_or_create(user=self.user1)
        profile.preferences = {'status': 'offline'}
        profile.save()
        self.user1.profile = profile

        cache.set(f"user_last_seen_{self.user1.id}", timezone.now().timestamp(), 300)
        self.assertEqual(self.user1.availability_status, 'offline')

    def test_presence_expiry_after_interval(self):
        """After cache heartbeat expires (key deleted or absent), status reverts to offline."""
        cache.set(f"user_last_seen_{self.user1.id}", timezone.now().timestamp(), 300)
        self.assertEqual(self.user1.availability_status, 'available')

        # Simulate expiration
        cache.delete(f"user_last_seen_{self.user1.id}")
        self.assertEqual(self.user1.availability_status, 'offline')

    async def test_websocket_connect_and_disconnect_broadcast(self):
        """
        Connecting to /ws/calls/global/ marks user online, increments active sockets,
        and broadcasts presence to workspace peers. Disconnecting marks user offline.
        """
        # User 2 connects first (as peer observer)
        comm2 = WebsocketCommunicator(application, "/ws/calls/global/")
        comm2.scope["user"] = self.user2
        connected2, _ = await comm2.connect()
        self.assertTrue(connected2)

        # User 1 connects (triggers presence_broadcast to workspace1)
        comm1 = WebsocketCommunicator(application, "/ws/calls/global/")
        comm1.scope["user"] = self.user1
        connected1, _ = await comm1.connect()
        self.assertTrue(connected1)

        # Check cache state for User 1
        active_sockets1 = cache.get(f"user_active_sockets_{self.user1.id}")
        self.assertEqual(active_sockets1, 1)
        last_seen1 = cache.get(f"user_last_seen_{self.user1.id}")
        self.assertIsNotNone(last_seen1)
        self.assertEqual(self.user1.availability_status, 'available')

        # User 2 should receive presence_change for User 1
        msg = await comm2.receive_json_from(timeout=2)
        self.assertEqual(msg.get("type"), "presence_change")
        self.assertEqual(msg.get("user_id"), str(self.user1.id))
        self.assertEqual(msg.get("status"), "available")

        # User 1 disconnects
        await comm1.disconnect()

        # Check cache state: active_sockets becomes 0, last_seen deleted
        active_sockets_after = cache.get(f"user_active_sockets_{self.user1.id}")
        self.assertEqual(active_sockets_after, 0)
        self.assertIsNone(cache.get(f"user_last_seen_{self.user1.id}"))
        self.assertEqual(self.user1.availability_status, 'offline')

        # User 2 should receive offline broadcast for User 1
        msg_offline = await comm2.receive_json_from(timeout=2)
        self.assertEqual(msg_offline.get("type"), "presence_change")
        self.assertEqual(msg_offline.get("user_id"), str(self.user1.id))
        self.assertEqual(msg_offline.get("status"), "offline")

        await comm2.disconnect()

    async def test_multiple_sessions_do_not_falsely_mark_offline(self):
        """
        When a user has two open sessions (tabs), closing one session does NOT
        mark the user offline. Only when the last session closes do they go offline.
        """
        # Tab 1 connects
        tab1 = WebsocketCommunicator(application, "/ws/calls/global/")
        tab1.scope["user"] = self.user1
        conn1, _ = await tab1.connect()
        self.assertTrue(conn1)
        self.assertEqual(cache.get(f"user_active_sockets_{self.user1.id}"), 1)

        # Tab 2 connects
        tab2 = WebsocketCommunicator(application, "/ws/calls/global/")
        tab2.scope["user"] = self.user1
        conn2, _ = await tab2.connect()
        self.assertTrue(conn2)
        self.assertEqual(cache.get(f"user_active_sockets_{self.user1.id}"), 2)

        # Tab 1 disconnects (e.g. user closes one tab)
        await tab1.disconnect()
        self.assertEqual(cache.get(f"user_active_sockets_{self.user1.id}"), 1)
        # User 1 is STILL online because Tab 2 is still open
        self.assertIsNotNone(cache.get(f"user_last_seen_{self.user1.id}"))
        self.assertEqual(self.user1.availability_status, 'available')

        # Tab 2 disconnects (user closes last tab)
        await tab2.disconnect()
        self.assertEqual(cache.get(f"user_active_sockets_{self.user1.id}"), 0)
        # Now User 1 is offline
        self.assertIsNone(cache.get(f"user_last_seen_{self.user1.id}"))
        self.assertEqual(self.user1.availability_status, 'offline')

    async def test_workspace_isolation_of_presence_events(self):
        """
        Presence broadcasts are isolated to shared workspaces.
        User 3 in workspace2 does NOT receive User 1's presence updates.
        """
        # User 3 in workspace2 connects
        comm3 = WebsocketCommunicator(application, "/ws/calls/global/")
        comm3.scope["user"] = self.user3
        conn3, _ = await comm3.connect()
        self.assertTrue(conn3)

        # User 1 in workspace1 connects
        comm1 = WebsocketCommunicator(application, "/ws/calls/global/")
        comm1.scope["user"] = self.user1
        conn1, _ = await comm1.connect()
        self.assertTrue(conn1)

        # User 3 should receive nothing (timeout)
        received_nothing = await comm3.receive_nothing(timeout=0.5)
        self.assertTrue(received_nothing)

        await comm1.disconnect()
        await comm3.disconnect()

    def test_member_card_rendering_offline_vs_online(self):
        """
        Standardized member card template renders accurate presence dot & text,
        hover card attributes, and uniform styling.
        """
        # 1. Offline rendering
        rendered_offline = render_to_string('components/workspace_member_card.html', {
            'member': self.mem2,
            'is_selected': False,
        })
        self.assertIn('data-presence-user-id', rendered_offline)
        self.assertIn('Offline', rendered_offline)
        self.assertIn('bg-zinc-500', rendered_offline)
        self.assertIn('Bob Jones', rendered_offline)
        self.assertIn('data-user-hover', rendered_offline)
        self.assertIn('min-h-[64px]', rendered_offline)

        # 2. Online rendering
        cache.set(f"user_last_seen_{self.user2.id}", timezone.now().timestamp(), 300)
        rendered_online = render_to_string('components/workspace_member_card.html', {
            'member': self.mem2,
            'is_selected': False,
        })
        self.assertIn('Online', rendered_online)
        self.assertIn('bg-emerald-500', rendered_online)

        # 3. Selected card styling
        rendered_selected = render_to_string('components/workspace_member_card.html', {
            'member': self.mem2,
            'is_selected': True,
        })
        self.assertIn('ring-2 ring-blue-500', rendered_selected)
