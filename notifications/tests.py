import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from tasks.models import Task, TaskStatus, TaskPriority
from files.models import StoredFile, FileCategory, FileShare, FileShareAccess
from files.services import get_workspace_storage_metrics
from chat.models import DirectMessageConversation
from chat.services import post_direct_message
from .models import Notification, NotificationCategory, NotificationType
from .services import (
    create_notification,
    mark_as_read,
    mark_as_unread,
    mark_all_as_read,
    delete_notification,
    get_user_notifications,
    get_notification_metrics,
    get_unread_count
)

User = get_user_model()


class NotificationModelAndServiceTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            email='alice@aetherspace.dev',
            password='TestPassword123!',
            first_name='Alice',
            last_name='Smith'
        )
        self.user2 = User.objects.create_user(
            email='bob@aetherspace.dev',
            password='TestPassword123!',
            first_name='Bob',
            last_name='Jones'
        )
        self.workspace_a = Workspace.objects.create(
            name='Alpha Workspace',
            owner=self.user1,
            storage_quota_mb=50
        )
        self.workspace_b = Workspace.objects.create(
            name='Beta Workspace',
            owner=self.user2,
            storage_quota_mb=100
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.user1,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.user2,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

    def test_create_notification_and_prevent_self_notification(self):
        # Self-notification should be suppressed
        self_notif = create_notification(
            recipient=self.user1,
            category=NotificationCategory.TASK,
            notification_type=NotificationType.TASK_ASSIGNED,
            title='Self Assigned Task',
            actor=self.user1,
            workspace=self.workspace_a
        )
        self.assertIsNone(self_notif)
        self.assertEqual(Notification.objects.count(), 0)

        # Notification for another user should succeed
        notif = create_notification(
            recipient=self.user2,
            category=NotificationCategory.TASK,
            notification_type=NotificationType.TASK_ASSIGNED,
            title='Task #619347 Assigned',
            body='Please review this task',
            actor=self.user1,
            workspace=self.workspace_a,
            action_url='/tasks/w/alpha-workspace/619347/'
        )
        self.assertIsNotNone(notif)
        self.assertEqual(notif.recipient, self.user2)
        self.assertEqual(notif.actor, self.user1)
        self.assertFalse(notif.is_read)
        self.assertIsNone(notif.read_at)

    def test_mark_as_read_and_unread(self):
        notif = create_notification(
            recipient=self.user2,
            category=NotificationCategory.BUG,
            notification_type=NotificationType.BUG_ASSIGNED,
            title='Bug Assigned',
            actor=self.user1,
            workspace=self.workspace_a
        )
        self.assertFalse(notif.is_read)

        # Mark as read
        success = mark_as_read(notif.id, self.user2)
        self.assertTrue(success)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)

        # Mark as unread
        success = mark_as_unread(notif.id, self.user2)
        self.assertTrue(success)
        notif.refresh_from_db()
        self.assertFalse(notif.is_read)
        self.assertIsNone(notif.read_at)

    def test_mark_all_as_read_scoped_to_workspace(self):
        # 3 notifications in workspace A
        for i in range(3):
            create_notification(
                recipient=self.user2,
                category=NotificationCategory.TASK,
                notification_type=NotificationType.TASK_ASSIGNED,
                title=f'Task A-{i}',
                actor=self.user1,
                workspace=self.workspace_a
            )
        # 2 notifications in workspace B
        for i in range(2):
            create_notification(
                recipient=self.user2,
                category=NotificationCategory.TASK,
                notification_type=NotificationType.TASK_ASSIGNED,
                title=f'Task B-{i}',
                actor=self.user1,
                workspace=self.workspace_b
            )

        self.assertEqual(get_unread_count(self.user2), 5)
        self.assertEqual(get_unread_count(self.user2, workspace=self.workspace_a), 3)

        # Mark all as read for workspace A only
        updated = mark_all_as_read(self.user2, workspace=self.workspace_a)
        self.assertEqual(updated, 3)

        self.assertEqual(get_unread_count(self.user2, workspace=self.workspace_a), 0)
        self.assertEqual(get_unread_count(self.user2, workspace=self.workspace_b), 2)
        self.assertEqual(get_unread_count(self.user2), 2)

    def test_category_filtering_and_metrics(self):
        create_notification(
            recipient=self.user2,
            category=NotificationCategory.TASK,
            notification_type=NotificationType.TASK_ASSIGNED,
            title='Task Alert',
            actor=self.user1,
            workspace=self.workspace_a
        )
        create_notification(
            recipient=self.user2,
            category=NotificationCategory.BUG,
            notification_type=NotificationType.BUG_ASSIGNED,
            title='Bug Alert',
            actor=self.user1,
            workspace=self.workspace_a
        )
        create_notification(
            recipient=self.user2,
            category=NotificationCategory.MENTION,
            notification_type=NotificationType.CHAT_MENTION,
            title='Chat Mention',
            actor=self.user1,
            workspace=self.workspace_a
        )

        metrics = get_notification_metrics(self.user2, workspace=self.workspace_a)
        self.assertEqual(metrics['total'], 3)
        self.assertEqual(metrics['unread'], 3)
        self.assertEqual(metrics['tasks'], 1)
        self.assertEqual(metrics['bugs'], 1)
        self.assertEqual(metrics['mentions'], 1)

    def test_delete_notification(self):
        notif = create_notification(
            recipient=self.user2,
            category=NotificationCategory.SYSTEM,
            notification_type=NotificationType.GENERAL,
            title='System Alert',
            actor=self.user1,
            workspace=self.workspace_a
        )
        # Other user cannot delete
        self.assertFalse(delete_notification(notif.id, self.user1))
        self.assertEqual(Notification.objects.count(), 1)

        # Recipient can delete
        self.assertTrue(delete_notification(notif.id, self.user2))
        self.assertEqual(Notification.objects.count(), 0)

    def test_workspace_storage_quota_default_and_calculation(self):
        # Default quota is 50 MB
        self.assertEqual(self.workspace_a.storage_quota_mb, 50)
        self.assertEqual(self.workspace_a.storage_quota_formatted, "50 MB")
        self.assertEqual(self.workspace_a.storage_quota_bytes, 50 * 1024 * 1024)

        # Beta workspace has 100 MB
        self.assertEqual(self.workspace_b.storage_quota_mb, 100)
        self.assertEqual(self.workspace_b.storage_quota_formatted, "100 MB")

        # Metric calculation
        metrics_a = get_workspace_storage_metrics(self.workspace_a)
        self.assertEqual(metrics_a['quota_label'], '50 MB')
        self.assertEqual(metrics_a['percentage'], 0.0)


class NotificationViewsAndWorkflowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = 'TestPassword123!'
        self.user1 = User.objects.create_user(
            email='alice.view@aetherspace.dev',
            password=self.password,
            first_name='Alice',
            last_name='Smith'
        )
        self.user2 = User.objects.create_user(
            email='bob.view@aetherspace.dev',
            password=self.password,
            first_name='Bob',
            last_name='Jones'
        )
        self.unauth_user = User.objects.create_user(
            email='eve.view@aetherspace.dev',
            password=self.password,
            first_name='Eve',
            last_name='Outsider'
        )
        self.workspace = Workspace.objects.create(
            name='Gamma Workspace',
            owner=self.user1,
            storage_quota_mb=50
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user1,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user2,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Seed initial notification
        self.notif = create_notification(
            recipient=self.user2,
            category=NotificationCategory.TASK,
            notification_type=NotificationType.TASK_ASSIGNED,
            title='Sprint 01 Task Assigned',
            body='Task 123456 requires your immediate attention',
            workspace=self.workspace,
            actor=self.user1,
            action_url='/tasks/w/gamma-workspace/123456/'
        )

    def test_notification_center_renders_across_tabs(self):
        self.client.login(email='bob.view@aetherspace.dev', password=self.password)
        
        # Router redirect
        router_url = reverse('notifications:notifications_router')
        resp = self.client.get(router_url)
        self.assertEqual(resp.status_code, 302)

        # Workspace Notification Center
        ws_url = reverse('notifications:workspace_notifications', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(ws_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Notification Center")
        self.assertContains(resp, "Sprint 01 Task Assigned")

        # Tab views
        for tab in ['all', 'unread', 'tasks', 'bugs', 'mentions']:
            resp = self.client.get(f"{ws_url}?tab={tab}")
            self.assertEqual(resp.status_code, 200)

    def test_workspace_isolation_forbidden_for_outsider(self):
        self.client.login(email='eve.view@aetherspace.dev', password=self.password)
        ws_url = reverse('notifications:workspace_notifications', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(ws_url)
        # Should be 403 Forbidden for non-member
        self.assertEqual(resp.status_code, 403)

    def test_mark_read_and_unread_actions(self):
        self.client.login(email='bob.view@aetherspace.dev', password=self.password)

        mark_url = reverse('notifications:mark_read', kwargs={'notification_id': self.notif.id})
        resp = self.client.post(mark_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.is_read)

        unmark_url = reverse('notifications:mark_unread', kwargs={'notification_id': self.notif.id})
        resp = self.client.post(unmark_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        self.notif.refresh_from_db()
        self.assertFalse(self.notif.is_read)

    def test_api_unread_notifications_endpoint(self):
        self.client.login(email='bob.view@aetherspace.dev', password=self.password)
        api_url = reverse('notifications:api_unread')
        resp = self.client.get(api_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['unread_count'], 1)
        self.assertEqual(len(data['notifications']), 1)
        self.assertEqual(data['notifications'][0]['title'], 'Sprint 01 Task Assigned')

    def test_workflow_direct_message_triggers_notification(self):
        self.client.login(email='alice.view@aetherspace.dev', password=self.password)
        
        # Start DM conversation
        conversation = DirectMessageConversation.objects.create(
            workspace=self.workspace,
            participant1=self.user1,
            participant2=self.user2
        )
        post_direct_message(conversation, self.user1, content="Hey Bob, check out the new design!")

        # Verify Bob received notification
        bob_dm_notif = Notification.objects.filter(
            recipient=self.user2,
            category=NotificationCategory.MENTION,
            notification_type=NotificationType.CHAT_DM
        ).first()

        self.assertIsNotNone(bob_dm_notif)
        self.assertIn("Alice Smith", bob_dm_notif.title)
        self.assertIn("Hey Bob", bob_dm_notif.body)

    def test_workflow_file_share_triggers_notification(self):
        self.client.login(email='alice.view@aetherspace.dev', password=self.password)

        stored_file = StoredFile.objects.create(
            workspace=self.workspace,
            uploaded_by=self.user1,
            name='Wireframe_Spec.pdf',
            original_name='Wireframe_Spec.pdf',
            storage_path='workspaces/test/file.pdf',
            category=FileCategory.DOCUMENT,
            mime_type='application/pdf',
            size_bytes=1024
        )

        share_url = reverse('files:file_share', kwargs={'slug': self.workspace.slug, 'file_id': stored_file.id})
        resp = self.client.post(share_url, {
            'user_id': str(self.user2.id),
            'access_level': FileShareAccess.VIEW
        })
        self.assertEqual(resp.status_code, 302)

        # Verify Bob received notification
        bob_file_notif = Notification.objects.filter(
            recipient=self.user2,
            category=NotificationCategory.FILE,
            notification_type=NotificationType.FILE_SHARED
        ).first()

        self.assertIsNotNone(bob_file_notif)
        self.assertIn("Wireframe_Spec.pdf", bob_file_notif.title)
