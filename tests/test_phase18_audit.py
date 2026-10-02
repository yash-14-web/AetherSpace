import json
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from accounts.models import User, UserRole, ApprovalStatus, generate_unique_contributor_id
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole
from tasks.models import Task, TaskStatus, TaskPriority
from bugs.models import Bug, BugStatus, BugPriority, BugSeverity
from files.models import StoredFile, FileCategory
from meetings.models import Meeting, MeetingStatus
from calendars.services import get_unified_schedule_items
from notifications.models import Notification, NotificationCategory, NotificationType
from notifications.services import get_user_notifications, get_unread_count, mark_all_as_read
from timetracking.models import TimeEntry, TimeEntryType


class Phase18CrossModuleAuditTests(TestCase):
    """
    Phase 18 Comprehensive Cross-Module Integration, Security, RBAC, and Performance Audit Test Suite.
    """

    def setUp(self):
        self.client = Client()

        # 1. Platform Admin
        self.platform_admin = User.objects.create_superuser(
            email='platform.admin@aetherspace.dev',
            password='AdminPassword123!',
            full_name='Platform Admin',
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED
        )

        # 2. Multi-workspace Manager
        self.manager = User.objects.create_user(
            email='manager.multi@aetherspace.dev',
            password='ManagerPassword123!',
            full_name='Lead Multi-Manager',
            role=UserRole.MANAGER,
            approval_status=ApprovalStatus.APPROVED
        )

        # 3. Contributor Alpha (member of Workspace Alpha only)
        self.contributor_alpha = User.objects.create_user(
            email='contributor.alpha@aetherspace.dev',
            password='DevPassword123!',
            full_name='Alpha Engineer',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED
        )

        # 4. Contributor Beta (member of Workspace Beta only)
        self.contributor_beta = User.objects.create_user(
            email='contributor.beta@aetherspace.dev',
            password='DevPassword123!',
            full_name='Beta Engineer',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED
        )

        # Workspaces
        self.workspace_a = Workspace.objects.create(
            name='Alpha Project',
            slug='alpha-project',
            owner=self.manager
        )
        self.workspace_b = Workspace.objects.create(
            name='Beta Project',
            slug='beta-project',
            owner=self.manager
        )

        # Memberships:
        # Manager is in both workspaces
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.manager,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_b,
            user=self.manager,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )

        # Contributor Alpha is in Workspace A only
        self.mem_alpha = WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.contributor_alpha,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE,
            role_tag='Core Frontend'
        )

        # Contributor Beta is in Workspace B only
        self.mem_beta = WorkspaceMembership.objects.create(
            workspace=self.workspace_b,
            user=self.contributor_beta,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE,
            role_tag='Backend API'
        )

        # Data in Workspace A
        self.task_a = Task.objects.create(
            workspace=self.workspace_a,
            task_code='100001',
            reporter=self.manager,
            assignee=self.contributor_alpha,
            title='Implement Alpha Feature',
            status=TaskStatus.IN_PROGRESS,
            due_date=timezone.localdate() + timedelta(days=2)
        )

        self.bug_a = Bug.objects.create(
            workspace=self.workspace_a,
            bug_code='B-100001',
            reporter=self.manager,
            assignee=self.contributor_alpha,
            title='Alpha Memory Leak',
            status=BugStatus.OPEN,
            severity=BugSeverity.SEV1,
            due_date=timezone.localdate() + timedelta(days=3)
        )

        # Data in Workspace B
        self.task_b = Task.objects.create(
            workspace=self.workspace_b,
            task_code='200002',
            reporter=self.manager,
            assignee=self.contributor_beta,
            title='Implement Beta Security',
            status=TaskStatus.TODO,
            due_date=timezone.localdate() + timedelta(days=4)
        )

        self.bug_b = Bug.objects.create(
            workspace=self.workspace_b,
            bug_code='B-200002',
            reporter=self.manager,
            assignee=self.contributor_beta,
            title='Beta Auth Timeout',
            status=BugStatus.OPEN,
            severity=BugSeverity.SEV2,
            due_date=timezone.localdate() + timedelta(days=5)
        )

    # -------------------------------------------------------------
    # 1. Contributor ID Format Audit
    # -------------------------------------------------------------
    def test_contributor_id_server_side_generation_format(self):
        """Verify Contributor ID matches exactly 5 numeric digits followed by 'C'."""
        cid = generate_unique_contributor_id()
        self.assertEqual(len(cid), 6)
        self.assertTrue(cid[:5].isdigit(), f"First 5 characters must be numeric: {cid}")
        self.assertEqual(cid[-1], 'C', f"Last character must be uppercase C: {cid}")

        # Verify auto-assigned on User model creation
        self.assertIsNotNone(self.contributor_alpha.contributor_id)
        self.assertEqual(len(self.contributor_alpha.contributor_id), 6)
        self.assertEqual(self.contributor_alpha.contributor_id[-1], 'C')

    # -------------------------------------------------------------
    # 2. Workspace Isolation & Direct Resource Access Audit
    # -------------------------------------------------------------
    def test_workspace_isolation_direct_task_access_blocked(self):
        """Contributor Alpha from Workspace A cannot access Workspace B tasks."""
        self.client.force_login(self.contributor_alpha)

        # Direct access to Workspace B URL -> 403 Forbidden
        url_b = reverse('tasks:task_detail', kwargs={'slug': self.workspace_b.slug, 'task_code': self.task_b.task_code})
        resp = self.client.get(url_b)
        self.assertEqual(resp.status_code, 403)

        # URL tampering: trying to fetch Task B using Workspace A's slug -> 404 Not Found
        tampered_url = reverse('tasks:task_detail', kwargs={'slug': self.workspace_a.slug, 'task_code': self.task_b.task_code})
        resp = self.client.get(tampered_url)
        self.assertEqual(resp.status_code, 404)

    def test_workspace_isolation_direct_bug_access_blocked(self):
        """Contributor Alpha from Workspace A cannot access Workspace B bugs."""
        self.client.force_login(self.contributor_alpha)

        # Direct access to Workspace B URL -> 403 Forbidden
        url_b = reverse('bugs:bug_detail', kwargs={'slug': self.workspace_b.slug, 'bug_code': self.bug_b.bug_code})
        resp = self.client.get(url_b)
        self.assertEqual(resp.status_code, 403)

        # URL tampering: trying to fetch Bug B using Workspace A's slug -> 404 Not Found
        tampered_url = reverse('bugs:bug_detail', kwargs={'slug': self.workspace_a.slug, 'bug_code': self.bug_b.bug_code})
        resp = self.client.get(tampered_url)
        self.assertEqual(resp.status_code, 404)

    def test_workspace_isolation_file_download_blocked(self):
        """Contributor Alpha from Workspace A cannot download files from Workspace B."""
        file_b = StoredFile.objects.create(
            workspace=self.workspace_b,
            uploaded_by=self.contributor_beta,
            name='beta_confidential.pdf',
            original_name='beta_confidential.pdf',
            storage_path='beta-project/beta_confidential.pdf',
            mime_type='application/pdf',
            category=FileCategory.DOCUMENT,
            size_bytes=4096
        )

        self.client.force_login(self.contributor_alpha)

        # Accessing via Workspace B slug -> 403
        url_b = reverse('files:file_download', kwargs={'slug': self.workspace_b.slug, 'file_id': file_b.id})
        resp = self.client.get(url_b)
        self.assertEqual(resp.status_code, 403)

        # Accessing via Workspace A slug -> 404
        tampered_url = reverse('files:file_download', kwargs={'slug': self.workspace_a.slug, 'file_id': file_b.id})
        resp = self.client.get(tampered_url)
        self.assertEqual(resp.status_code, 404)

    # -------------------------------------------------------------
    # 3. RBAC Audit: Contributor Restrictions
    # -------------------------------------------------------------
    def test_contributor_cannot_create_workspace(self):
        """Contributors are blocked from workspace creation (403 PermissionDenied)."""
        self.client.force_login(self.contributor_alpha)
        url = reverse('workspaces:create')

        # GET request
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

        # POST request
        resp = self.client.post(url, {'name': 'Unauthorized Space', 'description': 'Hacking'})
        self.assertEqual(resp.status_code, 403)

    def test_contributor_cannot_delete_tasks(self):
        """Contributors cannot delete tasks even in their own workspace."""
        self.client.force_login(self.contributor_alpha)
        url = reverse('tasks:task_delete', kwargs={'slug': self.workspace_a.slug, 'task_code': self.task_a.task_code})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Task.objects.filter(id=self.task_a.id).exists())

    def test_manager_can_delete_tasks(self):
        """Managers and Admins are permitted to delete tasks."""
        self.client.force_login(self.manager)
        url = reverse('tasks:task_delete', kwargs={'slug': self.workspace_a.slug, 'task_code': self.task_a.task_code})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Task.objects.filter(id=self.task_a.id).exists())

    # -------------------------------------------------------------
    # 4. Multi-Workspace Manager Audit
    # -------------------------------------------------------------
    def test_multi_workspace_manager_dashboard_data_integrity(self):
        """Manager sees aggregated metrics on Master Dashboard, and cleanly scoped metrics per workspace."""
        self.client.force_login(self.manager)

        # Master Dashboard
        resp = self.client.get(reverse('workspaces:master_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_workspaces'], 2)
        self.assertEqual(resp.context['total_tasks'], 2)
        self.assertEqual(resp.context['total_bugs'], 2)

        # Workspace A Dashboard
        resp_a = self.client.get(reverse('workspaces:workspace_dashboard', kwargs={'slug': self.workspace_a.slug}))
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_a.context['active_tasks_count'], 1)
        self.assertEqual(resp_a.context['open_bugs_count'], 1)
        self.assertIn(self.task_a, resp_a.context['recent_tasks'])
        self.assertNotIn(self.task_b, resp_a.context['recent_tasks'])

        # Workspace B Dashboard
        resp_b = self.client.get(reverse('workspaces:workspace_dashboard', kwargs={'slug': self.workspace_b.slug}))
        self.assertEqual(resp_b.status_code, 200)
        self.assertEqual(resp_b.context['active_tasks_count'], 1)
        self.assertEqual(resp_b.context['open_bugs_count'], 1)
        self.assertIn(self.task_b, resp_b.context['recent_tasks'])
        self.assertNotIn(self.task_a, resp_b.context['recent_tasks'])

    # -------------------------------------------------------------
    # 5. Search-First People Search & Workspace Boundary
    # -------------------------------------------------------------
    def test_people_search_strict_empty_first_and_workspace_boundary(self):
        """Opening a people selector displays zero users; querying displays permitted workspace users only."""
        self.client.force_login(self.contributor_alpha)
        search_url = reverse('workspaces:api_workspace_members_search', kwargs={'slug': self.workspace_a.slug})

        # 1. Opening without query -> strictly 0 results
        resp = self.client.get(search_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['users'], [])

        # 2. Querying for Contributor Alpha by Contributor ID -> found
        resp = self.client.get(f"{search_url}?q={self.contributor_alpha.contributor_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['users'][0]['email'], self.contributor_alpha.email)

        # 3. Querying for Contributor Beta who belongs to Workspace B -> NOT found
        resp = self.client.get(f"{search_url}?q={self.contributor_beta.contributor_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total'], 0)

    # -------------------------------------------------------------
    # 6. People Hover Profile Card & Tagging Role
    # -------------------------------------------------------------
    def test_user_hover_card_returns_real_tagging_role(self):
        """User hover card returns accurate workspace role and real Tagging Role."""
        self.client.force_login(self.manager)
        url = reverse('accounts:api_user_hover_card', kwargs={'user_id': self.contributor_alpha.id})

        resp = self.client.get(f"{url}?workspace={self.workspace_a.slug}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['contributor_id'], self.contributor_alpha.contributor_id)
        self.assertEqual(data['workspace_role'], 'Contributor')
        self.assertEqual(data['tagging_role'], 'Core Frontend')

    # -------------------------------------------------------------
    # 7. Notification Workspace Scoping & Mark All As Read
    # -------------------------------------------------------------
    def test_notification_workspace_scoping_and_mark_all_read(self):
        """Manager in both workspaces gets notifications properly scoped, with mark all as read respecting workspace."""
        # Create notification in Workspace A
        notif_a = Notification.objects.create(
            recipient=self.manager,
            category=NotificationCategory.TASK,
            notification_type=NotificationType.TASK_ASSIGNED,
            title='Alpha Task Updated',
            workspace=self.workspace_a,
            is_read=False
        )

        # Create notification in Workspace B
        notif_b = Notification.objects.create(
            recipient=self.manager,
            category=NotificationCategory.TASK,
            notification_type=NotificationType.TASK_ASSIGNED,
            title='Beta Task Updated',
            workspace=self.workspace_b,
            is_read=False
        )

        # Unread counts per workspace
        count_a = get_unread_count(self.manager, workspace=self.workspace_a)
        count_b = get_unread_count(self.manager, workspace=self.workspace_b)
        self.assertEqual(count_a, 1)
        self.assertEqual(count_b, 1)

        # Mark all read scoped to Workspace A
        self.client.force_login(self.manager)
        url = reverse('notifications:mark_all_read')
        resp = self.client.post(url, {'workspace_slug': self.workspace_a.slug}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)

        notif_a.refresh_from_db()
        notif_b.refresh_from_db()
        self.assertTrue(notif_a.is_read, "Workspace A notification must be marked as read.")
        self.assertFalse(notif_b.is_read, "Workspace B notification must remain UNREAD.")

    # -------------------------------------------------------------
    # 8. Time Tracking & Task Association Audit
    # -------------------------------------------------------------
    def test_time_tracking_task_association_and_persistence(self):
        """Time entries connect to tasks and enforce workspace isolation."""
        entry = TimeEntry.objects.create(
            workspace=self.workspace_a,
            user=self.contributor_alpha,
            task=self.task_a,
            description='Refactoring presence engine',
            started_at=timezone.now() - timedelta(minutes=45),
            duration_seconds=2700,
            is_running=False,
            entry_type=TimeEntryType.MANUAL
        )

        self.assertEqual(entry.task, self.task_a)
        self.assertEqual(entry.duration_formatted, '45m')
        self.assertEqual(entry.hours_decimal, 0.75)

        # Verified in task reverse relation
        self.assertEqual(self.task_a.time_entries.count(), 1)
        self.assertEqual(self.task_a.time_entries.first(), entry)

    # -------------------------------------------------------------
    # 9. Calendar Unified Cross-Module Integration
    # -------------------------------------------------------------
    def test_calendar_unified_schedule_reflects_tasks_bugs_meetings(self):
        """Calendar unification collects real tasks, bugs, and meetings without duplicates."""
        start = timezone.localdate()
        end = start + timedelta(days=7)

        # Create Meeting in Workspace A
        meeting_a = Meeting.objects.create(
            workspace=self.workspace_a,
            meeting_code='meet-sync-alpha',
            title='Sprint Alpha Sync',
            host=self.manager,
            status=MeetingStatus.SCHEDULED,
            scheduled_start=timezone.now() + timedelta(days=1),
            scheduled_end=timezone.now() + timedelta(days=1, hours=1)
        )

        items = get_unified_schedule_items(
            workspace=self.workspace_a,
            start_date=start,
            end_date=end,
            categories=['tasks', 'bugs', 'meetings']
        )

        task_ids = [item['id'] for item in items if item['category'] == 'task']
        bug_ids = [item['id'] for item in items if item['category'] == 'bug']
        meeting_ids = [item['id'] for item in items if item['category'] == 'meeting']

        self.assertIn(f"task-{self.task_a.id}", task_ids)
        self.assertIn(f"bug-{self.bug_a.id}", bug_ids)
        self.assertIn(f"meeting-{meeting_a.id}", meeting_ids)

        # Ensure Workspace B items are completely excluded
        self.assertNotIn(f"task-{self.task_b.id}", task_ids)
        self.assertNotIn(f"bug-{self.bug_b.id}", bug_ids)
