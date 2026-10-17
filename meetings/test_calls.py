import json
from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from chat.models import DirectMessageConversation
from meetings.models import (
    Meeting, MeetingStatus, CallSession, CallStatus, CallEndedReason
)
from meetings.services import (
    initiate_call_session,
    accept_call_session,
    decline_call_session,
    cancel_call_session,
    timeout_call_session,
    mark_call_connected,
    get_active_call_for_user,
)
from notifications.models import Notification
from core.models import ModuleStatus
from asgiref.sync import async_to_sync
from meetings.consumers import GlobalCallConsumer

User = get_user_model()


class MeetHubCallingTests(TestCase):
    """
    Automated test suite for Meet Hub M1 Real-Time Calling System:
    - Call session initiation, workspace isolation, self-call prevention
    - Busy collision prevention & stale call auto-expiry
    - Recipient accept & decline flows
    - Caller cancel flow
    - Timeout & missed call notification creation
    - State machine invariants & terminal state protection
    - HTTP APIs for initiate, accept, decline, cancel, and status
    """

    def setUp(self):
        self.client = Client()

        # Ensure Meet Hub is operational by default in test suite
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={'status': ModuleStatus.STATUS_AVAILABLE}
        )

        # Users
        self.caller = User.objects.create_user(
            username='caller_user',
            email='caller@aetherspace.dev',
            password='TestPassword123!'
        )
        self.recipient = User.objects.create_user(
            username='recipient_user',
            email='recipient@aetherspace.dev',
            password='TestPassword123!'
        )
        self.outsider = User.objects.create_user(
            username='outsider_user',
            email='outsider@external.dev',
            password='TestPassword123!'
        )

        # Workspace
        self.workspace = Workspace.objects.create(
            name='Orbit Alpha',
            slug='orbit-alpha',
            owner=self.caller
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.caller,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.recipient,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # DM Conversation
        self.conversation = DirectMessageConversation.objects.create(
            workspace=self.workspace,
            participant1=self.caller,
            participant2=self.recipient
        )

    def test_initiate_call_session_success(self):
        """User A can initiate a video or audio call session with User B."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO',
            conversation=self.conversation
        )
        self.assertIsNotNone(session.id)
        self.assertEqual(session.status, CallStatus.RINGING)
        self.assertEqual(session.call_mode, 'VIDEO')
        self.assertEqual(session.caller, self.caller)
        self.assertEqual(session.recipient, self.recipient)
        self.assertIsNotNone(session.meeting)
        self.assertTrue(session.meeting.meeting_code.startswith('meet-'))
        self.assertEqual(session.meeting.status, MeetingStatus.LIVE)
        self.assertFalse(session.meeting.is_audio_only)

    def test_initiate_audio_only_call(self):
        """Audio calls are flagged with is_audio_only=True."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='AUDIO'
        )
        self.assertEqual(session.call_mode, 'AUDIO')
        self.assertTrue(session.meeting.is_audio_only)

    def test_self_call_rejected(self):
        """Users cannot call themselves."""
        with self.assertRaises(ValidationError):
            initiate_call_session(
                workspace=self.workspace,
                caller=self.caller,
                recipient=self.caller,
                call_mode='VIDEO'
            )

    def test_workspace_isolation_enforced(self):
        """Users outside the workspace cannot be called or initiate calls."""
        # Outsider recipient
        with self.assertRaises(PermissionError):
            initiate_call_session(
                workspace=self.workspace,
                caller=self.caller,
                recipient=self.outsider,
                call_mode='VIDEO'
            )

        # Outsider caller
        with self.assertRaises(PermissionError):
            initiate_call_session(
                workspace=self.workspace,
                caller=self.outsider,
                recipient=self.recipient,
                call_mode='VIDEO'
            )

    def test_busy_collision_prevention(self):
        """Cannot call a user who is already in an active ringing call."""
        # Initial call
        initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        # Another user in the workspace tries to call recipient
        third_user = User.objects.create_user(username='third', email='third@aetherspace.dev', password='p')
        WorkspaceMembership.objects.create(workspace=self.workspace, user=third_user, status=MembershipStatus.ACTIVE)

        with self.assertRaises(ValidationError) as ctx:
            initiate_call_session(
                workspace=self.workspace,
                caller=third_user,
                recipient=self.recipient,
                call_mode='VIDEO'
            )
        self.assertIn("on another call", str(ctx.exception))

    def test_caller_cannot_initiate_multiple_calls_simultaneously(self):
        """Caller cannot initiate a second call while first call is ringing."""
        initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        third_user = User.objects.create_user(username='third_b', email='thirdb@aetherspace.dev', password='p')
        WorkspaceMembership.objects.create(workspace=self.workspace, user=third_user, status=MembershipStatus.ACTIVE)

        with self.assertRaises(ValidationError) as ctx:
            initiate_call_session(
                workspace=self.workspace,
                caller=self.caller,
                recipient=third_user,
                call_mode='VIDEO'
            )
        self.assertIn("already have an active call", str(ctx.exception))

    def test_stale_call_auto_expires(self):
        """Stale ringing calls (> 45s) auto-expire and do not block subsequent calls."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )
        # Artificially age the session
        stale_time = timezone.now() - timedelta(seconds=60)
        CallSession.objects.filter(id=session.id).update(created_at=stale_time, ringing_at=stale_time)

        # New call should now succeed because the stale call auto-expires to MISSED
        new_session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )
        self.assertIsNotNone(new_session.id)
        session.refresh_from_db()
        self.assertEqual(session.status, CallStatus.MISSED)

    def test_accept_call_session(self):
        """Recipient accepts incoming call, transitioning to ACCEPTED."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        success, msg, room_url = accept_call_session(session.id, self.recipient)
        self.assertTrue(success)
        self.assertIn(session.meeting.meeting_code, room_url)

        session.refresh_from_db()
        self.assertEqual(session.status, CallStatus.ACCEPTED)
        self.assertIsNotNone(session.accepted_at)

    def test_accept_call_permission_denied_for_non_recipient(self):
        """Caller or third party cannot accept the incoming call."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        with self.assertRaises(PermissionError):
            accept_call_session(session.id, self.caller)

    def test_decline_call_session(self):
        """Recipient declines incoming call, transitioning to DECLINED."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        success, msg = decline_call_session(session.id, self.recipient)
        self.assertTrue(success)

        session.refresh_from_db()
        self.assertEqual(session.status, CallStatus.DECLINED)
        self.assertEqual(session.ended_reason, CallEndedReason.DECLINED)
        self.assertIsNotNone(session.ended_at)

    def test_decline_permission_denied_for_caller(self):
        """Caller cannot decline the call (caller cancels instead)."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        with self.assertRaises(PermissionError):
            decline_call_session(session.id, self.caller)

    def test_cancel_call_session(self):
        """Caller cancels outgoing call before it is answered."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        success, msg = cancel_call_session(session.id, self.caller)
        self.assertTrue(success)

        session.refresh_from_db()
        self.assertEqual(session.status, CallStatus.CANCELLED)
        self.assertEqual(session.ended_reason, CallEndedReason.CANCELLED)
        self.assertIsNotNone(session.ended_at)

    def test_cancel_permission_denied_for_recipient(self):
        """Recipient cannot cancel the call (recipient declines instead)."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        with self.assertRaises(PermissionError):
            cancel_call_session(session.id, self.recipient)

    def test_timeout_call_session_creates_notification(self):
        """Unanswered call marks MISSED and creates a notification for the recipient."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        success, msg = timeout_call_session(session.id)
        self.assertTrue(success)

        session.refresh_from_db()
        self.assertEqual(session.status, CallStatus.MISSED)
        self.assertEqual(session.ended_reason, CallEndedReason.TIMEOUT)
        self.assertIsNotNone(session.missed_at)

        # Verify persistent missed call notification was created
        notif = Notification.objects.filter(
            recipient=self.recipient,
            actor=self.caller
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn("Missed Call", notif.title)

    def test_mark_call_connected(self):
        """When peers enter room, call transitions from ACCEPTED to CONNECTED."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )
        accept_call_session(session.id, self.recipient)

        connected = mark_call_connected(session.meeting.meeting_code, self.recipient)
        self.assertTrue(connected)

        session.refresh_from_db()
        self.assertEqual(session.status, CallStatus.CONNECTED)
        self.assertIsNotNone(session.connected_at)

    def test_state_machine_terminal_protection(self):
        """Terminal states cannot be mutated back to ACCEPTED or CONNECTED."""
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )
        decline_call_session(session.id, self.recipient)

        # Attempt to accept after decline
        success, msg, _ = accept_call_session(session.id, self.recipient)
        self.assertFalse(success)
        self.assertIn("Cannot accept call", msg)

    def test_get_active_call_for_user(self):
        """get_active_call_for_user correctly identifies incoming and outgoing calls."""
        # No call active
        self.assertIsNone(get_active_call_for_user(self.recipient))
        self.assertIsNone(get_active_call_for_user(self.caller))

        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        # Recipient sees incoming call
        recip_data = get_active_call_for_user(self.recipient)
        self.assertIsNotNone(recip_data)
        self.assertEqual(recip_data['role'], 'recipient')
        self.assertEqual(recip_data['call_id'], str(session.id))

        # Caller sees outgoing call
        caller_data = get_active_call_for_user(self.caller)
        self.assertIsNotNone(caller_data)
        self.assertEqual(caller_data['role'], 'caller')
        self.assertEqual(caller_data['call_id'], str(session.id))


class MeetHubCallingAPITests(TestCase):
    """
    Automated tests for HTTP API endpoints:
    - /meetings/w/<slug>/api/calls/initiate/
    - /meetings/w/<slug>/api/calls/<id>/accept/
    - /meetings/w/<slug>/api/calls/<id>/decline/
    - /meetings/w/<slug>/api/calls/<id>/cancel/
    - /meetings/w/<slug>/api/calls/<id>/status/
    """

    def setUp(self):
        self.client = Client()
        self.caller = User.objects.create_user(
            username='api_caller',
            email='api_caller@aetherspace.dev',
            password='TestPassword123!'
        )
        self.recipient = User.objects.create_user(
            username='api_recipient',
            email='api_recipient@aetherspace.dev',
            password='TestPassword123!'
        )
        self.workspace = Workspace.objects.create(
            name='API Space',
            slug='api-space',
            owner=self.caller
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.caller,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.recipient,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        from core.models import ModuleStatus
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={
                'name': 'Meet Hub',
                'status': ModuleStatus.STATUS_AVAILABLE
            }
        )

    def test_call_initiate_api(self):
        self.client.force_login(self.caller)
        url = reverse('meetings:call_initiate_api', kwargs={'slug': self.workspace.slug})

        response = self.client.post(
            url,
            data=json.dumps({
                'recipient_id': str(self.recipient.id),
                'call_mode': 'VIDEO'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('call_id', data)
        self.assertIn('room_url', data)

    def test_call_status_api(self):
        self.client.force_login(self.caller)
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        url = reverse('meetings:call_status_api', kwargs={'slug': self.workspace.slug, 'call_id': session.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['call_id'], str(session.id))
        self.assertEqual(data['status'], CallStatus.RINGING)

    def test_call_accept_api(self):
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        self.client.force_login(self.recipient)
        url = reverse('meetings:call_accept_api', kwargs={'slug': self.workspace.slug, 'call_id': session.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('room_url', data)

        session.refresh_from_db()
        self.assertEqual(session.status, CallStatus.ACCEPTED)

    def test_call_decline_api(self):
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        self.client.force_login(self.recipient)
        url = reverse('meetings:call_decline_api', kwargs={'slug': self.workspace.slug, 'call_id': session.id})
        response = self.client.post(url, data={'reason': 'declined'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        session.refresh_from_db()
        self.assertEqual(session.status, CallStatus.DECLINED)

    def test_call_cancel_api(self):
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )

        self.client.force_login(self.caller)
        url = reverse('meetings:call_cancel_api', kwargs={'slug': self.workspace.slug, 'call_id': session.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        session.refresh_from_db()
        self.assertEqual(session.status, CallStatus.CANCELLED)

    def test_call_initiate_when_module_available(self):
        """When ModuleStatus is AVAILABLE, call session initiates normally."""
        ModuleStatus.objects.update_or_create(
            module_key='meetings',
            defaults={'status': ModuleStatus.STATUS_AVAILABLE}
        )
        session = initiate_call_session(
            workspace=self.workspace,
            caller=self.caller,
            recipient=self.recipient,
            call_mode='VIDEO'
        )
        self.assertIsNotNone(session)
        self.assertEqual(session.status, CallStatus.RINGING)

    def test_call_initiate_when_module_in_maintenance(self):
        """When ModuleStatus is MAINTENANCE, call initiation raises PermissionError and creates no CallSession."""
        try:
            ModuleStatus.objects.update_or_create(
                module_key='meetings',
                defaults={
                    'status': ModuleStatus.STATUS_MAINTENANCE,
                    'public_message': 'Meet Hub is undergoing planned upgrades.'
                }
            )
            with self.assertRaises(PermissionError) as ctx:
                initiate_call_session(
                    workspace=self.workspace,
                    caller=self.caller,
                    recipient=self.recipient,
                    call_mode='VIDEO'
                )
            self.assertIn('undergoing planned upgrades', str(ctx.exception))
        finally:
            ModuleStatus.objects.filter(module_key='meetings').update(status=ModuleStatus.STATUS_AVAILABLE)

    def test_call_initiate_when_module_coming_soon(self):
        """When ModuleStatus is COMING_SOON, call initiation raises PermissionError."""
        try:
            ModuleStatus.objects.update_or_create(
                module_key='meetings',
                defaults={
                    'status': ModuleStatus.STATUS_COMING_SOON,
                    'public_message': 'Meet Hub calling is coming soon.'
                }
            )
            with self.assertRaises(PermissionError) as ctx:
                initiate_call_session(
                    workspace=self.workspace,
                    caller=self.caller,
                    recipient=self.recipient,
                    call_mode='VIDEO'
                )
            self.assertIn('coming soon', str(ctx.exception))
        finally:
            ModuleStatus.objects.filter(module_key='meetings').update(status=ModuleStatus.STATUS_AVAILABLE)

    def test_global_call_consumer_handle_initiate_gating(self):
        """GlobalCallConsumer.handle_initiate respects AVAILABLE, MAINTENANCE, and COMING_SOON states."""
        consumer = GlobalCallConsumer()
        consumer.user = self.caller

        try:
            # 1. Maintenance state -> rejected with message
            ModuleStatus.objects.update_or_create(
                module_key='meetings',
                defaults={
                    'status': ModuleStatus.STATUS_MAINTENANCE,
                    'public_message': 'Meet Hub maintenance active.'
                }
            )
            res_maint = async_to_sync(consumer.handle_initiate)(
                workspace_slug=self.workspace.slug,
                recipient_id=str(self.recipient.id),
                call_mode='VIDEO',
                conversation_id=None
            )
            self.assertFalse(res_maint['success'])
            self.assertIn('maintenance active', res_maint['message'])

            # 2. Coming soon state -> rejected with message
            ModuleStatus.objects.update_or_create(
                module_key='meetings',
                defaults={
                    'status': ModuleStatus.STATUS_COMING_SOON,
                    'public_message': 'Meet Hub arriving soon.'
                }
            )
            res_soon = async_to_sync(consumer.handle_initiate)(
                workspace_slug=self.workspace.slug,
                recipient_id=str(self.recipient.id),
                call_mode='VIDEO',
                conversation_id=None
            )
            self.assertFalse(res_soon['success'])
            self.assertIn('arriving soon', res_soon['message'])

            # 3. Available state -> succeeds and returns call_id
            ModuleStatus.objects.update_or_create(
                module_key='meetings',
                defaults={'status': ModuleStatus.STATUS_AVAILABLE}
            )
            res_avail = async_to_sync(consumer.handle_initiate)(
                workspace_slug=self.workspace.slug,
                recipient_id=str(self.recipient.id),
                call_mode='VIDEO',
                conversation_id=None
            )
            self.assertTrue(res_avail['success'])
            self.assertIn('call_id', res_avail)
        finally:
            ModuleStatus.objects.filter(module_key='meetings').update(status=ModuleStatus.STATUS_AVAILABLE)
