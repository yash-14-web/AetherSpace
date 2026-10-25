import json
import logging
from datetime import timedelta
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from channels.testing import WebsocketCommunicator
from aetherspace.asgi import application

from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from meetings.models import Meeting, MeetingParticipant, MeetingType, MeetingStatus, ParticipantRole
from meetings.services import (
    create_instant_meeting,
    end_meeting,
    generate_jaas_jwt,
)
from meetings.views import cleanup_stale_meetings

User = get_user_model()


class MeetingWebRTCSignalingTests(TransactionTestCase):
    """
    Forensic test suite for Meet Hub WebRTC mesh signaling, Channels consumer,
    SDP offer/answer exchange, ICE forwarding, media state, and access control.
    """

    def setUp(self):
        # Create Host User (Alice)
        self.host = User.objects.create_user(
            email="alice@aetherspace.dev",
            password="Password123!",
            full_name="Alice Host",
            approval_status="APPROVED",
        )

        # Create Workspace Alpha
        self.workspace = Workspace.objects.create(
            name="Alpha Engineering",
            slug="alpha-eng",
            description="Alpha primary workspace",
            owner=self.host,
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.host,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE,
        )

        # Create Attendee User (Bob)
        self.attendee = User.objects.create_user(
            email="bob@aetherspace.dev",
            password="Password123!",
            full_name="Bob Engineer",
            approval_status="APPROVED",
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.attendee,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE,
        )

        # Create Unauthorized User (Eve - not a member of Alpha)
        self.unauthorized_user = User.objects.create_user(
            email="eve@aetherspace.dev",
            password="Password123!",
            full_name="Eve Outsider",
            approval_status="APPROVED",
        )

        # Create an Instant Meeting
        self.meeting = create_instant_meeting(
            workspace=self.workspace,
            host=self.host,
            title="Sprint Standup"
        )

    async def test_websocket_unauthenticated_connection_rejected(self):
        """Unauthenticated WebSocket connection is closed with 4001."""
        path = f"/ws/meetings/{self.workspace.slug}/{self.meeting.meeting_code}/"
        communicator = WebsocketCommunicator(application, path)
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4001)

    async def test_websocket_unauthorized_user_rejected(self):
        """User who is not a member of the workspace is rejected with 4003."""
        path = f"/ws/meetings/{self.workspace.slug}/{self.meeting.meeting_code}/"
        communicator = WebsocketCommunicator(application, path)
        communicator.scope["user"] = self.unauthorized_user
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4003)

    async def test_websocket_authenticated_member_connects_and_receives_room_state(self):
        """Authenticated workspace member connects, receives initial room_state payload."""
        path = f"/ws/meetings/{self.workspace.slug}/{self.meeting.meeting_code}/"
        communicator = WebsocketCommunicator(application, path)
        communicator.scope["user"] = self.host
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # First message must be room_state
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "room_state")
        self.assertEqual(response["meeting_code"], self.meeting.meeting_code)
        self.assertEqual(response["self"]["id"], str(self.host.id))
        self.assertTrue(response["is_host"])

        await communicator.disconnect()

    async def test_webrtc_signaling_two_user_offer_answer_and_ice(self):
        """
        Two participants (Alice and Bob) join the same room:
        1. Alice connects and gets room_state.
        2. Bob connects and gets room_state; Alice receives peer_joined.
        3. Alice sends signal_offer to Bob; Bob receives it.
        4. Bob sends signal_answer to Alice; Alice receives it.
        5. Alice sends signal_ice to Bob; Bob receives it.
        """
        path = f"/ws/meetings/{self.workspace.slug}/{self.meeting.meeting_code}/"

        # 1. Alice connects
        alice_comm = WebsocketCommunicator(application, path)
        alice_comm.scope["user"] = self.host
        alice_connected, _ = await alice_comm.connect()
        self.assertTrue(alice_connected)
        alice_state = await alice_comm.receive_json_from()
        self.assertEqual(alice_state["type"], "room_state")

        # 2. Bob connects
        bob_comm = WebsocketCommunicator(application, path)
        bob_comm.scope["user"] = self.attendee
        bob_connected, _ = await bob_comm.connect()
        self.assertTrue(bob_connected)
        bob_state = await bob_comm.receive_json_from()
        self.assertEqual(bob_state["type"], "room_state")

        # Alice receives peer_joined for Bob
        alice_peer_joined = await alice_comm.receive_json_from()
        self.assertEqual(alice_peer_joined["type"], "peer_joined")
        self.assertEqual(alice_peer_joined["peer"]["id"], str(self.attendee.id))

        # 3. Alice sends SDP offer to Bob
        dummy_sdp_offer = {"type": "offer", "sdp": "v=0\r\no=alice ..."}
        await alice_comm.send_json_to({
            "type": "signal_offer",
            "target_id": str(self.attendee.id),
            "sdp": dummy_sdp_offer,
        })

        bob_offer = await bob_comm.receive_json_from()
        self.assertEqual(bob_offer["type"], "signal_offer")
        self.assertEqual(bob_offer["sender_id"], str(self.host.id))
        self.assertEqual(bob_offer["sdp"], dummy_sdp_offer)

        # 4. Bob sends SDP answer to Alice
        dummy_sdp_answer = {"type": "answer", "sdp": "v=0\r\no=bob ..."}
        await bob_comm.send_json_to({
            "type": "signal_answer",
            "target_id": str(self.host.id),
            "sdp": dummy_sdp_answer,
        })

        alice_answer = await alice_comm.receive_json_from()
        self.assertEqual(alice_answer["type"], "signal_answer")
        self.assertEqual(alice_answer["sender_id"], str(self.attendee.id))
        self.assertEqual(alice_answer["sdp"], dummy_sdp_answer)

        # 5. Alice sends ICE candidate to Bob
        dummy_ice = {"candidate": "candidate:1 1 UDP ...", "sdpMid": "0"}
        await alice_comm.send_json_to({
            "type": "signal_ice",
            "target_id": str(self.attendee.id),
            "candidate": dummy_ice,
        })

        bob_ice = await bob_comm.receive_json_from()
        self.assertEqual(bob_ice["type"], "signal_ice")
        self.assertEqual(bob_ice["sender_id"], str(self.host.id))
        self.assertEqual(bob_ice["candidate"], dummy_ice)

        # Cleanup
        await alice_comm.disconnect()
        await bob_comm.disconnect()

    async def test_media_state_chat_and_reaction_broadcasts(self):
        """
        Verify real-time broadcast of:
        - media state (mute, camera, screenshare, hand raise)
        - meeting chat messages
        - floating emoji reactions
        """
        path = f"/ws/meetings/{self.workspace.slug}/{self.meeting.meeting_code}/"

        alice_comm = WebsocketCommunicator(application, path)
        alice_comm.scope["user"] = self.host
        await alice_comm.connect()
        await alice_comm.receive_json_from() # room_state

        bob_comm = WebsocketCommunicator(application, path)
        bob_comm.scope["user"] = self.attendee
        await bob_comm.connect()
        await bob_comm.receive_json_from() # room_state
        await alice_comm.receive_json_from() # peer_joined

        # Media state broadcast
        await alice_comm.send_json_to({
            "type": "media_state",
            "is_muted": False,
            "is_camera_on": True,
            "screen_sharing": True,
            "is_hand_raised": True,
        })
        bob_media = await bob_comm.receive_json_from()
        self.assertEqual(bob_media["type"], "media_state")
        self.assertEqual(bob_media["sender_id"], str(self.host.id))
        self.assertTrue(bob_media["media_state"]["screen_sharing"])
        self.assertTrue(bob_media["media_state"]["is_hand_raised"])

        # In-call chat broadcast
        await bob_comm.send_json_to({
            "type": "meeting_chat",
            "text": "Hello team, can everyone hear me?",
        })
        alice_chat = await alice_comm.receive_json_from()
        self.assertEqual(alice_chat["type"], "meeting_chat")
        self.assertEqual(alice_chat["message"]["text"], "Hello team, can everyone hear me?")
        self.assertEqual(alice_chat["message"]["sender_id"], str(self.attendee.id))

        bob_chat = await bob_comm.receive_json_from()
        self.assertEqual(bob_chat["type"], "meeting_chat")
        self.assertEqual(bob_chat["message"]["text"], "Hello team, can everyone hear me?")

        # Floating emoji reaction
        await alice_comm.send_json_to({
            "type": "meeting_reaction",
            "emoji": "🎉",
        })
        bob_reaction = await bob_comm.receive_json_from()
        self.assertEqual(bob_reaction["type"], "meeting_reaction")
        self.assertEqual(bob_reaction["emoji"], "🎉")
        self.assertEqual(bob_reaction["sender_id"], str(self.host.id))

        await alice_comm.disconnect()
        # Bob receives peer_left for Alice
        bob_left = await bob_comm.receive_json_from()
        self.assertEqual(bob_left["type"], "peer_left")
        self.assertEqual(bob_left["peer_id"], str(self.host.id))

        await bob_comm.disconnect()

    async def test_duplicate_tab_connect_and_disconnect_preserves_original_meeting(self):
        """
        Opening a duplicate/popout tab creates a second WebSocket for the same user.
        Closing the duplicate tab decrements the socket count, does NOT emit peer_left,
        does NOT mark the participant as left, and does NOT end the meeting.
        """
        path = f"/ws/meetings/{self.workspace.slug}/{self.meeting.meeting_code}/"

        # Alice opens Tab 1
        alice_tab1 = WebsocketCommunicator(application, path)
        alice_tab1.scope["user"] = self.host
        connected1, _ = await alice_tab1.connect()
        self.assertTrue(connected1)
        await alice_tab1.receive_json_from()  # room_state

        # Bob connects
        bob_comm = WebsocketCommunicator(application, path)
        bob_comm.scope["user"] = self.attendee
        connected_bob, _ = await bob_comm.connect()
        self.assertTrue(connected_bob)
        await bob_comm.receive_json_from()  # room_state
        await alice_tab1.receive_json_from()  # peer_joined (bob)

        # Alice opens duplicate Tab 2 (Pop-out)
        alice_tab2 = WebsocketCommunicator(application, path)
        alice_tab2.scope["user"] = self.host
        connected2, _ = await alice_tab2.connect()
        self.assertTrue(connected2)
        await alice_tab2.receive_json_from()  # room_state

        # Check cache socket count for Alice is 2
        socket_key = f"meeting_{self.meeting.id}_user_{self.host.id}_sockets"
        self.assertEqual(cache.get(socket_key), 2)

        # Alice closes duplicate Tab 2
        await alice_tab2.disconnect()

        # Cache socket count decremented to 1
        self.assertEqual(cache.get(socket_key), 1)

        # Bob should NOT receive peer_left because Alice is still active in Tab 1
        has_msg = await bob_comm.receive_nothing(timeout=0.1)
        self.assertTrue(has_msg, "Bob should not receive peer_left when Alice closes a secondary tab")

        from channels.db import database_sync_to_async

        @database_sync_to_async
        def get_meeting_status():
            self.meeting.refresh_from_db()
            return self.meeting.status

        # Meeting must remain LIVE
        status = await get_meeting_status()
        self.assertEqual(status, MeetingStatus.LIVE)

        # Alice closes Tab 1
        await alice_tab1.disconnect()
        self.assertEqual(cache.get(socket_key, 0), 0)

        # Now Bob receives peer_left
        bob_msg = await bob_comm.receive_json_from()
        self.assertEqual(bob_msg["type"], "peer_left")
        self.assertEqual(bob_msg["peer_id"], str(self.host.id))

        # Meeting should still not be killed prematurely by a WebSocket disconnect
        status = await get_meeting_status()
        self.assertEqual(status, MeetingStatus.LIVE)

        await bob_comm.disconnect()


