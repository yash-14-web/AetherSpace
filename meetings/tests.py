import json
from datetime import timedelta
from django.conf import settings
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import ModuleStatus

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

        from core.models import ModuleStatus
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={
                'name': 'Meet Hub',
                'status': ModuleStatus.STATUS_AVAILABLE,
                'public_message': 'Meet Hub is operational.'
            }
        )

    def test_meeting_views_blocked_when_under_maintenance(self):
        from core.models import ModuleStatus
        try:
            ModuleStatus.objects.filter(module_key='meetings').update(status=ModuleStatus.STATUS_MAINTENANCE)
            self.client.force_login(self.owner)
            resp = self.client.get(reverse('meetings:meeting_start', kwargs={'slug': self.workspace.slug}))
            self.assertEqual(resp.status_code, 503)
            self.assertContains(resp, "Meet Hub", status_code=503)
        finally:
            ModuleStatus.objects.filter(module_key='meetings').update(status=ModuleStatus.STATUS_AVAILABLE)

    def test_meet_hub_access_authenticated_member(self):
        self.client.force_login(self.owner)
        url = reverse('meetings:meet_hub', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Meet Hub')

    def test_meet_hub_redesign_sections_and_no_recent_activity(self):
        """Verify redesigned Meet Hub contains the 4 approved sections and NO Recent Activity feed."""
        self.client.force_login(self.owner)
        url = reverse('meetings:meet_hub', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Section A: Header
        self.assertContains(response, 'Meet Hub')
        self.assertContains(response, 'Connect, collaborate, and meet with your workspace.')
        self.assertContains(response, 'Meeting ready')

        # Section B: Primary Meeting Actions
        self.assertContains(response, 'Start an instant meeting')
        self.assertContains(response, 'Launch a new meeting room and connect')
        self.assertContains(response, 'Start Meeting')
        self.assertContains(response, 'Schedule a meeting')
        self.assertContains(response, 'Plan a meeting for later and invite')
        self.assertContains(response, 'Schedule Meeting')

        # Section C: Upcoming Meetings
        self.assertContains(response, 'Upcoming Meetings')
        self.assertContains(response, 'View Calendar')
        self.assertContains(response, 'No upcoming meetings')

        # Section D: Workspace Members
        self.assertContains(response, 'Workspace Members')
        self.assertContains(response, 'Select or invite eligible participants to your meeting.')
        self.assertContains(response, 'View All Members')
        self.assertIn('workspace_members', response.context)

        # Verify Recent Activity is ABSENT
        self.assertNotContains(response, 'Recent Activity')
        self.assertNotContains(response, 'Recent Meetings')

    def test_meet_hub_upcoming_meetings_rendered(self):
        """Verify scheduled meetings render correctly in Upcoming Meetings section."""
        scheduled_time = timezone.now() + timedelta(days=2)
        schedule_meeting(
            workspace=self.workspace,
            host=self.owner,
            title='Architecture Sync',
            scheduled_start=scheduled_time,
            meeting_type=MeetingType.STANDUP,
            duration_minutes=30,
            invitees=[self.contributor]
        )
        self.client.force_login(self.contributor)
        url = reverse('meetings:meet_hub', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Architecture Sync')
        self.assertNotContains(response, 'No upcoming meetings')

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


class JitsiIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='jitsi_admin',
            email='jitsi_admin@example.com',
            password='TestPassword123!'
        )
        self.member = User.objects.create_user(
            username='jitsi_member',
            email='jitsi_member@example.com',
            password='TestPassword123!'
        )
        self.outsider = User.objects.create_user(
            username='jitsi_outsider',
            email='jitsi_outsider@example.com',
            password='TestPassword123!'
        )
        self.workspace = Workspace.objects.create(
            name='JitsiWorkspace',
            slug='jitsi-workspace',
            owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role=WorkspaceRole.ADMIN
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.member,
            role=WorkspaceRole.CONTRIBUTOR
        )
        self.meeting = create_instant_meeting(
            workspace=self.workspace,
            host=self.owner,
            title='Architecture Sync'
        )
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={
                'name': 'Meet Hub',
                'status': ModuleStatus.STATUS_AVAILABLE,
            }
        )

    def test_jitsi_domain_and_enabled_settings(self):
        """Verify JITSI_DOMAIN and JITSI_MEET_ENABLED are configured."""
        self.assertTrue(hasattr(settings, 'JITSI_DOMAIN'))
        self.assertIn(getattr(settings, 'JITSI_DOMAIN'), ['8x8.vc', 'meet.jit.si'])
        self.assertTrue(hasattr(settings, 'JITSI_MEET_ENABLED'))
        self.assertTrue(getattr(settings, 'JITSI_MEET_ENABLED'))

    def test_jitsi_room_name_deterministic_and_secure(self):
        """Verify jitsi_room_name is deterministic, has unguessable entropy, and valid characters."""
        room1 = self.meeting.jitsi_room_name
        room2 = self.meeting.jitsi_room_name
        self.assertEqual(room1, room2)

        # Must include workspace slug
        self.assertIn('jitsiworkspace', room1)
        # Must start with AetherSpace_
        self.assertTrue(room1.startswith('AetherSpace_'))
        # Must only contain alphanumeric and underscores
        import re
        self.assertTrue(re.match(r'^[A-Za-z0-9_]+$', room1))
        # Must be different for another meeting
        meeting2 = create_instant_meeting(
            workspace=self.workspace,
            host=self.owner,
            title='Standup 2'
        )
        self.assertNotEqual(self.meeting.jitsi_room_name, meeting2.jitsi_room_name)

    @override_settings(JAAS_APP_ID='', JITSI_DOMAIN='meet.jit.si')
    def test_meeting_room_receives_jitsi_context(self):
        """Verify meeting_room_view provides jitsi_domain, jitsi_room_name, jitsi_meet_enabled, and jitsi_user_info_json."""
        self.client.force_login(self.member)
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['jitsi_domain'], 'meet.jit.si')
        self.assertEqual(response.context['jitsi_room_name'], self.meeting.jitsi_room_name)
        self.assertTrue(response.context['jitsi_meet_enabled'])
        self.assertIn('displayName', response.context['jitsi_user_info_json'])
        self.assertIn('jitsi_member', response.context['jitsi_user_info_json'])
        self.assertContains(response, 'id="jitsi-meet-container"')
        self.assertContains(response, 'https://meet.jit.si/external_api.js')

    def test_non_member_cannot_access_meeting_room(self):
        """Verify outsider cannot access meeting room (403 Forbidden)."""
        self.client.force_login(self.outsider)
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_existing_meeting_urls_remain_valid(self):
        """Verify standard meeting URL resolution is unchanged."""
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        self.assertTrue(url.startswith(f"/meetings/w/{self.workspace.slug}/room/"))

    def test_meeting_participant_duration_seconds_calculation(self):
        """Verify MeetingParticipant.duration_seconds calculates accurately when online and left."""
        now = timezone.now()
        part = MeetingParticipant.objects.create(
            meeting=self.meeting,
            user=self.member,
            role=ParticipantRole.ATTENDEE,
            left_at=now - timedelta(minutes=4),
        )
        # Update joined_at directly because auto_now_add overrides create kwargs
        MeetingParticipant.objects.filter(id=part.id).update(joined_at=now - timedelta(minutes=10))
        part.refresh_from_db()
        # 6 minutes = 360 seconds
        self.assertEqual(part.duration_seconds, 360)

        # Online participant without left_at
        part_online = MeetingParticipant.objects.create(
            meeting=self.meeting,
            user=self.owner,
            role=ParticipantRole.HOST,
            left_at=None,
        )
        MeetingParticipant.objects.filter(id=part_online.id).update(joined_at=now - timedelta(minutes=3))
        part_online.refresh_from_db()
        self.assertGreaterEqual(part_online.duration_seconds, 175)

    def test_meeting_end_api_leave_action_preserves_meeting(self):
        """Verify participant leaving finalizes attendance but keeps meeting live."""
        record_participant_join(self.meeting, self.member)
        self.client.force_login(self.member)

        url = reverse('meetings:meeting_end_api', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        response = self.client.post(
            url,
            data=json.dumps({'action': 'leave'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertIn('redirect_url', data)

        # Meeting must still be LIVE
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, MeetingStatus.LIVE)

        # Participant must have left_at recorded
        part = MeetingParticipant.objects.get(meeting=self.meeting, user=self.member)
        self.assertIsNotNone(part.left_at)
        self.assertGreaterEqual(part.duration_seconds, 0)

    def test_meeting_end_api_host_end_action_closes_meeting(self):
        """Verify host ending meeting transitions status to ENDED."""
        self.client.force_login(self.owner)

        url = reverse('meetings:meeting_end_api', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        response = self.client.post(
            url,
            data=json.dumps({'action': 'end'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))

        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, MeetingStatus.ENDED)

    def test_jitsi_user_info_serialization_safety(self):
        """Verify jitsi_user_info_json exposes only safe display properties and no secrets."""
        self.client.force_login(self.member)
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        info_json = response.context['jitsi_user_info_json']
        user_info = json.loads(info_json)

        self.assertIn('displayName', user_info)
        self.assertIn('email', user_info)
        # Verify no sensitive password hashes, tokens, or system keys
        self.assertNotIn('password', user_info)
        self.assertNotIn('secret', user_info)
        self.assertNotIn('SECRET_KEY', str(response.content))

    def test_non_host_cannot_end_meeting_for_all(self):
        """Verify non-host participant cannot end the meeting for all (403 Forbidden)."""
        self.client.force_login(self.member)
        url = reverse('meetings:meeting_end_api', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        response = self.client.post(
            url,
            data=json.dumps({'action': 'end'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('Only the meeting host or workspace manager', data.get('error', ''))

        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, MeetingStatus.LIVE)

    def test_cross_workspace_direct_url_tampering_blocked(self):
        """Verify meeting code from another workspace cannot be accessed by altering URL slug."""
        other_owner = User.objects.create_user(
            username='other_ws_owner',
            email='other_ws_owner@example.com',
            password='TestPassword123!'
        )
        other_workspace = Workspace.objects.create(
            name='Other Workspace',
            slug='other-ws',
            owner=other_owner
        )
        WorkspaceMembership.objects.create(
            workspace=other_workspace,
            user=other_owner,
            role=WorkspaceRole.ADMIN
        )
        other_meeting = create_instant_meeting(
            workspace=other_workspace,
            host=other_owner,
            title='Secret Meeting'
        )

        # self.member is in self.workspace, but NOT in other_workspace
        # Attempting to query other_meeting code within self.workspace slug
        self.client.force_login(self.member)
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': other_meeting.meeting_code
        })
        response = self.client.get(url)
        # Redirected to meet_hub because meeting does not belong to self.workspace
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/meetings/w/{self.workspace.slug}/", response.url)

    def test_meeting_room_respects_maintenance_gate(self):
        """Verify meeting room returns 503 when Meet Hub module is in maintenance."""
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={
                'name': 'Meet Hub',
                'status': ModuleStatus.STATUS_MAINTENANCE,
            }
        )
        self.client.force_login(self.member)
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 503)

        # Restore available status for remaining tests
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={
                'name': 'Meet Hub',
                'status': ModuleStatus.STATUS_AVAILABLE,
            }
        )

    def test_jitsi_disabled_flag_context(self):
        """Verify room view correctly reflects JITSI_MEET_ENABLED=False."""
        with self.settings(JITSI_MEET_ENABLED=False):
            self.client.force_login(self.member)
            url = reverse('meetings:meeting_room', kwargs={
                'slug': self.workspace.slug,
                'meeting_code': self.meeting.meeting_code
            })
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context['jitsi_meet_enabled'])
            self.assertNotContains(response, 'https://meet.jit.si/external_api.js')

    def test_duplicate_participant_join_idempotent(self):
        """Verify calling record_participant_join repeatedly guarantees only one active record."""
        record_participant_join(self.meeting, self.member)
        record_participant_join(self.meeting, self.member)
        record_participant_join(self.meeting, self.member)
        self.assertEqual(
            MeetingParticipant.objects.filter(meeting=self.meeting, user=self.member).count(),
            1
        )

    def test_meeting_room_status_cancelled_and_ended(self):
        """Verify cancelled and ended meetings render appropriate status templates."""
        self.client.force_login(self.member)
        url = reverse('meetings:meeting_room', kwargs={
            'slug': self.workspace.slug,
            'meeting_code': self.meeting.meeting_code
        })

        # Cancelled
        self.meeting.status = MeetingStatus.CANCELLED
        self.meeting.save(update_fields=['status'])
        resp_cancelled = self.client.get(url)
        self.assertEqual(resp_cancelled.status_code, 200)
        self.assertContains(resp_cancelled, 'Meeting Cancelled')

        # Ended
        self.meeting.status = MeetingStatus.ENDED
        self.meeting.actual_end = timezone.now()
        self.meeting.save(update_fields=['status', 'actual_end'])
        resp_ended = self.client.get(url)
        self.assertEqual(resp_ended.status_code, 200)
        self.assertContains(resp_ended, 'Meeting Has Ended')
