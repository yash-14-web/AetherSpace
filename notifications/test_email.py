from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from django.template.loader import render_to_string

from accounts.models import User, UserProfile, UserRole, ApprovalStatus
from workspaces.models import (
    Workspace, WorkspaceRole, MembershipStatus, WorkspaceMembership,
    WorkspaceInvitation, WorkspaceAccessRequest, GlobalAccessRequest,
    AccessRequestAction, AccessRequestStatus
)
from tasks.models import Task, TaskStatus, TaskPriority
from meetings.models import Meeting, MeetingType, MeetingStatus
from notifications.models import EmailDeliveryLog, EmailDeliveryStatus, EmailEventType
from notifications.email_service import (
    send_aether_email,
    send_task_assigned_email,
    send_meeting_scheduled_email,
    send_account_approved_email,
    send_account_status_email,
    send_workspace_invitation_email,
    send_password_reset_email,
    send_email_verification_email,
    send_notification_email,
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

    # =========================================================================
    # Phase A Regression Tests (Tests 1 to 12)
    # =========================================================================

    def test_regression_test_1_password_reset_ignores_notification_frequency(self):
        """Test 1: Password reset email ignores email_frequency='never'."""
        mail.outbox = []
        profile = self.user.profile
        profile.preferences = {'notifications': {'email_frequency': 'never'}}
        profile.save()

        reset_url = "https://app.aetherspace.dev/auth/reset-password/test-token/"
        success = send_password_reset_email(user=self.user, reset_url=reset_url)

        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reset Your Account Password", mail.outbox[0].subject)
        self.assertIn(reset_url, mail.outbox[0].body)
        log = EmailDeliveryLog.objects.filter(
            recipient_email=self.user.email,
            event_type=EmailEventType.PASSWORD_RESET
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, EmailDeliveryStatus.SENT)

    def test_regression_test_2_email_verification_ignores_notification_frequency(self):
        """Test 2: Email verification ignores email_frequency='never'."""
        mail.outbox = []
        profile = self.user.profile
        profile.preferences = {'notifications': {'email_frequency': 'never'}}
        profile.save()

        verify_url = "https://app.aetherspace.dev/auth/verify/test-token/"
        success = send_email_verification_email(user=self.user, verify_url=verify_url)

        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Verify Your Email Address", mail.outbox[0].subject)
        self.assertIn(verify_url, mail.outbox[0].body)
        log = EmailDeliveryLog.objects.filter(
            recipient_email=self.user.email,
            event_type=EmailEventType.EMAIL_VERIFICATION
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, EmailDeliveryStatus.SENT)

    def test_regression_test_3_workspace_invitation_context(self):
        """Test 3: Workspace invitation displays workspace name and role in HTML and TXT without blanks."""
        mail.outbox = []
        invite = WorkspaceInvitation.objects.create(
            workspace=self.workspace,
            email='newcontributor@aetherspace.dev',
            role=WorkspaceRole.CONTRIBUTOR,
            invited_by=self.admin
        )

        success = send_workspace_invitation_email(
            invitation=invite,
            recipient_email=invite.email,
            workspace=self.workspace,
            invitation_url=f"/workspaces/join/{invite.token}/",
            role_name=invite.get_role_display(),
            actor=self.admin
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        msg = mail.outbox[0]
        html_content = msg.alternatives[0][0]
        text_content = msg.body

        # Assert workspace name in both HTML and TXT
        self.assertIn(self.workspace.name, text_content)
        self.assertIn(self.workspace.name, html_content)

        # Assert role in both HTML and TXT
        self.assertIn("Contributor", text_content)
        self.assertIn("Contributor", html_content)

        # Assert inviter/actor info
        self.assertIn(self.admin.email, text_content)
        self.assertIn(self.admin.email, html_content)

        # Assert CTA URL is present
        self.assertIn(f"/workspaces/join/{invite.token}/", text_content)
        self.assertIn(f"/workspaces/join/{invite.token}/", html_content)

        # Ensure no blanks or undefined values
        self.assertNotIn("Role: </", html_content)
        self.assertNotIn("Join  on AetherSpace", html_content)
        self.assertNotIn("Role: \n", text_content)

    @override_settings(SITE_URL='https://app.aetherspace.dev')
    def test_regression_test_4_production_site_url(self):
        """Test 4: Configured production SITE_URL is used in email CTAs instead of localhost."""
        mail.outbox = []
        task = Task.objects.create(
            task_code='789012',
            workspace=self.workspace,
            reporter=self.admin,
            assignee=self.user,
            title='Production URL Test Task',
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH
        )
        success = send_task_assigned_email(task=task, assignee=self.user, actor=self.admin)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        msg = mail.outbox[0]
        html_content = msg.alternatives[0][0]
        text_content = msg.body

        # Confirm configured production site URL is present
        expected_cta = f"https://app.aetherspace.dev/tasks/w/{self.workspace.slug}/t/{task.task_code}/"
        self.assertIn(expected_cta, text_content)
        self.assertIn(expected_cta, html_content)

        # Confirm localhost fallback is not used
        self.assertNotIn("http://127.0.0.1:8000", text_content)
        self.assertNotIn("http://127.0.0.1:8000", html_content)

    def test_regression_test_5_general_notification_txt(self):
        """Test 5: General notification uses dedicated .txt template without leaking HTML tags."""
        mail.outbox = []
        success = send_notification_email(
            recipient_user=self.user,
            event_type=EmailEventType.GENERAL,
            subject='[AetherSpace] Platform Maintenance Notice',
            template_name='notifications/emails/general_notification.html',
            context={
                'title': 'Scheduled Maintenance',
                'body': 'System maintenance will occur at midnight UTC.',
                'action_url': '/status/',
            }
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        msg = mail.outbox[0]
        text_content = msg.body

        # Dedicated .txt template header and content
        self.assertIn("AETHERSPACE NOTIFICATION", text_content)
        self.assertNotIn("⚡", text_content)
        self.assertIn("Scheduled Maintenance", text_content)
        self.assertIn("System maintenance will occur at midnight UTC.", text_content)
        self.assertIn("/status/", text_content)

        # Ensure no HTML tags leaked into plain text
        self.assertNotIn("<html>", text_content)
        self.assertNotIn("<body>", text_content)
        self.assertNotIn("<div", text_content)
        self.assertNotIn("<p>", text_content)
        self.assertNotIn("<span", text_content)

    def test_regression_test_6_html_entity_handling(self):
        """Test 6: Plain-text unescapes entities (' becomes ' not &#x27;) while HTML remains safely escaped."""
        mail.outbox = []
        title = "Dev's <Critical> & \"High\" Task"
        body = "Here's the user's issue with <angle brackets> & \"quotes\"."

        send_notification_email(
            recipient_user=self.user,
            event_type=EmailEventType.GENERAL,
            subject='[AetherSpace] Entity Test',
            template_name='notifications/emails/general_notification.html',
            context={
                'title': title,
                'body': body,
            }
        )
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        text_content = msg.body
        html_content = msg.alternatives[0][0]

        # Plain text must be human-readable without raw entity codes
        self.assertIn("Dev's", text_content)
        self.assertNotIn("&#x27;", text_content)
        self.assertNotIn("&quot;", text_content)
        self.assertNotIn("&amp;", text_content)
        self.assertIn("user's issue", text_content)
        self.assertIn('"quotes"', text_content)

        # HTML content must be safely escaped by Django
        self.assertTrue("&#x27;" in html_content or "&apos;" in html_content or "&#39;" in html_content)
        self.assertIn("&amp;", html_content)

        # Also test fallback path where no dedicated .txt template exists
        mail.outbox = []
        raw_html = "<p>User&#x27;s request for &quot;Admin&quot; &amp; &lt;Manager&gt;</p>"
        send_aether_email(
            recipient_email=self.user.email,
            subject='Fallback Entity Test',
            html_content=raw_html,
            recipient_user=self.user
        )
        fallback_text = mail.outbox[0].body
        self.assertIn("User's request for \"Admin\" & <Manager>", fallback_text)
        self.assertNotIn("&#x27;", fallback_text)
        self.assertNotIn("&quot;", fallback_text)
        self.assertNotIn("&amp;", fallback_text)

    def test_regression_test_7_access_request_display_label(self):
        """Test 7: Access request email displays human-readable label ('Create Task' not 'task.create')."""
        mail.outbox = []
        req_task = GlobalAccessRequest.objects.create(
            user=self.user,
            workspace=self.workspace,
            action=AccessRequestAction.TASK_CREATE,
            reason="Need to create tasks for the sprint",
            status=AccessRequestStatus.PENDING
        )
        action_label = req_task.get_action_display()
        self.assertEqual(action_label, "Create Task")

        send_notification_email(
            recipient_user=req_task.user,
            event_type=EmailEventType.ACCESS_REQUEST_APPROVED,
            subject=f"[AetherSpace] Access Request Approved — {action_label}",
            template_name='notifications/emails/general_notification.html',
            context={
                'recipient': req_task.user,
                'actor': self.admin,
                'workspace': self.workspace,
                'title': f"Access Request Approved: {action_label}",
                'body': f"Your access request for '{action_label}' was approved.",
            }
        )
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("Create Task", body)
        self.assertNotIn("task.create", body)

        # Repeat for Bug Create
        mail.outbox = []
        req_bug = GlobalAccessRequest.objects.create(
            user=self.user,
            workspace=self.workspace,
            action=AccessRequestAction.BUG_CREATE,
            reason="Need to report defects",
            status=AccessRequestStatus.PENDING
        )
        bug_label = req_bug.get_action_display()
        self.assertEqual(bug_label, "Raise Bug")

        send_notification_email(
            recipient_user=req_bug.user,
            event_type=EmailEventType.ACCESS_REQUEST_REJECTED,
            subject=f"[AetherSpace] Access Request Rejected — {bug_label}",
            template_name='notifications/emails/general_notification.html',
            context={
                'recipient': req_bug.user,
                'actor': self.admin,
                'workspace': self.workspace,
                'title': f"Access Request Rejected: {bug_label}",
                'body': f"Your request for '{bug_label}' was rejected.",
                'reason': 'Insufficient justification.',
            }
        )
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("Raise Bug", body)
        self.assertNotIn("bug.create", body)

    def test_regression_test_8_access_request_subject(self):
        """Test 8: Access request subject has [AetherSpace] prefix and no raw enums."""
        mail.outbox = []
        action_label = "Create Task"
        subject = f"[AetherSpace] Access Request Approved — {action_label}"

        send_notification_email(
            recipient_user=self.user,
            event_type=EmailEventType.ACCESS_REQUEST_APPROVED,
            subject=subject,
            template_name='notifications/emails/general_notification.html',
            context={'title': 'Approved', 'body': 'Approved body'}
        )
        self.assertEqual(len(mail.outbox), 1)
        sent_subject = mail.outbox[0].subject
        self.assertTrue(sent_subject.startswith("[AetherSpace]"))
        self.assertIn("Create Task", sent_subject)
        self.assertNotIn("task.create", sent_subject)

    def test_regression_test_9_badge_template_rendering(self):
        """Test 9: General notification renders with badge-indigo style class defined in base template."""
        rendered = render_to_string('notifications/emails/general_notification.html', {
            'user': self.user,
            'title': 'Test Notification',
            'body': 'Badge test body',
            'app_name': 'AetherSpace',
            'site_url': 'http://127.0.0.1:8000',
            'year': 2026,
        })
        self.assertIn("badge-indigo", rendered)
        self.assertIn(".badge-indigo", rendered)
        self.assertIn("color: #818cf8;", rendered)

    def test_regression_test_10_existing_notification_preference_suppression(self):
        """Test 10: Normal optional notification remains suppressed when user disables category."""
        mail.outbox = []
        profile = self.user.profile
        profile.preferences = {'notifications': {'task_alerts': False}}
        profile.save()

        task = Task.objects.create(
            task_code='123456',
            workspace=self.workspace,
            reporter=self.admin,
            assignee=self.user,
            title='Optional Alert Task',
            status=TaskStatus.TODO,
            priority=TaskPriority.LOW
        )
        success = send_task_assigned_email(task=task, assignee=self.user, actor=self.admin)
        self.assertFalse(success)
        self.assertEqual(len(mail.outbox), 0)

        log = EmailDeliveryLog.objects.filter(
            recipient_email=self.user.email,
            event_type=EmailEventType.TASK_ASSIGNED
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, EmailDeliveryStatus.SUPPRESSED)

    def test_regression_test_11_deduplication_regression(self):
        """Test 11: Deduplication suppresses second identical email within 60s window."""
        mail.outbox = []
        subject = "[AetherSpace] Duplicate Test Notification"
        ctx = {'title': 'Duplication Check', 'body': 'Check message.'}

        first_sent = send_notification_email(
            recipient_user=self.user,
            event_type=EmailEventType.GENERAL,
            subject=subject,
            template_name='notifications/emails/general_notification.html',
            context=ctx
        )
        self.assertTrue(first_sent)
        self.assertEqual(len(mail.outbox), 1)

        # Immediate repeat within 60 seconds
        second_sent = send_notification_email(
            recipient_user=self.user,
            event_type=EmailEventType.GENERAL,
            subject=subject,
            template_name='notifications/emails/general_notification.html',
            context=ctx
        )
        self.assertFalse(second_sent)
        self.assertEqual(len(mail.outbox), 1)  # Still 1

        logs = EmailDeliveryLog.objects.filter(
            recipient_email=self.user.email,
            subject=subject
        ).order_by('sent_at')
        self.assertEqual(logs.count(), 2)
        self.assertEqual(logs[0].status, EmailDeliveryStatus.SENT)
        self.assertEqual(logs[1].status, EmailDeliveryStatus.SUPPRESSED)
        self.assertIn("deduplication window", logs[1].error_message)

    def test_regression_test_12_email_delivery_failure(self):
        """Test 12: Backend delivery failure logs FAILED in EmailDeliveryLog without throwing or leaking secrets."""
        mail.outbox = []
        with patch('django.core.mail.message.EmailMultiAlternatives.send', side_effect=Exception("SMTP Connection refused")):
            success = send_notification_email(
                recipient_user=self.user,
                event_type=EmailEventType.GENERAL,
                subject='[AetherSpace] Failure Test',
                template_name='notifications/emails/general_notification.html',
                context={'title': 'Failure Test', 'body': 'Should fail safely.'}
            )

        self.assertFalse(success)
        self.assertEqual(len(mail.outbox), 0)

        log = EmailDeliveryLog.objects.filter(
            recipient_email=self.user.email,
            subject='[AetherSpace] Failure Test'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, EmailDeliveryStatus.FAILED)
        self.assertIn("SMTP Connection refused", log.error_message)
        # Verify no credentials or secrets leaked
        self.assertNotIn("password", log.error_message.lower())
        self.assertNotIn("secret", log.error_message.lower())


class EmailDesignSystemPhaseBTests(TestCase):
    """
    Phase B Automated Test Suite for AetherSpace Central Email Design System.
    Validates rendering, responsive layout, component architecture, security escaping,
    plain-text fallbacks, and preview endpoints.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@aetherspace.dev',
            username='admin_phaseb',
            password='Password123!',
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )
        UserProfile.objects.create(user=self.admin)

        self.user = User.objects.create_user(
            email='contributor@aetherspace.dev',
            username='contrib_phaseb',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )
        UserProfile.objects.create(user=self.user)

        self.workspace = Workspace.objects.create(
            name='AetherSpace Design WS',
            slug='aetherspace-design-ws',
            owner=self.admin
        )

    def test_all_templates_dual_format_rendering(self):
        """Verify all 9 production templates render both HTML and TXT successfully."""
        from admin_panel.email_preview import get_preview_catalog, render_preview
        catalog = get_preview_catalog()

        # Minimum required template keys per specification
        required_keys = [
            'verification',
            'password_reset',
            'workspace_invite',
            'account_approved',
            'account_rejected',
            'task_assigned',
            'bug_assigned',
            'meeting_event',
            'mention_notification',
            'access_approved',
            'access_rejected',
            'general_notification',
        ]

        for key in required_keys:
            self.assertIn(key, catalog, f"Required preview key '{key}' missing from catalog.")
            html_content = render_preview(key, as_text=False)
            txt_content = render_preview(key, as_text=True)

            self.assertIsNotNone(html_content, f"Failed rendering HTML for {key}")
            self.assertIsNotNone(txt_content, f"Failed rendering TXT for {key}")
            self.assertGreater(len(html_content), 100, f"HTML for {key} is unexpectedly small")
            self.assertGreater(len(txt_content), 50, f"TXT for {key} is unexpectedly small")

    def test_shared_header_and_footer_components(self):
        """Verify standard AetherSpace branding in header and footer across templates."""
        from admin_panel.email_preview import render_preview
        html = render_preview('task_assigned', as_text=False)
        txt = render_preview('task_assigned', as_text=True)

        # Header branding - Real logo asset, no emojis
        self.assertIn("AetherSpace", html)
        self.assertIn("/static/images/logo.png", html)
        self.assertIn('alt="AetherSpace Logo"', html)
        self.assertNotIn("⚡", html)
        self.assertIn("High-Performance Agile Team Platform", html)

        self.assertIn("AETHERSPACE", txt)
        self.assertNotIn("⚡", txt)
        self.assertIn("High-Performance Agile Team Platform", txt)

        # Footer branding & notification link
        self.assertTrue("&copy; 2026 AetherSpace" in html or "© 2026 AetherSpace" in html)
        self.assertIn("notification preferences", html)
        self.assertIn("/settings/notifications/", html)
        self.assertIn("2026 AetherSpace", txt)
        self.assertIn("/settings/notifications/", txt)

    def test_bulletproof_button_component(self):
        """Verify CTA buttons render with bulletproof table wrapper and inline styles."""
        from admin_panel.email_preview import render_preview
        html = render_preview('verification', as_text=False)

        # Button structure
        self.assertIn('<table border="0" cellpadding="0" cellspacing="0" role="presentation"', html)
        self.assertIn('bgcolor="#2563eb"', html)
        self.assertIn('class="btn"', html)
        self.assertIn('Verify Email Address', html)
        self.assertIn('/auth/verify/', html)

    def test_semantic_status_badges(self):
        """Verify semantic badge styles are present without exposing internal raw enums."""
        from admin_panel.email_preview import render_preview
        task_html = render_preview('task_assigned', as_text=False)
        bug_html = render_preview('bug_assigned', as_text=False)
        invite_html = render_preview('workspace_invite', as_text=False)

        self.assertIn('badge badge-blue', task_html)
        self.assertIn('Task Assignment', task_html)
        self.assertNotIn('task.create', task_html)
        self.assertNotIn('task.assigned', task_html)

        self.assertIn('badge badge-rose', bug_html)
        self.assertIn('Defect Assignment', bug_html)

        self.assertIn('badge badge-blue', invite_html)
        self.assertIn('Workspace Invitation', invite_html)

    def test_metadata_card_component(self):
        """Verify metadata card displays formatted resource details."""
        from admin_panel.email_preview import render_preview
        task_html = render_preview('task_assigned', as_text=False)

        self.assertIn('class="metadata-card"', task_html)
        self.assertIn('Task ID', task_html)
        self.assertIn('619347', task_html)
        self.assertIn('Priority', task_html)
        self.assertTrue('High' in task_html or 'HIGH' in task_html)
        self.assertIn('AetherSpace Core', task_html)

    def test_user_content_security_escaping(self):
        """Verify untrusted user-submitted strings are strictly HTML-escaped."""
        ctx = {
            'user': self.user,
            'title': '<script>alert("xss-title")</script>',
            'body': 'Malicious payload <img src=x onerror="alert(1)"> attached.',
            'app_name': 'AetherSpace',
            'site_url': 'http://127.0.0.1:8000',
            'year': 2026,
        }
        rendered = render_to_string('emails/general_notification.html', ctx)

        # Unsafe tags MUST be escaped
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;alert(&quot;xss-title&quot;)&lt;/script&gt;', rendered)
        self.assertNotIn('<img src=x', rendered)
        self.assertIn('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;', rendered)

    def test_plain_text_cleanliness_and_no_raw_entities(self):
        """Verify plain-text contains zero HTML markup and no encoded HTML entities."""
        from admin_panel.email_preview import render_preview
        for key in ['task_assigned', 'bug_assigned', 'mention_notification', 'general_notification']:
            txt = render_preview(key, as_text=True)
            self.assertNotIn('<html>', txt)
            self.assertNotIn('<body>', txt)
            self.assertNotIn('<table', txt)
            self.assertNotIn('<div', txt)
            self.assertNotIn('<span', txt)
            self.assertNotIn('&amp;', txt)
            self.assertNotIn('&#x27;', txt)
            self.assertNotIn('&quot;', txt)
            self.assertNotIn('&lt;', txt)
            self.assertNotIn('&gt;', txt)

    def test_missing_optional_variables_graceful_handling(self):
        """Verify templates render gracefully when optional variables are omitted."""
        # Minimal context for task assignment (no actor, no due date, no description)
        task = Task(
            task_code='999999',
            title='Minimal Task',
            priority=TaskPriority.LOW,
            status=TaskStatus.TODO,
            workspace=self.workspace
        )
        ctx = {
            'task': task,
            'user': self.user,
            'action_url': '/tasks/test/',
            'site_url': 'http://127.0.0.1:8000',
            'year': 2026,
        }
        html = render_to_string('emails/task_assigned.html', ctx)
        txt = render_to_string('emails/task_assigned.txt', ctx)
        self.assertIn('Minimal Task', html)
        self.assertIn('Minimal Task', txt)

    def test_admin_preview_views_access_control(self):
        """Verify email preview views are strictly restricted to platform administrators."""
        from django.urls import reverse
        index_url = reverse('admin_panel:email_preview_index')
        detail_url = reverse('admin_panel:email_preview_detail', kwargs={'template_key': 'task_assigned'})
        render_url = reverse('admin_panel:email_preview_render', kwargs={'template_key': 'task_assigned'})

        # Anonymous user -> redirected to login
        resp = self.client.get(index_url)
        self.assertEqual(resp.status_code, 302)

        # Standard contributor -> forbidden (403)
        self.client.force_login(self.user)
        resp = self.client.get(index_url)
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get(render_url)
        self.assertEqual(resp.status_code, 403)

        # Platform Admin -> 200 OK
        self.client.force_login(self.admin)
        resp = self.client.get(index_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Central Email Design System Catalog')

        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Task Assignment')

        resp = self.client.get(render_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'AetherSpace')
        self.assertContains(resp, '/static/images/logo.png')
        self.assertNotContains(resp, '⚡')
        # Sameorigin allows iframe embedding in admin panel
        self.assertEqual(resp.headers.get('X-Frame-Options'), 'SAMEORIGIN')

    def test_admin_preview_render_embeddability_and_headers(self):
        """Verify the preview render endpoint returns 200 HTML, SAMEORIGIN, no attachment."""
        self.client.force_login(self.admin)
        render_url = reverse('admin_panel:email_preview_render', kwargs={'template_key': 'task_assigned'})
        resp = self.client.get(render_url)

        # 1. Successful HTML response
        self.assertEqual(resp.status_code, 200)
        # 2. Correct Content-Type
        self.assertEqual(resp['Content-Type'], 'text/html; charset=utf-8')
        # 3. Embeddable in authenticated admin preview context
        self.assertEqual(resp.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        # 4. Does not become a file download (no Content-Disposition)
        self.assertNotIn('Content-Disposition', resp.headers)
        # 5. References approved logo asset with SITE_URL
        self.assertContains(resp, '/static/images/logo.png')
        self.assertContains(resp, 'alt="AetherSpace Logo"')
        # 6. No emoji branding in rendered preview
        self.assertNotContains(resp, '⚡')

    @override_settings(SITE_URL='https://custom-domain.example.com')
    def test_email_logo_uses_site_url_and_approved_asset(self):
        """Verify email logo uses SITE_URL without hardcoding localhost or using emojis."""
        from admin_panel.email_preview import render_preview
        html = render_preview('task_assigned', as_text=False)
        txt = render_preview('task_assigned', as_text=True)

        # Logo asset referenced with SITE_URL
        expected_logo_src = 'https://custom-domain.example.com/static/images/logo.png'
        self.assertIn(expected_logo_src, html)
        self.assertIn('alt="AetherSpace Logo"', html)
        self.assertIn('width="36"', html)
        self.assertIn('height="36"', html)

        # No localhost in rendered HTML with production SITE_URL
        self.assertNotIn('http://127.0.0.1:8000/static/images/logo.png', html)
        self.assertNotIn('localhost', html)

        # Zero emojis in header or text
        self.assertNotIn('⚡', html)
        self.assertNotIn('⚡', txt)