class MeetingRoomViewTests(TestCase):
    """
    Test suite for HTTP meeting room views, WebRTC context injection, and security.
    """

    def setUp(self):
        self.host = User.objects.create_user(
            email="charlie@aetherspace.dev",
            password="Password123!",
            full_name="Charlie Host",
            approval_status="APPROVED",
        )
        self.workspace = Workspace.objects.create(
            name="Beta Projects",
            slug="beta-proj",
            owner=self.host,
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.host,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE,
        )
        from core.models import ModuleStatus
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={
                'name': 'Meet Hub',
                'status': ModuleStatus.STATUS_AVAILABLE,
            }
        )
        self.meeting = create_instant_meeting(
            workspace=self.workspace,
            host=self.host,
            title="Design Review"
        )

    def test_meeting_room_view_injects_webrtc_ice_servers_and_user_meta(self):
        """Room view returns 200 and passes ice_servers_json, current_user_json, user_id_str."""
        self.client.force_login(self.host)
        url = f"/meetings/w/{self.workspace.slug}/room/{self.meeting.meeting_code}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self.assertIn("ice_servers_json", response.context)
        self.assertIn("user_id_str", response.context)
        self.assertEqual(response.context["user_id_str"], str(self.host.id))
        self.assertIn("current_user_json", response.context)
        self.assertContains(response, 'id="jitsi-meet-container"')

    def test_cross_workspace_meeting_room_access_blocked(self):
        """User cannot access meeting room of a workspace they do not belong to."""
        other_user = User.objects.create_user(
            email="other@aetherspace.dev",
            password="Password123!",
            approval_status="APPROVED",
        )
        self.client.force_login(other_user)
        url = f"/meetings/w/{self.workspace.slug}/room/{self.meeting.meeting_code}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


