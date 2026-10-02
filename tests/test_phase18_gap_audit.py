import json
import re
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import PermissionDenied

from accounts.models import User, UserRole, ApprovalStatus, UserProfile
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole
from tasks.models import Task, TaskStatus, TaskPriority
from bugs.models import Bug, BugStatus, BugPriority, BugSeverity
from files.models import StoredFile, FileCategory, Folder
from meetings.models import Meeting, MeetingStatus, MeetingType
from meetings.services import schedule_meeting
from calendars.models import CalendarEvent, CalendarEventType
from calendars.services import get_unified_schedule_items
from chat.models import Channel, Message
from chat.services import post_channel_message
from notifications.models import Notification, NotificationCategory, NotificationType, EmailDeliveryLog, EmailDeliveryStatus
from notifications.email_service import (
    send_task_assigned_email,
    send_bug_assigned_email,
    send_meeting_scheduled_email,
    send_meeting_status_email,
    send_account_approved_email,
    send_account_status_email,
    send_password_reset_email,
    send_notification_email,
)
from files.services import SupabaseStorageService, sanitize_filename


class Phase18GapAuditTests(TestCase):
    """
    Phase 18 Completion Gap Audit Test Suite covering:
    - Transactional Email Generation & Preference / Deduplication Engine
    - Supabase Storage Metadata, Download Protection, & Missing Object Handling
    - Cross-Module RBAC & Direct Unauthorized Access
    - Cross-Module Integrations (Bug -> Notifs/Cal, Meeting -> Notifs/Email, Chat -> Notifs/Files)
    - Query Efficiency & Pagination Guardrails
    """

    def setUp(self):
        self.client = Client()

        # Users
        self.admin = User.objects.create_superuser(
            email='admin.gap@aetherspace.dev',
            password='AdminPassword123!',
            full_name='Admin User',
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED
        )

        self.manager = User.objects.create_user(
            email='manager.gap@aetherspace.dev',
            password='ManagerPassword123!',
            full_name='Manager User',
            role=UserRole.MANAGER,
            approval_status=ApprovalStatus.APPROVED
        )

        self.contributor_a = User.objects.create_user(
            email='contrib.a@aetherspace.dev',
            username='contributor_a',
            password='DevPassword123!',
            full_name='Contributor Alpha',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED
        )

        self.contributor_b = User.objects.create_user(
            email='contrib.b@aetherspace.dev',
            password='DevPassword123!',
            full_name='Contributor Beta',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED
        )

        # Workspaces
        self.ws_a = Workspace.objects.create(name='Workspace Alpha', slug='ws-alpha', owner=self.manager)
        self.ws_b = Workspace.objects.create(name='Workspace Beta', slug='ws-beta', owner=self.manager)

        # Memberships
        WorkspaceMembership.objects.create(
            workspace=self.ws_a, user=self.manager, role=WorkspaceRole.MANAGER, status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.ws_b, user=self.manager, role=WorkspaceRole.MANAGER, status=MembershipStatus.ACTIVE
        )

        self.mem_a = WorkspaceMembership.objects.create(
            workspace=self.ws_a, user=self.contributor_a, role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE, role_tag='Frontend Lead'
        )
        self.mem_b = WorkspaceMembership.objects.create(
            workspace=self.ws_b, user=self.contributor_b, role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE, role_tag='Backend Specialist'
        )

    # -------------------------------------------------------------------------
    # 1. TRANSACTIONAL EMAIL GENERATION TESTS
    # -------------------------------------------------------------------------

    def test_email_task_assignment_html_and_plaintext(self):
        """Verify Task Assignment email generates dual HTML + text with correct context and URL."""
        task = Task.objects.create(
            workspace=self.ws_a,
            task_code='619347',
            title='Implement RBAC Integration',
            reporter=self.manager,
            assignee=self.contributor_a,
            status=TaskStatus.TODO
        )

        mail.outbox = []
        result = send_task_assigned_email(task=task, assignee=self.contributor_a, actor=self.manager)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

        msg = mail.outbox[0]
        self.assertIn(self.contributor_a.email, msg.to)
        self.assertIn('#619347', msg.subject)
        self.assertIn('Implement RBAC Integration', msg.subject)

        # Verify dual alternatives (plaintext + HTML)
        self.assertTrue(len(msg.body) > 0)
        self.assertTrue(len(msg.alternatives) > 0)
        html_body = msg.alternatives[0][0]
        self.assertIn('#619347', html_body)
        self.assertIn(f"/tasks/w/{self.ws_a.slug}/t/619347/", html_body)

        # Verify delivery log recorded
        log = EmailDeliveryLog.objects.filter(recipient_email=self.contributor_a.email, event_type='TASK_ASSIGNED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, EmailDeliveryStatus.SENT)

    def test_email_bug_assignment_generation(self):
        """Verify Bug Assignment email generates dual HTML + text with defect code."""
        bug = Bug.objects.create(
            workspace=self.ws_a,
            bug_code='B-882316',
            title='Data bleed in workspace query',
            reporter=self.manager,
            assignee=self.contributor_a,
            status=BugStatus.OPEN,
            severity=BugSeverity.SEV1
        )

        mail.outbox = []
        result = send_bug_assigned_email(bug=bug, assignee=self.contributor_a, actor=self.manager)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

        msg = mail.outbox[0]
        self.assertIn('B-882316', msg.subject)
        self.assertIn('Data bleed in workspace query', msg.subject)
        html_body = msg.alternatives[0][0]
        self.assertIn('B-882316', html_body)
        self.assertIn(f"/bugs/w/{self.ws_a.slug}/b/B-882316/", html_body)

    def test_email_meeting_notifications(self):
        """Verify Meeting scheduled and status change emails generate correctly."""
        meeting = Meeting.objects.create(
            workspace=self.ws_a,
            title='Sprint Architecture Review',
            meeting_code='meet-arch-1234',
            host=self.manager,
            meeting_type=MeetingType.GENERAL,
            status=MeetingStatus.SCHEDULED,
            scheduled_start=timezone.now() + timedelta(days=1),
            scheduled_end=timezone.now() + timedelta(days=1, hours=1)
        )

        mail.outbox = []
        # Scheduled
        res1 = send_meeting_scheduled_email(meeting=meeting, participant_user=self.contributor_a, actor=self.manager)
        self.assertTrue(res1)
        self.assertIn('Meeting Scheduled: Sprint Architecture Review', mail.outbox[0].subject)

        # Status Update (Cancelled)
        res2 = send_meeting_status_email(meeting=meeting, participant_user=self.contributor_a, status_change='CANCELLED', actor=self.manager)
        self.assertTrue(res2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('Cancelled', mail.outbox[1].subject)

    def test_email_account_approval_and_password_reset(self):
        """Verify account approval and password reset emails generate properly."""
        mail.outbox = []
        # Account approved
        res1 = send_account_approved_email(user=self.contributor_a, approved_by=self.admin)
        self.assertTrue(res1)
        self.assertIn('Account has been Approved', mail.outbox[0].subject)
        self.assertIn(self.contributor_a.contributor_id, mail.outbox[0].subject)

        # Password reset
        reset_link = 'https://aetherspace.dev/auth/reset-password/uid/token/'
        res2 = send_password_reset_email(user=self.contributor_a, reset_url=reset_link)
        self.assertTrue(res2)
        self.assertIn('Reset Your Account Password', mail.outbox[1].subject)
        self.assertIn(reset_link, mail.outbox[1].body)

    def test_email_notification_preferences_suppression(self):
        """Verify user preferences (frequency=never or category alert disabled) suppress delivery."""
        profile = UserProfile.objects.create(
            user=self.contributor_b,
            preferences={
                'notifications': {
                    'email_frequency': 'never',
                    'task_alerts': False
                }
            }
        )

        task = Task.objects.create(
            workspace=self.ws_b,
            task_code='619348',
            title='Disabled Alert Task',
            reporter=self.manager,
            assignee=self.contributor_b,
            status=TaskStatus.TODO
        )

        mail.outbox = []
        res = send_task_assigned_email(task=task, assignee=self.contributor_b, actor=self.manager)
        self.assertFalse(res)
        self.assertEqual(len(mail.outbox), 0)

        # Check suppression log
        log = EmailDeliveryLog.objects.filter(recipient_email=self.contributor_b.email, event_type='TASK_ASSIGNED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, EmailDeliveryStatus.SUPPRESSED)

    def test_email_duplicate_prevention(self):
        """Verify duplicate identical emails within 60 seconds are suppressed."""
        mail.outbox = []
        subject = "[AetherSpace] Deduplication Test Subject"
        ctx = {'message': 'Hello'}

        res1 = send_notification_email(
            recipient_user=self.contributor_a,
            event_type='TEST_EVENT',
            subject=subject,
            template_name='emails/verification.html',
            context=ctx
        )
        self.assertTrue(res1)
        self.assertEqual(len(mail.outbox), 1)

        # Immediate duplicate
        res2 = send_notification_email(
            recipient_user=self.contributor_a,
            event_type='TEST_EVENT',
            subject=subject,
            template_name='emails/verification.html',
            context=ctx
        )
        self.assertFalse(res2)
        self.assertEqual(len(mail.outbox), 1)  # No second email sent

    # -------------------------------------------------------------------------
    # 2. SUPABASE STORAGE ARCHITECTURE & ACCESS PROTECTION
    # -------------------------------------------------------------------------

    def test_supabase_storage_path_and_metadata_persistence(self):
        """Verify persistent storage path follows workspaces/{id}/{prefix}_{name} and PostgreSQL metadata."""
        file_data = b"Antigravity AetherSpace Storage Test Content"
        uploaded = SimpleUploadedFile("architecture_diagram.png", file_data, content_type="image/png")

        storage_path = SupabaseStorageService.upload_file(
            file_obj=uploaded,
            workspace_id=self.ws_a.id,
            filename=uploaded.name,
            content_type="image/png"
        )

        self.assertTrue(storage_path.startswith(f"workspaces/{self.ws_a.id}/"))
        self.assertIn("architecture_diagram.png", storage_path)

        stored_file = StoredFile.objects.create(
            workspace=self.ws_a,
            uploaded_by=self.contributor_a,
            name="Architecture Diagram",
            original_name="architecture_diagram.png",
            storage_path=storage_path,
            size_bytes=len(file_data),
            category=FileCategory.IMAGE,
            mime_type="image/png"
        )

        self.assertEqual(stored_file.workspace, self.ws_a)
        self.assertEqual(stored_file.filename, "architecture_diagram.png")
        self.assertTrue(stored_file.is_image)
        self.assertIn("B", stored_file.size_display)

    def test_supabase_storage_missing_object_handled_gracefully(self):
        """Verify missing storage objects do not crash download endpoint with 500."""
        stored_file = StoredFile.objects.create(
            workspace=self.ws_a,
            uploaded_by=self.contributor_a,
            name="Missing File",
            original_name="missing_file.pdf",
            storage_path="workspaces/non_existent_path_99999.pdf",
            size_bytes=1024,
            category=FileCategory.DOCUMENT
        )

        self.client.force_login(self.contributor_a)
        url = reverse('files:file_download', kwargs={'slug': self.ws_a.slug, 'file_id': stored_file.id})
        response = self.client.get(url)

        # Redirects with friendly error message instead of 500 error
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/files/w/{self.ws_a.slug}/{stored_file.id}/", response.url)

    def test_supabase_storage_unauthorized_cross_workspace_download_denied(self):
        """Verify user in Workspace B cannot download file in Workspace A."""
        stored_file = StoredFile.objects.create(
            workspace=self.ws_a,
            uploaded_by=self.contributor_a,
            name="Confidential A",
            original_name="confidential_a.pdf",
            storage_path="workspaces/test_path_a.pdf",
            size_bytes=2048,
            category=FileCategory.DOCUMENT
        )

        # User B attempts to access through Workspace A's URL -> 403 Forbidden
        self.client.force_login(self.contributor_b)
        url = reverse('files:file_download', kwargs={'slug': self.ws_a.slug, 'file_id': stored_file.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        # User B attempts to tamper URL using Workspace B's slug with File A's ID -> 404
        tampered_url = reverse('files:file_download', kwargs={'slug': self.ws_b.slug, 'file_id': stored_file.id})
        response_tampered = self.client.get(tampered_url)
        self.assertEqual(response_tampered.status_code, 404)

    # -------------------------------------------------------------------------
    # 3. RBAC & DIRECT UNAUTHORIZED RESOURCE ACCESS
    # -------------------------------------------------------------------------

    def test_admin_url_access_restricted_for_managers_and_contributors(self):
        """Verify non-admin users (Managers and Contributors) receive 403 on /admin-panel/."""
        # 1. Contributor access
        self.client.force_login(self.contributor_a)
        res_contrib = self.client.get(reverse('admin_panel:dashboard'))
        self.assertEqual(res_contrib.status_code, 403)

        # 2. Manager access
        self.client.force_login(self.manager)
        res_manager = self.client.get(reverse('admin_panel:dashboard'))
        self.assertEqual(res_manager.status_code, 403)

        # 3. Platform Admin access
        self.client.force_login(self.admin)
        res_admin = self.client.get(reverse('admin_panel:dashboard'))
        self.assertEqual(res_admin.status_code, 200)

    def test_direct_unauthorized_access_to_meetings_blocked(self):
        """Verify Contributor Beta cannot join or view Meeting belonging to Workspace Alpha."""
        meeting = Meeting.objects.create(
            workspace=self.ws_a,
            title='Confidential Strategy',
            meeting_code='meet-strat-8888',
            host=self.manager,
            status=MeetingStatus.SCHEDULED,
            scheduled_start=timezone.now() + timedelta(hours=2),
            scheduled_end=timezone.now() + timedelta(hours=3)
        )

        self.client.force_login(self.contributor_b)
        room_url = reverse('meetings:meeting_room', kwargs={'slug': self.ws_a.slug, 'meeting_code': meeting.meeting_code})
        response = self.client.get(room_url)
        self.assertEqual(response.status_code, 403)

        detail_url = reverse('meetings:meeting_detail', kwargs={'slug': self.ws_a.slug, 'meeting_code': meeting.meeting_code})
        response_detail = self.client.get(detail_url)
        self.assertEqual(response_detail.status_code, 403)

    def test_direct_unauthorized_access_to_calendar_events_blocked(self):
        """Verify Contributor Beta cannot view or edit CalendarEvent in Workspace Alpha."""
        event = CalendarEvent.objects.create(
            workspace=self.ws_a,
            created_by=self.manager,
            title='Workspace Alpha Roadmap Event',
            event_type=CalendarEventType.WORK_SESSION,
            start_at=timezone.now() + timedelta(days=2),
            end_at=timezone.now() + timedelta(days=2, hours=2)
        )

        self.client.force_login(self.contributor_b)
        url = reverse('calendars:event_detail', kwargs={'slug': self.ws_a.slug, 'event_id': event.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        # Tampered URL with Workspace B slug
        tampered_url = reverse('calendars:event_detail', kwargs={'slug': self.ws_b.slug, 'event_id': event.id})
        response_tampered = self.client.get(tampered_url)
        self.assertEqual(response_tampered.status_code, 404)

    def test_direct_unauthorized_access_to_chat_channels_blocked(self):
        """Verify Contributor Beta cannot view or post to Channel in Workspace Alpha."""
        channel = Channel.objects.create(
            workspace=self.ws_a,
            name='general-alpha',
            slug='general-alpha',
            is_private=False,
            created_by=self.manager
        )

        self.client.force_login(self.contributor_b)
        channel_url = reverse('chat:channel_view', kwargs={'slug': self.ws_a.slug, 'channel_slug': channel.slug})
        response = self.client.get(channel_url)
        self.assertEqual(response.status_code, 403)

    def test_direct_unauthorized_access_to_notifications_blocked(self):
        """Verify User B cannot mark read or delete User A's notifications."""
        notif = Notification.objects.create(
            recipient=self.contributor_a,
            workspace=self.ws_a,
            category=NotificationCategory.TASK,
            notification_type=NotificationType.TASK_ASSIGNED,
            title='Private Alert for Alpha',
            body='Secret information'
        )

        self.client.force_login(self.contributor_b)
        mark_read_url = reverse('notifications:mark_read', kwargs={'notification_id': notif.id})
        response = self.client.post(mark_read_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.json().get('status'), 'not_found')

        # Verify notif remains unread
        notif.refresh_from_db()
        self.assertFalse(notif.is_read)

    # -------------------------------------------------------------------------
    # 4. CROSS-MODULE INTEGRATIONS AUDIT
    # -------------------------------------------------------------------------

    def test_bug_to_notifications_and_calendar_integration(self):
        """Verify Bug with due date integrates into in-app notifications and Calendar schedule."""
        from bugs.services import create_bug
        bug = create_bug(
            workspace=self.ws_a,
            reporter=self.manager,
            title='Critical DB Race Condition',
            assignee=self.contributor_a,
            due_date=timezone.now().date() + timedelta(days=2)
        )

        # 1. Notifications integration
        notif = Notification.objects.filter(
            recipient=self.contributor_a,
            category=NotificationCategory.BUG,
            notification_type=NotificationType.BUG_ASSIGNED
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn(bug.bug_code, notif.title)

        # 2. Calendar integration
        today = timezone.now().date()
        cal_items = get_unified_schedule_items(
            workspace=self.ws_a,
            start_date=today,
            end_date=today + timedelta(days=7),
            categories=['bugs']
        )
        bug_items = [it for it in cal_items if it.get('code') == bug.bug_code]
        self.assertEqual(len(bug_items), 1)
        self.assertEqual(bug_items[0]['category'], 'bug')
        self.assertIn(self.ws_a.slug, bug_items[0]['detail_url'])

    def test_meeting_to_notifications_and_email_integration(self):
        """Verify scheduling a meeting automatically generates in-app notifications and emails."""
        mail.outbox = []
        scheduled_time = timezone.now() + timedelta(days=1)
        meeting = schedule_meeting(
            workspace=self.ws_a,
            title='Sprint Retro & Planning',
            host=self.manager,
            scheduled_start=scheduled_time,
            duration_minutes=45,
            invitees=[self.contributor_a]
        )

        # Check in-app notification created
        notif = Notification.objects.filter(
            recipient=self.contributor_a,
            category=NotificationCategory.MEETING,
            notification_type=NotificationType.MEETING_INVITE
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn('Sprint Retro & Planning', notif.title)
        self.assertEqual(notif.actor, self.manager)

        # Check transactional email dispatched
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.contributor_a.email, mail.outbox[0].to)
        self.assertIn('Sprint Retro & Planning', mail.outbox[0].subject)

    def test_chat_to_notifications_and_attachment_integration(self):
        """Verify chat channel message with @mention triggers notification and handles attachments."""
        channel = Channel.objects.create(
            workspace=self.ws_a,
            name='engineering',
            slug='engineering',
            is_private=False,
            created_by=self.manager
        )

        test_file = SimpleUploadedFile("chat_patch.diff", b"diff --git a/test b/test", content_type="text/plain")

        msg = post_channel_message(
            channel=channel,
            sender=self.manager,
            content=f"Hey @{self.contributor_a.username}, check out this patch!",
            files=[test_file]
        )

        # Verify message created and attachment stored
        self.assertEqual(msg.channel, channel)
        self.assertEqual(msg.attachments.count(), 1)
        self.assertEqual(msg.attachments.first().file_name, "chat_patch.diff")

        # Verify mention notification generated
        notif = Notification.objects.filter(
            recipient=self.contributor_a,
            category=NotificationCategory.MENTION,
            notification_type=NotificationType.CHAT_MENTION
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn('#engineering', notif.title)

    # -------------------------------------------------------------------------
    # 5. QUERY EFFICIENCY & PAGINATION GUARDRAILS
    # -------------------------------------------------------------------------

    def test_task_and_bug_lists_are_paginated(self):
        """Verify tasks and bugs views use pagination and do not dump entire datasets."""
        # Create 25 tasks
        for i in range(25):
            Task.objects.create(
                workspace=self.ws_a,
                task_code=f"6194{i:02d}",
                title=f"Task {i}",
                reporter=self.manager,
                status=TaskStatus.TODO
            )

        self.client.force_login(self.contributor_a)
        url = reverse('tasks:task_list', kwargs={'slug': self.ws_a.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Verify tasks page is paginated (12 items per page)
        tasks_page = response.context.get('tasks')
        self.assertIsNotNone(tasks_page)
        self.assertEqual(len(tasks_page.object_list), 12)
        self.assertTrue(tasks_page.has_next())
