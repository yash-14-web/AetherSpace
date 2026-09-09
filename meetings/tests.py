from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model

from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from chat.models import Channel, DirectMessageConversation, Message
from meetings.models import (
    Meeting,
    MeetingType,
    MeetingStatus,
    ParticipantRole,
    MeetingParticipant,
    MeetingInvite,
)
from meetings.services import (
    generate_unique_meeting_code,
    create_instant_meeting,
    create_chat_call,
    schedule_meeting,
    start_meeting,
    end_meeting,
    cancel_meeting,
    record_participant_join,
    record_participant_leave,
)

User = get_user_model()


class MeetingModelAndServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='admin_owner',
            email='admin@example.com',
            password='TestPassword123!'
        )
        self.contributor = User.objects.create_user(
            username='dev_alice',
            email='alice@example.com',
            password='TestPassword123!'
        )
        self.workspace = Workspace.objects.create(
            name='AetherCorp',
            slug='aethercorp',
            owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role=WorkspaceRole.ADMIN
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR
        )

    def test_meeting_code_generation(self):
        code = generate_unique_meeting_code()
        self.assertTrue(code.startswith('meet-'))
        parts = code.split('-')
        self.assertEqual(len(parts), 3)
        self.assertEqual(len(parts[1]), 4)
        self.assertEqual(len(parts[2]), 4)

    def test_create_instant_meeting(self):
        meeting = create_instant_meeting(
            workspace=self.workspace,
            host=self.owner,
            title='Ad-hoc Sync',
            is_audio_only=False
        )
        self.assertEqual(meeting.status, MeetingStatus.LIVE)
        self.assertEqual(meeting.meeting_type, MeetingType.INSTANT)
        self.assertFalse(meeting.is_audio_only)
        self.assertIsNotNone(meeting.actual_start)
        
        # Verify host participant created
        participants = MeetingParticipant.objects.filter(meeting=meeting)
        self.assertEqual(participants.count(), 1)
        self.assertEqual(participants.first().user, self.owner)
        self.assertEqual(participants.first().role, ParticipantRole.HOST)
        self.assertTrue(meeting.is_live)

    def test_schedule_meeting(self):
        start_time = timezone.now() + timedelta(days=1)
        meeting = schedule_meeting(
            workspace=self.workspace,
            host=self.owner,
            title='Sprint Retrospective',
            scheduled_start=start_time,
            meeting_type=MeetingType.STANDUP,
            duration_minutes=45,
            invitees=[self.contributor]
        )
        self.assertEqual(meeting.status, MeetingStatus.SCHEDULED)
        self.assertEqual(meeting.invites.count(), 1)
        self.assertEqual(meeting.invites.first().user, self.contributor)
        self.assertFalse(meeting.is_live)

    def test_participant_join_and_leave(self):
        meeting = create_instant_meeting(
            workspace=self.workspace,
            host=self.owner,
            title='Standup'
        )
        # Contributor joins
        part = record_participant_join(meeting, self.contributor)
        self.assertEqual(part.role, ParticipantRole.ATTENDEE)
        self.assertTrue(part.is_online)
        self.assertEqual(meeting.active_participants_count, 2)

        # Contributor leaves
        record_participant_leave(meeting, self.contributor)
        part.refresh_from_db()
        self.assertFalse(part.is_online)
        self.assertIsNotNone(part.left_at)
        self.assertEqual(meeting.active_participants_count, 1)

    def test_end_meeting(self):
        meeting = create_instant_meeting(
            workspace=self.workspace,
            host=self.owner,
            title='Standup'
        )
        end_meeting(meeting)
        self.assertEqual(meeting.status, MeetingStatus.ENDED)
        self.assertIsNotNone(meeting.actual_end)
        self.assertFalse(meeting.is_live)

    def test_cancel_meeting(self):
        start_time = timezone.now() + timedelta(days=2)
        meeting = schedule_meeting(
            workspace=self.workspace,
            host=self.owner,
            title='Standup',
            scheduled_start=start_time
        )
        cancel_meeting(meeting)
        self.assertEqual(meeting.status, MeetingStatus.CANCELLED)


class MeetingViewsAndRBACTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username='lead_manager',
            email='lead@example.com',
            password='TestPassword123!'
        )
        self.contributor = User.objects.create_user(
            username='dev_bob',
            email='bob@example.com',
            password='TestPassword123!'
        )
        self.outsider = User.objects.create_user(
            username='outsider_mallory',
            email='mallory@example.com',
            password='TestPassword123!'
        )
        self.workspace = Workspace.objects.create(
            name='AetherCorp',
            slug='aethercorp',
            owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role=WorkspaceRole.MANAGER
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR
        )

    def test_meet_hub_access_authenticated_member(self):
        self.client.force_login(self.owner)
        url = reverse('meetings:meet_hub', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Meet Hub')

    def test_meet_hub_access_denied_outsider(self):
        self.client.force_login(self.outsider)
        url = reverse('meetings:meet_hub', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_start_instant_meeting_post(self):
        self.client.force_login(self.contributor)
        url = reverse('meetings:meeting_start', kwargs={'slug': self.workspace.slug})
        response = self.client.post(url, {
            'title': 'Feature Review',
            'call_mode': 'VIDEO'
        })
        self.assertEqual(response.status_code, 302)
        created = Meeting.objects.filter(workspace=self.workspace, title='Feature Review').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.host, self.contributor)
        self.assertRedirects(response, reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': created.meeting_code
        }))

    def test_meeting_room_status_completed(self):
        meeting = create_instant_meeting(
            workspace=self.workspace,
            host=self.owner,
            title='Concluded Call'
        )
        end_meeting(meeting)
        self.client.force_login(self.contributor)
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': meeting.meeting_code
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Meeting Has Ended')

    def test_in_chat_calling_integration_channel(self):
        channel = Channel.objects.create(
            workspace=self.workspace,
            name='general',
            slug='general',
            created_by=self.owner
        )
        self.client.force_login(self.owner)
        url = reverse('meetings:meeting_chat_call', kwargs={'slug': self.workspace.slug})
        response = self.client.post(url, {
            'channel_id': str(channel.id),
            'call_type': 'video'
        })
        self.assertEqual(response.status_code, 302)
        
        # Check that meeting was created
        meeting = Meeting.objects.filter(workspace=self.workspace, meeting_type=MeetingType.CHAT_CALL).first()
        self.assertIsNotNone(meeting)
        
        # Check that Message was posted
        msg = Message.objects.filter(channel=channel).first()
        self.assertIsNotNone(msg)
        self.assertTrue(msg.content.startswith(f"CALL_INVITE:{meeting.meeting_code}"))

    def test_in_chat_calling_integration_dm(self):
        conv = DirectMessageConversation.objects.create(
            workspace=self.workspace,
            participant1=self.owner,
            participant2=self.contributor
        )
        self.client.force_login(self.contributor)
        url = reverse('meetings:meeting_chat_call', kwargs={'slug': self.workspace.slug})
        response = self.client.post(url, {
            'conversation_id': str(conv.id),
            'call_type': 'audio'
        })
        self.assertEqual(response.status_code, 302)
        
        meeting = Meeting.objects.filter(workspace=self.workspace, meeting_type=MeetingType.CHAT_CALL, is_audio_only=True).first()
        self.assertIsNotNone(meeting)
        
        # Check direct message was posted
        msg = Message.objects.filter(conversation=conv).first()
        self.assertIsNotNone(msg)
        self.assertTrue(msg.content.startswith(f"CALL_INVITE:{meeting.meeting_code}:AUDIO"))