class MeetingLifecycleAndMultiTabTests(TestCase):
    """
    Focused verification tests for Meet Hub lifecycle:
    - Multi-tab presence & Pop-out leave behavior
    - Unload / refresh beacon handling
    - Explicit host termination
    - Periodic heartbeat ping & stale-meeting cleanup
    - Safe diagnostic logging (no JWTs or private keys logged)
    """

    def setUp(self):
        self.host = User.objects.create_user(
            email="host@aetherspace.dev",
            password="Password123!",
            full_name="Host User",
            approval_status="APPROVED",
        )
        self.workspace = Workspace.objects.create(
            name="Lifecycle Space",
            slug="lifecycle-space",
            owner=self.host,
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.host,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE,
        )
        from core.models import ModuleStatus
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={'name': 'Meet Hub', 'status': ModuleStatus.STATUS_AVAILABLE}
        )
        self.meeting = create_instant_meeting(
            workspace=self.workspace,
            host=self.host,
            title="Lifecycle Test Standup"
        )
        self.client.force_login(self.host)

    def tearDown(self):
        cache.clear()

    def test_closing_secondary_tab_preserves_original_meeting(self):
        """
        When a user closes a secondary tab (e.g. pop-out window),
        meeting_end_api detects active sockets remaining in cache,
        records no full leave, and leaves the meeting LIVE.
        """
        # Simulate active tab 1 socket
        socket_key = f"meeting_{self.meeting.id}_user_{self.host.id}_sockets"
        cache.set(socket_key, 1, timeout=300)

        url = f"/meetings/w/{self.workspace.slug}/{self.meeting.meeting_code}/api/end/"
        resp = self.client.post(url, data=json.dumps({"action": "leave"}), content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("Secondary tab closed", data.get("message", ""))

        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, MeetingStatus.LIVE)

    def test_unload_beacon_on_refresh_preserves_meeting(self):
        """
        When a tab refreshes (F5), pagehide sends a beacon with is_unload=True.
        The endpoint must preserve the meeting session and not immediately terminate it.
        """
        url = f"/meetings/w/{self.workspace.slug}/{self.meeting.meeting_code}/api/end/"
        resp = self.client.post(
            url,
            data=json.dumps({"action": "leave", "is_unload": True}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("action"), "leave")

        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, MeetingStatus.LIVE)

    def test_explicit_host_end_terminates_meeting_for_all(self):
        """
        When the host explicitly clicks 'End meeting for all' (action='end'),
        the meeting status transitions to ENDED immediately.
        """
        url = f"/meetings/w/{self.workspace.slug}/{self.meeting.meeting_code}/api/end/"
        resp = self.client.post(
            url,
            data=json.dumps({"action": "end"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("action"), "end")

        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, MeetingStatus.ENDED)

    def test_heartbeat_ping_updates_timestamp(self):
        """
        Frontend 25-second ping updates the meeting's updated_at timestamp,
        preventing background cleanup from marking an active room as stale.
        """
        old_time = timezone.now() - timedelta(minutes=10)
        Meeting.objects.filter(id=self.meeting.id).update(updated_at=old_time)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.updated_at, old_time)

        ping_url = f"/meetings/w/{self.workspace.slug}/{self.meeting.meeting_code}/api/ping/"
        resp = self.client.post(ping_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("status"), "LIVE")

        self.meeting.refresh_from_db()
        self.assertGreater(self.meeting.updated_at, old_time)

    def test_stale_meeting_cleanup_policy(self):
        """
        cleanup_stale_meetings should end abandoned meetings (>180s without heartbeat
        and no active participants), while keeping active meetings live.
        """
        # Active meeting with recent update is NOT cleaned up
        cleanup_stale_meetings(self.workspace)
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, MeetingStatus.LIVE)

        # Abandoned meeting: old created_at (>300s), old updated_at (>180s), all participants left
        old_time = timezone.now() - timedelta(minutes=10)
        MeetingParticipant.objects.filter(meeting=self.meeting).update(
            left_at=old_time
        )
        Meeting.objects.filter(id=self.meeting.id).update(
            created_at=old_time,
            updated_at=old_time
        )

        cleanup_stale_meetings(self.workspace)

        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, MeetingStatus.ENDED)

    def test_diagnostic_logging_never_includes_secrets(self):
        """
        Ensure logger outputs in meetings services never expose private keys or JWT tokens.
        """
        logger = logging.getLogger("meetings.services")
        log_records = []

        class InterceptHandler(logging.Handler):
            def emit(self, record):
                log_records.append(record.getMessage())

        handler = InterceptHandler()
        logger.addHandler(handler)
        prev_level = logger.level
        logger.setLevel(logging.DEBUG)

        try:
            # Trigger JWT generation with dummy keys
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization

            dummy_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            dummy_pem = dummy_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')

            with override_settings(
                JAAS_APP_ID="vpaas-magic-cookie-test",
                JAAS_API_KEY_ID="test-key",
                JAAS_PRIVATE_KEY=dummy_pem
            ):
                token, err = generate_jaas_jwt(self.meeting, self.host)
                self.assertIsNotNone(token)

            # Check that log messages never contain the private key header or full JWT
            for msg in log_records:
                self.assertNotIn("BEGIN PRIVATE KEY", msg)
                self.assertNotIn("BEGIN RSA PRIVATE KEY", msg)
                if token:
                    self.assertNotIn(token, msg)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(prev_level)
