from django.test import TestCase
from django.core import mail
from django.utils import timezone

from accounts.models import User, UserProfile, UserRole, ApprovalStatus
from workspaces.models import Workspace, WorkspaceRole, MembershipStatus, WorkspaceMembership
from tasks.models import Task, TaskStatus, TaskPriority
from meetings.models import Meeting, MeetingType, MeetingStatus
from notifications.models import EmailDeliveryLog, EmailDeliveryStatus
from notifications.email_service import (
    send_aether_email,
    send_task_assigned_email,
    send_meeting_scheduled_email,
    send_account_approved_email,
    send_account_status_email,
    send_workspace_invitation_email
)


class EmailNotificationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@aetherspace.dev',
            username='admin',
            password='Password123!',
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )
        UserProfile.objects.create(user=self.admin)

        self.user = User.objects.create_user(
            email='dev@aetherspace.dev',
            username='devuser',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )
        UserProfile.objects.create(user=self.user)

        self.workspace = Workspace.objects.create(
            name='Email Test WS',
            slug='email-test-ws',
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
            user=self.user,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

    def test_send_aether_email_basic_and_log(self):
        """Test sending email creates outbox message and EmailDeliveryLog entry."""
        mail.outbox = []
        success = send_aether_email(
            recipient_email=self.user.email,
            subject='Test Subject',
            html_content='<p>Hello Test</p>',
            text_content='Hello Test',
            event_type='TEST_EVENT',
            recipient_user=self.user
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Test Subject')
        self.assertEqual(mail.outbox[0].to, [self.user.email])

        log = EmailDeliveryLog.objects.filter(recipient_email=self.user.email).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, EmailDeliveryStatus.SENT)
        self.assertEqual(log.event_type, 'TEST_EVENT')

    def test_email_preference_opt_out(self):
        """Ensure users with email_frequency 'never' do not receive emails."""
        mail.outbox = []
        # Update user profile preferences
        profile = self.user.profile
        prefs = profile.preferences or {}
        prefs['notifications'] = {'email_frequency': 'never'}
        profile.preferences = prefs
        profile.save()

        success = send_aether_email(
            recipient_email=self.user.email,
            subject='Should Not Send',
            html_content='<p>Ignored</p>',
            recipient_user=self.user
        )
        self.assertFalse(success)
        self.assertEqual(len(mail.outbox), 0)

        log = EmailDeliveryLog.objects.filter(recipient_email=self.user.email, subject='Should Not Send').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, EmailDeliveryStatus.SUPPRESSED)

    def test_email_deduplication(self):
        """Verify identical emails sent within 60s are suppressed."""
        mail.outbox = []
        # First send
        send_aether_email(
            recipient_email=self.user.email,
            subject='Dedup Test',
            html_content='<p>First</p>',
            recipient_user=self.user
        )
        self.assertEqual(len(mail.outbox), 1)

        # Immediate duplicate send
        dup_success = send_aether_email(
            recipient_email=self.user.email,
            subject='Dedup Test',
            html_content='<p>First</p>',
            recipient_user=self.user
        )
        self.assertFalse(dup_success)
        self.assertEqual(len(mail.outbox), 1)  # Still 1

    def test_send_task_assigned_email(self):
        """Test task assignment email trigger."""
        mail.outbox = []
        task = Task.objects.create(
            task_code='619347',
            workspace=self.workspace,
            reporter=self.admin,
            assignee=self.user,
            title='Implement Email Notifications',
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH
        )
        success = send_task_assigned_email(task=task, assignee=self.user, actor=self.admin)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('#619347', mail.outbox[0].subject)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_send_meeting_scheduled_email(self):
        """Test meeting scheduled email trigger."""
        mail.outbox = []
        meeting = Meeting.objects.create(
            workspace=self.workspace,
            meeting_code='meet-a1b2-c3d4',
            title='Sprint Kickoff',
            host=self.admin,
            meeting_type=MeetingType.GENERAL,
            status=MeetingStatus.SCHEDULED,
            scheduled_start=timezone.now() + timezone.timedelta(days=1)
        )
        success = send_meeting_scheduled_email(meeting=meeting, recipient=self.user, actor=self.admin)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Sprint Kickoff', mail.outbox[0].subject)

    def test_send_account_approved_email(self):
        """Test account approved email trigger."""
        mail.outbox = []
        success = send_account_approved_email(user=self.user, approved_by=self.admin)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Account has been Approved', mail.outbox[0].subject)

    def test_send_workspace_invitation_email(self):
        """Test workspace invitation email trigger."""
        mail.outbox = []
        success = send_workspace_invitation_email(
            recipient_email='invitee@example.com',
            workspace=self.workspace,
            invitation_url='http://localhost:8000/workspaces/invite/xyz/',
            role_name='Contributor',
            actor=self.admin
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.workspace.name, mail.outbox[0].subject)
