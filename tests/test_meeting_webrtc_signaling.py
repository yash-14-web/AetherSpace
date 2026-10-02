import json
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from channels.testing import WebsocketCommunicator
from aetherspace.asgi import application

from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from meetings.models import Meeting, MeetingParticipant, MeetingType, MeetingStatus, ParticipantRole
from meetings.services import create_instant_meeting, end_meeting

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
        self.assertContains(response, 'id="local-video"')
        self.assertContains(response, 'x-show="peer.is_camera_on || peer.screen_sharing"')

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
