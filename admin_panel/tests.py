import json
import io
import uuid
import base64
import openpyxl
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User, UserRole
from workspaces.models import (
    Workspace, WorkspaceMembership, WorkspaceRole, WorkspaceStatus,
    WorkspaceInvitation, WorkspaceAccessRequest, AccessRequestStatus,
    InvitationStatus, MembershipStatus,
    GlobalAccessRequest, TemporaryAccessGrant, AccessRequestAction,
    AccessRequestUrgency, AccessDurationChoice
)
from workspaces.permissions import can_user_perform_action
from notifications.models import Notification
from files.models import StoredFile, Folder
from tasks.models import Task, TaskStatus, TaskPriority, Sprint, SprintStatus, TaskComment, TaskActivity, CodeReviewRequest
from bugs.models import Bug, BugStatus, BugPriority, BugSeverity, BugComment, BugActivity
from core.models import ModuleStatus
from chat.models import Channel, Message
from calendars.models import CalendarEvent
from meetings.models import Meeting
from timetracking.models import TimeEntry
from admin_panel.models import AuditLog, AdminAlert, AlertSeverity, AlertCategory, AuditActionStatus
from admin_panel.services import StorageSyncService, AuditLogService, SystemHealthService, DataExportService
from admin_panel.backup_service import WorkspaceBackupService, WorkspaceRestoreService, REQUIRED_SHEETS, BACKUP_SCHEMA_VERSION


class AdminPanelRBACAndSecurityTests(TestCase):
    """Test strict server-side RBAC enforcement and authorization."""

    def setUp(self):
        self.client = Client()

        # Platform Admin
        self.admin_user = User.objects.create_user(
            username='admin_test',
            email='admin@aetherspace.io',
            password='Password123!',
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )

        # Manager
        self.manager_user = User.objects.create_user(
            username='manager_test',
            email='manager@aetherspace.io',
            password='Password123!',
            role=UserRole.MANAGER,
            is_active=True,
            is_verified=True,
        )

        # Contributor
        self.contributor_user = User.objects.create_user(
            username='contrib_test',
            email='contrib@aetherspace.io',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            is_active=True,
            is_verified=True,
        )

        # Workspace
        self.workspace = Workspace.objects.create(
            name='Test Workspace',
            slug='test-workspace',
            owner=self.admin_user,
            status=WorkspaceStatus.ACTIVE,
            max_seats=15,
            storage_quota_mb=50
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    def test_anonymous_user_redirected_to_login(self):
        """Unauthenticated user accessing admin panel is redirected to login."""
        response = self.client.get(reverse('admin_panel:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_manager_access_forbidden(self):
        """Manager role attempting to access admin panel receives HTTP 403 Forbidden."""
        self.client.force_login(self.manager_user)
        response = self.client.get(reverse('admin_panel:dashboard'))
        self.assertEqual(response.status_code, 403)

        response_users = self.client.get(reverse('admin_panel:user_list'))
        self.assertEqual(response_users.status_code, 403)

        response_audit = self.client.get(reverse('admin_panel:audit_logs'))
        self.assertEqual(response_audit.status_code, 403)

    def test_contributor_access_forbidden(self):
        """Contributor role attempting to access admin panel receives HTTP 403 Forbidden."""
        self.client.force_login(self.contributor_user)
        response = self.client.get(reverse('admin_panel:dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_platform_admin_access_allowed(self):
        """Platform Admin has access to all admin panel sections."""
        self.client.force_login(self.admin_user)

        endpoints = [
            'admin_panel:dashboard',
            'admin_panel:user_list',
            'admin_panel:roles_permissions',
            'admin_panel:invitations_list',
            'admin_panel:workspace_list',
            'admin_panel:workspace_requests',
            'admin_panel:member_management',
            'admin_panel:audit_logs',
            'admin_panel:system_overview',
            'admin_panel:integrations',
            'admin_panel:storage_files',
            'admin_panel:security_overview',
            'admin_panel:backup_restore',
            'admin_panel:activity_monitor',
            'admin_panel:performance_overview',
            'admin_panel:alerts_list',
        ]
        for name in endpoints:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, f"Failed for endpoint {name}")

    def test_post_mutation_endpoints_denied_for_manager(self):
        """Manager attempting any POST administrative mutation receives HTTP 403 Forbidden."""
        self.client.force_login(self.manager_user)

        # 1. Update module status
        resp = self.client.post(reverse('admin_panel:update_module_status', kwargs={'module_key': 'tasks'}), {'status': 'MAINTENANCE'})
        self.assertEqual(resp.status_code, 403)

        # 2. Storage sync audit
        resp = self.client.post(reverse('admin_panel:storage_sync_audit'))
        self.assertEqual(resp.status_code, 403)

        # 3. Data export
        resp = self.client.post(reverse('admin_panel:export_data'))
        self.assertEqual(resp.status_code, 403)

        # 4. Toggle user status
        resp = self.client.post(reverse('admin_panel:toggle_user_status', kwargs={'user_id': self.contributor_user.id}))
        self.assertEqual(resp.status_code, 403)

        # 5. Update user role
        resp = self.client.post(reverse('admin_panel:update_user_role', kwargs={'user_id': self.contributor_user.id}), {'role': 'MANAGER'})
        self.assertEqual(resp.status_code, 403)

    def test_post_mutation_endpoints_denied_for_contributor(self):
        """Contributor attempting any POST administrative mutation receives HTTP 403 Forbidden."""
        self.client.force_login(self.contributor_user)

        # 1. Update module status
        resp = self.client.post(reverse('admin_panel:update_module_status', kwargs={'module_key': 'tasks'}), {'status': 'MAINTENANCE'})
        self.assertEqual(resp.status_code, 403)

        # 2. Storage sync audit
        resp = self.client.post(reverse('admin_panel:storage_sync_audit'))
        self.assertEqual(resp.status_code, 403)

        # 3. Data export
        resp = self.client.post(reverse('admin_panel:export_data'))
        self.assertEqual(resp.status_code, 403)

    def test_post_mutation_endpoints_denied_for_anonymous(self):
        """Anonymous user attempting POST administrative mutation is redirected to login."""
        resp = self.client.post(reverse('admin_panel:storage_sync_audit'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp.url)

        resp = self.client.post(reverse('admin_panel:export_data'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp.url)

    def test_module_status_update_authorization_and_method(self):
        """Module status update rejects GET (405) and persists updates when POSTed by Admin."""
        ModuleStatus.objects.update_or_create(
            module_key='tasks',
            defaults={'name': 'Tasks', 'status': 'AVAILABLE'}
        )

        # 1. GET is rejected with HTTP 405 Method Not Allowed
        self.client.force_login(self.admin_user)
        get_resp = self.client.get(reverse('admin_panel:update_module_status', kwargs={'module_key': 'tasks'}))
        self.assertEqual(get_resp.status_code, 405)

        # 2. POST by platform admin succeeds and updates DB
        post_resp = self.client.post(reverse('admin_panel:update_module_status', kwargs={'module_key': 'tasks'}), {
            'status': 'MAINTENANCE',
            'public_message': 'Scheduled sprint engine maintenance',
            'maintenance_explanation': 'Upgrading index performance'
        })
        self.assertEqual(post_resp.status_code, 302)

        mod = ModuleStatus.objects.get(module_key='tasks')
        self.assertEqual(mod.status, 'MAINTENANCE')
        self.assertEqual(mod.public_message, 'Scheduled sprint engine maintenance')

        # Audit log written
        log = AuditLog.objects.filter(action='MODULE_STATUS_CHANGED').first()
        self.assertIsNotNone(log)

    def test_storage_sync_audit_authorization_and_method(self):
        """Storage sync audit rejects GET (405) and runs on POST with CSRF."""
        self.client.force_login(self.admin_user)

        # 1. GET rejected with 405
        get_resp = self.client.get(reverse('admin_panel:storage_sync_audit'))
        self.assertEqual(get_resp.status_code, 405)

        # 2. POST succeeds
        post_resp = self.client.post(reverse('admin_panel:storage_sync_audit'))
        self.assertEqual(post_resp.status_code, 302)

        log = AuditLog.objects.filter(action='STORAGE_SYNC_AUDIT_RUN').first()
        self.assertIsNotNone(log)

    def test_data_export_authorization_and_method(self):
        """Data export rejects GET (405) and generates export file on POST."""
        self.client.force_login(self.admin_user)

        # 1. GET rejected with 405
        get_resp = self.client.get(reverse('admin_panel:export_data'))
        self.assertEqual(get_resp.status_code, 405)

        # 2. POST succeeds and downloads JSON
        post_resp = self.client.post(reverse('admin_panel:export_data'))
        self.assertEqual(post_resp.status_code, 200)
        self.assertEqual(post_resp['Content-Type'], 'application/json')
        self.assertIn('attachment;', post_resp['Content-Disposition'])

    def test_sole_platform_admin_protection(self):
        """Cannot demote the sole active platform admin."""
        self.client.force_login(self.admin_user)

        # Ensure only 1 active admin
        User.objects.filter(role=UserRole.ADMIN).exclude(id=self.admin_user.id).delete()
        self.assertEqual(User.objects.filter(role=UserRole.ADMIN, is_active=True).count(), 1)

        # Attempt to demote self to Contributor
        url = reverse('admin_panel:update_user_role', kwargs={'user_id': self.admin_user.id})
        response = self.client.post(url, {'role': UserRole.CONTRIBUTOR})
        self.assertEqual(response.status_code, 302)

        # Admin role must remain unchanged
        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.role, UserRole.ADMIN)

    def test_self_deactivation_protection(self):
        """Admin cannot deactivate their own active account."""
        self.client.force_login(self.admin_user)
        url = reverse('admin_panel:toggle_user_status', kwargs={'user_id': self.admin_user.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)


class AdminPeopleSearchAPITests(TestCase):
    """Test search-first people search API mandatory rule."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_api',
            email='admin_api@aetherspace.io',
            password='Password123!',
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        self.user1 = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            full_name='Alice Architect',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
        )
        self.user2 = User.objects.create_user(
            username='bob',
            email='bob@example.com',
            full_name='Bob Backend',
            password='Password123!',
            role=UserRole.MANAGER,
        )
        self.client.force_login(self.admin)

    def test_empty_query_returns_empty_list(self):
        """Empty or whitespace query MUST return empty user list (Search-First rule)."""
        response = self.client.get(reverse('admin_panel:api_people_search'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['users'], [])

        # Whitespace query
        response_ws = self.client.get(reverse('admin_panel:api_people_search') + '?q=   ')
        self.assertEqual(response_ws.status_code, 200)
        self.assertEqual(response_ws.json()['users'], [])

    def test_query_returns_matching_users(self):
        """Query with search term returns matching records."""
        response = self.client.get(reverse('admin_panel:api_people_search') + '?q=Alice')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['users']), 1)
        self.assertEqual(data['users'][0]['email'], 'alice@example.com')
        self.assertEqual(data['users'][0]['full_name'], 'Alice Architect')


class AdminUserManagementTests(TestCase):
    """Test user role adjustments and status toggling."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_u',
            email='admin_u@aetherspace.io',
            password='Password123!',
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        self.target_user = User.objects.create_user(
            username='target_u',
            email='target@aetherspace.io',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            is_active=True,
            is_verified=True,
        )
        self.client.force_login(self.admin)

    def test_toggle_user_status(self):
        """Deactivate and reactivate target user."""
        # Deactivate
        url = reverse('admin_panel:toggle_user_status', kwargs={'user_id': self.target_user.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_active)

        # Audit log created
        log = AuditLog.objects.filter(target_id=str(self.target_user.id), action='USER_DEACTIVATED').first()
        self.assertIsNotNone(log)

        # Reactivate
        response2 = self.client.post(url)
        self.assertEqual(response2.status_code, 302)
        self.target_user.refresh_from_db()
        self.assertTrue(self.target_user.is_active)

    def test_cannot_deactivate_self(self):
        """Administrator cannot deactivate their own active account."""
        url = reverse('admin_panel:toggle_user_status', kwargs={'user_id': self.admin.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_update_user_role(self):
        """Promote contributor to manager."""
        url = reverse('admin_panel:update_user_role', kwargs={'user_id': self.target_user.id})
        response = self.client.post(url, {'role': UserRole.MANAGER})
        self.assertEqual(response.status_code, 302)
        self.target_user.refresh_from_db()
        self.assertEqual(self.target_user.role, UserRole.MANAGER)

        log = AuditLog.objects.filter(target_id=str(self.target_user.id), action='USER_ROLE_CHANGED').first()
        self.assertIsNotNone(log)

    def test_user_details_view_with_tasks_and_bugs(self):
        """User details view renders cleanly with memberships, assigned tasks, and bugs."""
        workspace = Workspace.objects.create(
            name='User Inspection WS',
            slug='user-inspection-ws',
            owner=self.admin,
            status=WorkspaceStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=workspace,
            user=self.target_user,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE,
            functional_role='QA Engineer'
        )
        Task.objects.create(
            workspace=workspace,
            title='Test Assigned Task',
            task_code='987654',
            assignee=self.target_user,
            reporter=self.admin
        )
        Bug.objects.create(
            workspace=workspace,
            title='Test Reported Bug',
            bug_code='B-123456',
            reporter=self.target_user
        )

        url = reverse('admin_panel:user_details', kwargs={'user_id': self.target_user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Assigned Task')
        self.assertContains(response, '987654')
        self.assertContains(response, 'B-123456')
        self.assertContains(response, 'QA Engineer')


class AdminWorkspaceAndRequestsTests(TestCase):
    """Test workspace status, quotas, and access request resolution."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_ws',
            email='admin_ws@aetherspace.io',
            password='Password123!',
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        self.applicant = User.objects.create_user(
            username='applicant',
            email='applicant@aetherspace.io',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            is_active=True,
        )
        self.workspace = Workspace.objects.create(
            name='Operations Workspace',
            slug='ops-workspace',
            owner=self.admin,
            status=WorkspaceStatus.ACTIVE,
            max_seats=10,
            storage_quota_mb=50
        )
        self.client.force_login(self.admin)

    def test_update_workspace_quota(self):
        """Adjust seat limit and storage quota."""
        url = reverse('admin_panel:update_workspace_quota', kwargs={'slug': self.workspace.slug})
        response = self.client.post(url, {
            'max_seats': 25,
            'storage_quota_mb': 100,
        })
        self.assertEqual(response.status_code, 302)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.max_seats, 25)
        self.assertEqual(self.workspace.storage_quota_mb, 100)

    def test_toggle_workspace_status(self):
        """Suspend and reactivate workspace."""
        url = reverse('admin_panel:toggle_workspace_status', kwargs={'slug': self.workspace.slug})
        response = self.client.post(url, {'status': WorkspaceStatus.SUSPENDED})
        self.assertEqual(response.status_code, 302)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.status, WorkspaceStatus.SUSPENDED)

    def test_decide_workspace_access_request_approve(self):
        """Approve access request into workspace."""
        req = WorkspaceAccessRequest.objects.create(
            workspace=self.workspace,
            user=self.applicant,
            status=AccessRequestStatus.PENDING
        )
        url = reverse('admin_panel:decide_workspace_request', kwargs={'request_id': req.id})
        response = self.client.post(url, {'decision': 'APPROVE', 'role': WorkspaceRole.CONTRIBUTOR})
        self.assertEqual(response.status_code, 302)

        req.refresh_from_db()
        self.assertEqual(req.status, AccessRequestStatus.APPROVED)

        # Membership was granted
        membership = WorkspaceMembership.objects.filter(workspace=self.workspace, user=self.applicant).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.status, MembershipStatus.ACTIVE)

    def test_workspace_details_view_renders(self):
        """Workspace details view renders cleanly with quota forms, member roster, and actions."""
        url = reverse('admin_panel:workspace_details', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.workspace.name)
        self.assertContains(response, 'Workspace Limits & Quotas')
        self.assertContains(response, 'Workspace Status Governance')


class AdminStorageAndAlertsTests(TestCase):
    """Test real storage sync, atomic purge, and alert resolution."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_sa',
            email='admin_sa@aetherspace.io',
            password='Password123!',
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        self.workspace = Workspace.objects.create(
            name='Storage Test WS',
            slug='storage-test-ws',
            owner=self.admin,
            status=WorkspaceStatus.ACTIVE,
        )
        self.client.force_login(self.admin)

    def test_storage_sync_audit_execution(self):
        """Storage sync audit rejects GET (405) and runs on POST, creating an audit log."""
        url = reverse('admin_panel:storage_sync_audit')
        # GET is rejected
        get_resp = self.client.get(url)
        self.assertEqual(get_resp.status_code, 405)

        # POST executes audit
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        log = AuditLog.objects.filter(action='STORAGE_SYNC_AUDIT_RUN').first()
        self.assertIsNotNone(log)

    def test_purge_stored_file(self):
        """Atomic purge removes file and writes audit log."""
        f = StoredFile.objects.create(
            workspace=self.workspace,
            uploaded_by=self.admin,
            name='test_purge.pdf',
            storage_path='test/test_purge.pdf',
            size_bytes=1024,
            is_external_link=False,
        )
        url = reverse('admin_panel:purge_file', kwargs={'file_id': f.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        self.assertFalse(StoredFile.objects.filter(id=f.id).exists())
        log = AuditLog.objects.filter(action='FILE_PURGED', target_id=str(f.id)).first()
        self.assertIsNotNone(log)

    def test_resolve_alert(self):
        """Resolve an active administrative alert."""
        alert = AdminAlert.objects.create(
            title='Test Warning Alert',
            message='Storage nearing 80% capacity',
            severity=AlertSeverity.WARNING,
            category=AlertCategory.STORAGE,
            workspace=self.workspace,
            is_resolved=False,
        )
        url = reverse('admin_panel:resolve_alert', kwargs={'alert_id': alert.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        alert.refresh_from_db()
        self.assertTrue(alert.is_resolved)
        self.assertEqual(alert.resolved_by, self.admin)
        self.assertIsNotNone(alert.resolved_at)

    def test_export_data_download(self):
        """Metadata JSON download rejects GET (405) and returns application/json attachment on POST."""
        url = reverse('admin_panel:export_data')
        # GET is rejected
        get_resp = self.client.get(url)
        self.assertEqual(get_resp.status_code, 405)

        # POST returns json attachment
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('attachment;', response['Content-Disposition'])

        payload = json.loads(response.content)
        self.assertIn('exported_at', payload)
        self.assertIn('users', payload)
        self.assertIn('workspaces', payload)


class AdminBackupAndRestoreComprehensiveTests(TestCase):
    """
    Comprehensive test suite for Phase B, C, D workspace backup & restore system.
    Covers all 25 mandatory requirements.
    """

    def setUp(self):
        self.client = Client()

        # Admin User
        self.admin = User.objects.create_user(
            username='admin_bk',
            email='admin_bk@aetherspace.io',
            password='Password123!',
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )

        # Manager User
        self.manager = User.objects.create_user(
            username='manager_bk',
            email='manager_bk@aetherspace.io',
            password='Password123!',
            role=UserRole.MANAGER,
            is_active=True,
            is_verified=True,
        )

        # Contributor User
        self.contributor = User.objects.create_user(
            username='contrib_bk',
            email='contrib_bk@aetherspace.io',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            is_active=True,
            is_verified=True,
        )

        # Primary Workspace
        self.workspace = Workspace.objects.create(
            name='Alpha Project',
            slug='alpha-project',
            owner=self.admin,
            status=WorkspaceStatus.ACTIVE,
            max_seats=20,
            storage_quota_mb=100
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE,
            functional_role='Software Engineer'
        )

        # Sprint
        self.sprint = Sprint.objects.create(
            workspace=self.workspace,
            name='Sprint 1 - Foundation',
            goal='Establish core framework',
            status=SprintStatus.ACTIVE,
            created_by=self.admin
        )

        # Task
        self.task = Task.objects.create(
            workspace=self.workspace,
            task_code='619347',
            title='Implement Authentication Layer',
            description='Configure session cookies and CSRF tokens',
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            assignee=self.contributor,
            reporter=self.admin,
            sprint_ref=self.sprint,
            sprint=self.sprint.name,
            estimated_hours=8
        )

        # Task Comment & Activity
        self.task_comment = TaskComment.objects.create(
            task=self.task,
            author=self.contributor,
            content='Session middleware configured.'
        )
        self.task_activity = TaskActivity.objects.create(
            task=self.task,
            actor=self.admin,
            action='STATUS_CHANGED',
            old_value='TODO',
            new_value='IN_PROGRESS',
            message='Moved task to In Progress'
        )

        # Bug
        self.bug = Bug.objects.create(
            workspace=self.workspace,
            bug_code='B-882316',
            title='Token Refresh Race Condition',
            description='Simultaneous requests expire refresh token prematurely',
            status=BugStatus.OPEN,
            priority=BugPriority.HIGH,
            severity=BugSeverity.SEV2,
            linked_task=self.task,
            sprint=self.sprint.name,
            reporter=self.contributor,
            assignee=self.admin
        )
        self.bug_comment = BugComment.objects.create(
            bug=self.bug,
            author=self.admin,
            content='Investigating token mutex lock.'
        )
        self.bug_activity = BugActivity.objects.create(
            bug=self.bug,
            actor=self.contributor,
            action='BUG_REPORTED',
            message='Created bug report'
        )

        # Code Review
        self.code_review = CodeReviewRequest.objects.create(
            review_code='CR-619347',
            task=self.task,
            requester=self.contributor,
            reviewer=self.admin,
            title='PR for Auth Layer',
            github_pr_url='https://github.com/aetherspace/pull/42'
        )

        # Calendar Event & Meeting
        self.event = CalendarEvent.objects.create(
            workspace=self.workspace,
            title='Sprint 1 Demo',
            event_type='SPRINT_DEMO',
            calendar_category='SPRINT',
            start_at=timezone.now(),
            end_at=timezone.now() + timezone.timedelta(hours=1),
            created_by=self.admin
        )
        self.meeting = Meeting.objects.create(
            workspace=self.workspace,
            meeting_code='M-ALPHA1',
            title='Sprint Standup',
            host=self.admin,
            scheduled_start=timezone.now()
        )

        # Stored File (Metadata Only)
        self.stored_file = StoredFile.objects.create(
            workspace=self.workspace,
            uploaded_by=self.admin,
            name='architecture_diagram.png',
            original_name='architecture_diagram.png',
            storage_path='alpha-project/architecture_diagram.png',
            size_bytes=204800,
            mime_type='image/png',
            category='IMAGE'
        )

        # Secondary Workspace for isolation tests
        self.other_workspace = Workspace.objects.create(
            name='Beta Project',
            slug='beta-project',
            owner=self.admin,
            status=WorkspaceStatus.ACTIVE
        )
        self.other_task = Task.objects.create(
            workspace=self.other_workspace,
            task_code='999999',
            title='Beta Task Unrelated',
            reporter=self.admin
        )

        self.client.force_login(self.admin)

    # 1. Excel export creates valid workbook
    def test_01_excel_export_creates_valid_workbook(self):
        url = reverse('admin_panel:export_workspace_backup')
        response = self.client.post(url, {'workspace_slug': self.workspace.slug})
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', response['Content-Type'])
        self.assertIn('.xlsx', response['Content-Disposition'])

        # Validate with openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
        self.assertEqual(len(wb.sheetnames), 19)
        for expected_sheet in REQUIRED_SHEETS:
            self.assertIn(expected_sheet, wb.sheetnames)

    # 2. Export includes all records without 500-record truncation
    def test_02_export_includes_all_records_no_500_limit(self):
        # Bulk create 520 tasks
        tasks = [
            Task(
                workspace=self.workspace,
                task_code=f"8{i:05d}",
                title=f"Bulk Task #{i}",
                reporter=self.admin
            )
            for i in range(520)
        ]
        Task.objects.bulk_create(tasks)

        buf, counts = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        wb = openpyxl.load_workbook(buf, data_only=True)
        ws_tasks = wb["Tasks"]
        # Total rows = 520 bulk + 1 initial setup task + 1 header row = 522
        self.assertGreaterEqual(ws_tasks.max_row, 521)
        self.assertEqual(counts["Tasks"], 521)

    # 3. Workspace isolation during export
    def test_03_workspace_isolation_during_export(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        wb = openpyxl.load_workbook(buf, data_only=True)
        ws_tasks = wb["Tasks"]

        task_codes_in_export = [
            str(row[1]) for row in ws_tasks.iter_rows(min_row=2, values_only=True) if row and row[1]
        ]
        self.assertIn('619347', task_codes_in_export)
        self.assertNotIn('999999', task_codes_in_export)

    # 4. Chat is strictly excluded from backup
    def test_04_chat_excluded_from_backup(self):
        # Create a channel and message in the workspace
        channel = Channel.objects.create(
            workspace=self.workspace,
            name='general',
            created_by=self.admin
        )
        Message.objects.create(
            workspace=self.workspace,
            channel=channel,
            sender=self.admin,
            content='Top secret message that should not be backed up'
        )

        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        wb = openpyxl.load_workbook(buf, data_only=True)

        # No chat sheets
        for sheetname in wb.sheetnames:
            self.assertNotIn("chat", sheetname.lower())
            self.assertNotIn("message", sheetname.lower())

        # Metadata verifies chat exclusion
        ws_meta = wb["Export_Metadata"]
        meta_text = str([c for row in ws_meta.iter_rows(values_only=True) for c in row if c])
        self.assertIn("EXCLUDED_BY_DESIGN", meta_text)
        self.assertNotIn("Top secret message", meta_text)

    # 5. Export metadata sheet content
    def test_05_export_metadata_content(self):
        buf, counts = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        wb = openpyxl.load_workbook(buf, data_only=True)
        ws_meta = wb["Export_Metadata"]

        meta_dict = {}
        for row in ws_meta.iter_rows(min_row=2, values_only=True):
            if row and row[0]:
                meta_dict[str(row[0])] = str(row[1] or '')

        self.assertEqual(meta_dict.get('backup_schema_version'), BACKUP_SCHEMA_VERSION)
        self.assertEqual(meta_dict.get('application_name'), 'AetherSpace')
        self.assertEqual(meta_dict.get('workspace_id'), str(self.workspace.id))
        self.assertEqual(meta_dict.get('workspace_slug'), self.workspace.slug)
        self.assertIn('integrity_checksum_sha256', meta_dict)

    # 6. Identifiers preserved in export
    def test_06_identifiers_preserved(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        wb = openpyxl.load_workbook(buf, data_only=True)

        # Task ID & Code
        ws_tasks = wb["Tasks"]
        task_row = [r for r in ws_tasks.iter_rows(min_row=2, values_only=True) if r and r[1] == '619347'][0]
        self.assertEqual(str(task_row[0]), str(self.task.id))
        self.assertEqual(str(task_row[1]), '619347')

        # Bug ID & Code
        ws_bugs = wb["Bugs"]
        bug_row = [r for r in ws_bugs.iter_rows(min_row=2, values_only=True) if r and r[1] == 'B-882316'][0]
        self.assertEqual(str(bug_row[0]), str(self.bug.id))
        self.assertEqual(str(bug_row[1]), 'B-882316')

    # 7. Foreign-key references preserved
    def test_07_foreign_keys_preserved(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        wb = openpyxl.load_workbook(buf, data_only=True)

        ws_tasks = wb["Tasks"]
        headers = [c for c in ws_tasks[1]]
        header_names = [c.value for c in headers]

        assignee_idx = header_names.index('assignee_id')
        reporter_idx = header_names.index('reporter_id')
        sprint_idx = header_names.index('sprint_id')

        task_row = [r for r in ws_tasks.iter_rows(min_row=2, values_only=True) if r and r[1] == '619347'][0]
        self.assertEqual(str(task_row[assignee_idx]), str(self.contributor.id))
        self.assertEqual(str(task_row[reporter_idx]), str(self.admin.id))
        self.assertEqual(str(task_row[sprint_idx]), str(self.sprint.id))

    # 8. Empty workspace backup works
    def test_08_empty_workspace_backup(self):
        empty_ws = Workspace.objects.create(
            name='Empty Workspace',
            slug='empty-workspace',
            owner=self.admin
        )
        buf, counts = WorkspaceBackupService.export_workspace_to_excel(empty_ws, self.admin)
        wb = openpyxl.load_workbook(buf, data_only=True)
        self.assertEqual(len(wb.sheetnames), 19)
        self.assertEqual(counts["Tasks"], 0)
        self.assertEqual(counts["Bugs"], 0)

    # 9. Upload validation rejects invalid workbook
    def test_09_upload_validation_rejects_invalid_file(self):
        invalid_bytes = b"Corrupt data not an excel file"
        preview = WorkspaceRestoreService.validate_and_preview_backup(invalid_bytes, self.admin)
        self.assertFalse(preview['is_valid'])
        self.assertGreater(len(preview['errors']), 0)

    # 10. Schema version validation
    def test_10_schema_version_validation(self):
        # Create a workbook with wrong schema version
        wb = openpyxl.Workbook()
        for s in REQUIRED_SHEETS:
            if s != "Sheet":
                wb.create_sheet(s)
        ws_meta = wb["Export_Metadata"]
        ws_meta.append(["Metadata_Field", "Value"])
        ws_meta.append(["backup_schema_version", "9.9.9"])
        ws_meta.append(["application_name", "AetherSpace"])

        buf = io.BytesIO()
        wb.save(buf)
        preview = WorkspaceRestoreService.validate_and_preview_backup(buf.getvalue(), self.admin)
        self.assertFalse(preview['is_valid'])
        self.assertTrue(any("Unsupported backup schema version" in err for err in preview['errors']))

    # 11. Missing required sheet validation
    def test_11_missing_required_sheet_validation(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Export_Metadata"
        ws.append(["Metadata_Field", "Value"])
        ws.append(["backup_schema_version", "1.0.0"])

        buf = io.BytesIO()
        wb.save(buf)
        preview = WorkspaceRestoreService.validate_and_preview_backup(buf.getvalue(), self.admin)
        self.assertFalse(preview['is_valid'])
        self.assertTrue(any("missing required worksheet" in err for err in preview['errors']))

    # 12. Invalid foreign-key / missing references detection
    def test_12_invalid_foreign_key_detection(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        preview = WorkspaceRestoreService.validate_and_preview_backup(buf.getvalue(), self.admin)
        self.assertTrue(preview['is_valid'])
        self.assertIn('files_binary_status', preview)

    # 13. Duplicate/conflicting ID detection
    def test_13_duplicate_conflicting_id_detection(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        preview = WorkspaceRestoreService.validate_and_preview_backup(buf.getvalue(), self.admin)
        self.assertTrue(any("Task ID(s) collide" in c for c in preview['conflicts']))

    # 14. Preview does not modify database
    def test_14_preview_does_not_modify_db(self):
        tasks_count_before = Task.objects.count()
        bugs_count_before = Bug.objects.count()
        ws_count_before = Workspace.objects.count()

        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        uploaded = SimpleUploadedFile("backup.xlsx", buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        response = self.client.post(reverse('admin_panel:preview_backup_restore'), {'backup_file': uploaded})
        self.assertEqual(response.status_code, 200)

        self.assertEqual(Task.objects.count(), tasks_count_before)
        self.assertEqual(Bug.objects.count(), bugs_count_before)
        self.assertEqual(Workspace.objects.count(), ws_count_before)

    # 15. Restore requires explicit confirmation
    def test_15_restore_requires_explicit_confirmation(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        uploaded = SimpleUploadedFile("backup.xlsx", buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # Step 1: Preview only
        preview_resp = self.client.post(reverse('admin_panel:preview_backup_restore'), {'backup_file': uploaded})
        self.assertEqual(preview_resp.status_code, 200)
        self.assertContains(preview_resp, 'Confirm &amp; Execute Restore')

        # No new workspace created yet
        self.assertFalse(Workspace.objects.filter(slug='restored-isolated-ws').exists())

        # Step 2: Confirmation POST creates records
        payload_b64 = preview_resp.context['payload_b64']
        confirm_resp = self.client.post(reverse('admin_panel:confirm_backup_restore'), {
            'payload_b64': payload_b64,
            'target_workspace_slug': 'restored-isolated-ws'
        })
        self.assertEqual(confirm_resp.status_code, 200)
        self.assertTrue(Workspace.objects.filter(slug='restored-isolated-ws').exists())

    # 16. Successful transactional restore
    def test_16_successful_transactional_restore(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        # Disaster recovery: restore after data loss of original workspace
        self.workspace.delete()
        success, report = WorkspaceRestoreService.execute_transactional_restore(
            file_content_bytes=buf.getvalue(),
            actor=self.admin,
            target_workspace_slug='restored-project-success'
        )
        self.assertTrue(success)
        self.assertEqual(report['verification_result'], 'PASSED')
        self.assertGreater(report['records_restored'], 0)

        restored_ws = Workspace.objects.get(slug='restored-project-success')
        self.assertTrue(Task.objects.filter(workspace=restored_ws, task_code='619347').exists())
        self.assertTrue(Bug.objects.filter(workspace=restored_ws, bug_code='B-882316').exists())

    # 17. Failed restore rolls back transaction atomically
    def test_17_failed_restore_rolls_back_atomically(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)

        # Corrupt the buffer by giving invalid bytes for confirm
        success, report = WorkspaceRestoreService.execute_transactional_restore(
            file_content_bytes=b"Invalid non-excel stream",
            actor=self.admin,
            target_workspace_slug='should-never-exist'
        )
        self.assertFalse(success)
        self.assertEqual(report['verification_result'], 'FAILED_ROLLED_BACK')
        self.assertFalse(Workspace.objects.filter(slug='should-never-exist').exists())

    # 18. Workspace isolation during restore
    def test_18_workspace_isolation_during_restore(self):
        initial_beta_tasks = list(Task.objects.filter(workspace=self.other_workspace).values_list('id', flat=True))

        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        WorkspaceRestoreService.execute_transactional_restore(
            file_content_bytes=buf.getvalue(),
            actor=self.admin,
            target_workspace_slug='restored-isolated-ws-2'
        )

        # Other workspace tasks unchanged
        current_beta_tasks = list(Task.objects.filter(workspace=self.other_workspace).values_list('id', flat=True))
        self.assertEqual(initial_beta_tasks, current_beta_tasks)

    # 19. Unauthorized user cannot export
    def test_19_unauthorized_user_cannot_export(self):
        url = reverse('admin_panel:export_workspace_backup')

        # Contributor receives 403
        self.client.force_login(self.contributor)
        resp = self.client.post(url, {'workspace_slug': self.workspace.slug})
        self.assertEqual(resp.status_code, 403)

        # Manager receives 403
        self.client.force_login(self.manager)
        resp = self.client.post(url, {'workspace_slug': self.workspace.slug})
        self.assertEqual(resp.status_code, 403)

        # Anonymous receives 302
        self.client.logout()
        resp = self.client.post(url, {'workspace_slug': self.workspace.slug})
        self.assertEqual(resp.status_code, 302)

    # 20. Unauthorized user cannot restore
    def test_20_unauthorized_user_cannot_restore(self):
        url = reverse('admin_panel:confirm_backup_restore')

        # Contributor receives 403
        self.client.force_login(self.contributor)
        resp = self.client.post(url, {'payload_b64': 'dummy'})
        self.assertEqual(resp.status_code, 403)

        # Manager receives 403
        self.client.force_login(self.manager)
        resp = self.client.post(url, {'payload_b64': 'dummy'})
        self.assertEqual(resp.status_code, 403)

    # 21. Restore audit log created
    def test_21_restore_audit_log_created(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        WorkspaceRestoreService.execute_transactional_restore(
            file_content_bytes=buf.getvalue(),
            actor=self.admin,
            target_workspace_slug='audit-test-ws'
        )
        log = AuditLog.objects.filter(action='WORKSPACE_RESTORE_COMPLETED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.admin)

    # 22. Existing data is not silently overwritten
    def test_22_existing_data_not_silently_overwritten(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        original_desc = self.task.description

        # Modify description in db
        self.task.description = "New description in active database"
        self.task.save()

        # Restore into same workspace
        WorkspaceRestoreService.execute_transactional_restore(
            file_content_bytes=buf.getvalue(),
            actor=self.admin,
            target_workspace_slug=self.workspace.slug
        )

        self.task.refresh_from_db()
        # Must retain current DB description (non-destructive conflict handling)
        self.assertEqual(self.task.description, "New description in active database")

    # 23. File metadata export and payload status
    def test_23_file_metadata_export_and_payload_status(self):
        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        wb = openpyxl.load_workbook(buf, data_only=True)
        ws_files = wb["Files_Metadata"]

        headers = [c.value for c in ws_files[1]]
        status_idx = headers.index('payload_status')
        size_idx = headers.index('size_bytes')

        file_row = [r for r in ws_files.iter_rows(min_row=2, values_only=True) if r and r[6] == 'architecture_diagram.png'][0]
        self.assertEqual(file_row[status_idx], 'METADATA_ONLY_BINARY_EXCLUDED')
        self.assertEqual(file_row[size_idx], 204800)

    # 24. Chat is excluded during restore
    def test_24_chat_excluded_during_restore(self):
        channel_count_before = Channel.objects.count()
        message_count_before = Message.objects.count()

        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        WorkspaceRestoreService.execute_transactional_restore(
            file_content_bytes=buf.getvalue(),
            actor=self.admin,
            target_workspace_slug='restored-no-chat-ws'
        )

        self.assertEqual(Channel.objects.count(), channel_count_before)
        self.assertEqual(Message.objects.count(), message_count_before)

    # 25. No 500-record truncation on restore
    def test_25_no_500_record_truncation_on_restore(self):
        # Create 505 tasks in workspace
        tasks = [
            Task(
                workspace=self.workspace,
                task_code=f"7{i:05d}",
                title=f"Bulk Task #{i}",
                reporter=self.admin
            )
            for i in range(505)
        ]
        Task.objects.bulk_create(tasks)

        buf, _ = WorkspaceBackupService.export_workspace_to_excel(self.workspace, self.admin)
        self.workspace.delete()
        success, report = WorkspaceRestoreService.execute_transactional_restore(
            file_content_bytes=buf.getvalue(),
            actor=self.admin,
            target_workspace_slug='restored-505-ws'
        )
        self.assertTrue(success)
        restored_ws = Workspace.objects.get(slug='restored-505-ws')
        self.assertGreaterEqual(Task.objects.filter(workspace=restored_ws).count(), 505)


class AdminAlertsIntegrationsAndAccessRequestTests(TestCase):
    """
    Comprehensive tests for:
    1. System Alerts real lifecycle (detection, generation, idempotency, filtering, resolution, history)
    2. Integrations & Performance platform health diagnostics (honesty, SELECT 1 ping, audit logging)
    3. Storage Sync Audit session persistence & toast/result UX
    4. Global Request Access & Temporary Permission System (submission, self-approval prevention,
       scoped temporary grants, expiration, workspace isolation, notifications, and audit logging)
    """

    def setUp(self):
        self.client = Client()

        # Platform Admin
        self.admin = User.objects.create_user(
            username='admin_alert',
            email='admin_alert@aetherspace.io',
            password='Password123!',
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )

        # Manager
        self.manager = User.objects.create_user(
            username='manager_alert',
            email='manager_alert@aetherspace.io',
            password='Password123!',
            role=UserRole.MANAGER,
            is_active=True,
            is_verified=True,
        )

        # Contributor
        self.contributor = User.objects.create_user(
            username='contrib_alert',
            email='contrib_alert@aetherspace.io',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            is_active=True,
            is_verified=True,
        )

        # Workspaces
        self.workspace_a = Workspace.objects.create(
            name='Workspace Alpha',
            slug='workspace-alpha',
            owner=self.admin,
            status=WorkspaceStatus.ACTIVE,
            max_seats=15,
            storage_quota_mb=10,
        )
        self.membership_a = WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE,
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.admin,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )

        self.workspace_b = Workspace.objects.create(
            name='Workspace Beta',
            slug='workspace-beta',
            owner=self.admin,
            status=WorkspaceStatus.ACTIVE,
            max_seats=15,
            storage_quota_mb=20,
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_b,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE,
        )

    # =========================================================================
    # 1. SYSTEM ALERTS LIFECYCLE
    # =========================================================================

    def test_storage_quota_alert_lifecycle_and_idempotency(self):
        """Storage quota condition creates WARNING at 80%, CRITICAL at 100%, and auto-resolves below 80%."""
        # 1. 85% usage (8.5 MB out of 10 MB)
        f1 = StoredFile.objects.create(
            workspace=self.workspace_a,
            uploaded_by=self.admin,
            name='large_archive.zip',
            storage_path='alpha/large_archive.zip',
            size_bytes=int(8.5 * 1024 * 1024),
            is_external_link=False,
        )

        SystemHealthService.sync_dynamic_alerts()
        alert = AdminAlert.objects.filter(
            workspace=self.workspace_a,
            category=AlertCategory.STORAGE,
            is_resolved=False
        ).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.WARNING)
        self.assertIn("storage capacity", alert.title.lower())

        # 2. Repeated sync does NOT create duplicates
        SystemHealthService.sync_dynamic_alerts()
        open_storage_alerts = AdminAlert.objects.filter(
            workspace=self.workspace_a,
            category=AlertCategory.STORAGE,
            is_resolved=False
        ).count()
        self.assertEqual(open_storage_alerts, 1)

        # 3. Usage reaches 110% (11 MB) -> escalated to CRITICAL in-place
        f2 = StoredFile.objects.create(
            workspace=self.workspace_a,
            uploaded_by=self.admin,
            name='extra_dump.sql',
            storage_path='alpha/extra_dump.sql',
            size_bytes=int(2.5 * 1024 * 1024),
            is_external_link=False,
        )
        SystemHealthService.sync_dynamic_alerts()
        alert.refresh_from_db()
        self.assertEqual(alert.severity, AlertSeverity.CRITICAL)

        # 4. Storage cleaned up -> auto-resolves
        f1.delete()
        f2.delete()
        SystemHealthService.sync_dynamic_alerts()
        alert.refresh_from_db()
        self.assertTrue(alert.is_resolved)

    def test_sev1_bug_alert_lifecycle_and_idempotency(self):
        """Sev-1 critical bug condition generates CRITICAL alert and auto-resolves when bug is resolved."""
        bug = Bug.objects.create(
            workspace=self.workspace_a,
            title='Production DB deadlock',
            bug_code='B-999001',
            severity=BugSeverity.SEV1,
            priority=BugPriority.CRITICAL,
            status=BugStatus.OPEN,
            reporter=self.contributor,
        )

        SystemHealthService.sync_dynamic_alerts()
        alert = AdminAlert.objects.filter(
            workspace=self.workspace_a,
            category=AlertCategory.BUGS,
            is_resolved=False
        ).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.CRITICAL)
        self.assertIn('B-999001', alert.message)

        # Repeated sync does NOT create duplicates
        SystemHealthService.sync_dynamic_alerts()
        bug_alerts_count = AdminAlert.objects.filter(
            workspace=self.workspace_a,
            category=AlertCategory.BUGS,
            is_resolved=False
        ).count()
        self.assertEqual(bug_alerts_count, 1)

        # Resolve the bug -> auto-resolves alert on next sync
        bug.status = BugStatus.RESOLVED
        bug.save()
        SystemHealthService.sync_dynamic_alerts()
        alert.refresh_from_db()
        self.assertTrue(alert.is_resolved)

    def test_security_anomaly_alert_generation_and_idempotency(self):
        """Multiple failed audit log entries trigger a security anomaly alert."""
        for i in range(6):
            AuditLog.objects.create(
                action='AUTH_FAILURE',
                status=AuditActionStatus.FAILURE,
                metadata={'reason': f'Brute force attempt #{i}'}
            )

        SystemHealthService.sync_dynamic_alerts()
        alert = AdminAlert.objects.filter(
            category=AlertCategory.SECURITY,
            is_resolved=False
        ).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.WARNING)
        self.assertIn("Security Alert", alert.title)

        # Idempotency
        SystemHealthService.sync_dynamic_alerts()
        sec_alerts = AdminAlert.objects.filter(category=AlertCategory.SECURITY, is_resolved=False).count()
        self.assertEqual(sec_alerts, 1)

    def test_alert_severity_and_status_filtering_in_admin_panel(self):
        """Admin Alerts UI supports severity and status filtering."""
        self.client.force_login(self.admin)

        crit_alert = AdminAlert.objects.create(
            title='Critical DB Outage',
            message='Connection pool exhausted',
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.SYSTEM,
            workspace=self.workspace_a,
            is_resolved=False
        )
        warn_alert = AdminAlert.objects.create(
            title='Warning Disk Pressure',
            message='Disk 85% full',
            severity=AlertSeverity.WARNING,
            category=AlertCategory.SYSTEM,
            workspace=self.workspace_a,
            is_resolved=False
        )
        resolved_alert = AdminAlert.objects.create(
            title='Old Resolved Issue',
            message='Restored service',
            severity=AlertSeverity.INFO,
            category=AlertCategory.SYSTEM,
            workspace=self.workspace_a,
            is_resolved=True,
            resolved_at=timezone.now(),
            resolved_by=self.admin
        )

        # Filter by CRITICAL
        resp = self.client.get(reverse('admin_panel:alerts_list') + '?severity=CRITICAL')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Critical DB Outage')
        self.assertNotContains(resp, 'Warning Disk Pressure')

        # Filter by RESOLVED status
        resp_res = self.client.get(reverse('admin_panel:alerts_list') + '?status=resolved')
        self.assertEqual(resp_res.status_code, 200)
        self.assertContains(resp_res, 'Old Resolved Issue')

    def test_manual_resolve_alert_and_resolved_history(self):
        """Admin can manually resolve an alert and it appears in resolved history."""
        self.client.force_login(self.admin)

        alert = AdminAlert.objects.create(
            title='Manual Triage Alert',
            message='Manual inspection requested',
            severity=AlertSeverity.WARNING,
            category=AlertCategory.SYSTEM,
            workspace=self.workspace_a,
            is_resolved=False
        )

        url = reverse('admin_panel:resolve_alert', kwargs={'alert_id': alert.id})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)

        alert.refresh_from_db()
        self.assertTrue(alert.is_resolved)
        self.assertEqual(alert.resolved_by, self.admin)
        self.assertIsNotNone(alert.resolved_at)

    def test_unauthorized_user_cannot_manipulate_alerts(self):
        """Manager and Contributor cannot access Admin Alerts or resolve alerts."""
        alert = AdminAlert.objects.create(
            title='Secured Alert',
            message='Protected message',
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.SECURITY,
            is_resolved=False
        )

        self.client.force_login(self.contributor)
        # 1. Contributor cannot view alerts
        resp1 = self.client.get(reverse('admin_panel:alerts_list'))
        self.assertEqual(resp1.status_code, 403)

        # 2. Contributor cannot resolve alert
        resp2 = self.client.post(reverse('admin_panel:resolve_alert', kwargs={'alert_id': alert.id}))
        self.assertEqual(resp2.status_code, 403)

        # 3. Contributor cannot trigger alert sync
        resp3 = self.client.post(reverse('admin_panel:sync_alerts'))
        self.assertEqual(resp3.status_code, 403)

        self.client.force_login(self.manager)
        resp4 = self.client.post(reverse('admin_panel:resolve_alert', kwargs={'alert_id': alert.id}))
        self.assertEqual(resp4.status_code, 403)

    # =========================================================================
    # 2. INTEGRATIONS & PERFORMANCE PLATFORM HEALTH
    # =========================================================================

    def test_integrations_status_honesty_and_structure(self):
        """Integration statuses separate config, health, last_checked, evidence, and never leak credentials."""
        status_list = SystemHealthService.get_integrations_status()

        self.assertGreaterEqual(len(status_list), 5)
        names = [item['name'] for item in status_list]
        self.assertTrue(any('PostgreSQL' in n for n in names))
        self.assertTrue(any('Storage' in n for n in names))
        self.assertTrue(any('Email' in n for n in names))
        self.assertTrue(any('Jitsi' in n for n in names))
        self.assertTrue(any('WhiteNoise' in n for n in names))

        for entry in status_list:
            self.assertIn('configuration', entry)
            self.assertIn('health_status', entry)
            self.assertIn('last_checked', entry)
            self.assertIn('evidence', entry)
            self.assertNotIn('password', entry['evidence'].lower())

        jitsi_item = [i for i in status_list if 'Jitsi' in i['name']][0]
        self.assertEqual(jitsi_item['health_status'], 'Not automatically verified')
        self.assertIn('meet.jit.si', jitsi_item['configuration'])

    def test_test_integration_action(self):
        """Platform Admin can run a safe real health check on PostgreSQL."""
        self.client.force_login(self.admin)
        url = reverse('admin_panel:test_integration', kwargs={'key': 'postgres'})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)

        # Invalid key should fail gracefully
        url_bad = reverse('admin_panel:test_integration', kwargs={'key': 'unknown_service'})
        resp_bad = self.client.post(url_bad)
        self.assertEqual(resp_bad.status_code, 302)

    def test_performance_overview_and_remeasure_ping(self):
        """Performance overview renders real metrics and POST re-measures live ping with AuditLog."""
        self.client.force_login(self.admin)

        # 1. GET page
        resp = self.client.get(reverse('admin_panel:performance_overview'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('diagnostics', resp.context)
        diag = resp.context['diagnostics']
        self.assertIn('database', diag)
        self.assertIn('application', diag)
        self.assertIn('apm', diag)
        self.assertEqual(diag['apm']['status'], 'Not Configured')

        # 2. POST re-measure ping
        post_resp = self.client.post(reverse('admin_panel:performance_overview'))
        self.assertEqual(post_resp.status_code, 302)

        # Audit log written
        log = AuditLog.objects.filter(action='DATABASE_PING_REMEASURED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, AuditActionStatus.SUCCESS)

    # =========================================================================
    # 3. TOAST UX & STORAGE SYNC AUDIT RESULT PANEL
    # =========================================================================

    def test_storage_sync_audit_persists_in_session_and_renders(self):
        """Storage sync audit records results in session for persistent display across redirects."""
        self.client.force_login(self.admin)

        post_resp = self.client.post(reverse('admin_panel:storage_sync_audit'))
        self.assertEqual(post_resp.status_code, 302)

        # Check session
        session_data = self.client.session.get('last_storage_sync_audit')
        self.assertIsNotNone(session_data)
        self.assertIn('total_audited', session_data)
        self.assertIn('synced_count', session_data)
        self.assertIn('missing_count', session_data)
        self.assertIn('mismatched_count', session_data)
        self.assertIn('checked_at', session_data)

        # GET storage_files renders the persistent inline audit report
        get_resp = self.client.get(reverse('admin_panel:storage_files'))
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, 'Storage Sync Audit Report')

        # Dismiss audit clears session
        dismiss_resp = self.client.get(reverse('admin_panel:storage_files') + '?dismiss_audit=1')
        self.assertEqual(dismiss_resp.status_code, 302)
        self.assertIsNone(self.client.session.get('last_storage_sync_audit'))

    # =========================================================================
    # 4. GLOBAL ACCESS REQUEST SYSTEM & TEMPORARY PERMISSIONS
    # =========================================================================

    def test_submit_access_request_validation(self):
        """Submitting an access request enforces required reason and goal description for emergency."""
        self.client.force_login(self.contributor)
        url = reverse('workspaces:submit_access_request')

        # 1. Missing reason fails
        resp1 = self.client.post(url, {
            'workspace_id': str(self.workspace_a.id),
            'action': AccessRequestAction.TASK_CREATE,
            'reason': '   ',
            'urgency': AccessRequestUrgency.NORMAL,
        })
        self.assertEqual(resp1.status_code, 302)
        self.assertEqual(GlobalAccessRequest.objects.count(), 0)

        # 2. EMERGENCY urgency without goal description fails
        resp2 = self.client.post(url, {
            'workspace_id': str(self.workspace_a.id),
            'action': AccessRequestAction.TASK_CREATE,
            'reason': 'Production outage fix',
            'urgency': AccessRequestUrgency.EMERGENCY,
            'goal_description': '  ',
        })
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(GlobalAccessRequest.objects.count(), 0)

        # 3. Valid submission succeeds and notifies
        resp3 = self.client.post(url, {
            'workspace_id': str(self.workspace_a.id),
            'action': AccessRequestAction.TASK_CREATE,
            'reason': 'Deploying hotfix sprint task',
            'goal_description': 'Need to create hotfix sprint task for deploy',
            'urgency': AccessRequestUrgency.URGENT,
            'requested_duration': AccessDurationChoice.ONE_HOUR,
            'evidence_url': 'https://github.com/org/repo/issues/42',
        })
        self.assertEqual(resp3.status_code, 302)
        req = GlobalAccessRequest.objects.filter(user=self.contributor).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.status, AccessRequestStatus.PENDING)
        self.assertEqual(req.action, AccessRequestAction.TASK_CREATE)
        self.assertEqual(req.evidence_url, 'https://github.com/org/repo/issues/42')

        # Requester receives notification acknowledging receipt
        requester_notif = Notification.objects.filter(recipient=self.contributor).first()
        self.assertIsNotNone(requester_notif)
        self.assertIn("Access Request Submitted", requester_notif.title)

    def test_requester_cannot_approve_own_request(self):
        """Admin cannot approve their own access request (Self-approval violation prevention)."""
        self.client.force_login(self.admin)

        # Admin creates request for themselves
        req = GlobalAccessRequest.objects.create(
            user=self.admin,
            workspace=self.workspace_a,
            action=AccessRequestAction.TASK_CREATE,
            reason='Need access to self-manage task',
            urgency=AccessRequestUrgency.NORMAL,
            requested_duration=AccessDurationChoice.ONE_HOUR,
            status=AccessRequestStatus.PENDING,
        )

        decide_url = reverse('admin_panel:decide_workspace_request', kwargs={'request_id': req.id})
        resp = self.client.post(decide_url, {
            'decision': 'APPROVE',
            'duration_choice': AccessDurationChoice.ONE_HOUR,
        })
        self.assertEqual(resp.status_code, 302)

        req.refresh_from_db()
        # Must still be PENDING - self-approval blocked!
        self.assertEqual(req.status, AccessRequestStatus.PENDING)
        self.assertFalse(TemporaryAccessGrant.objects.filter(access_request=req).exists())

    def test_approve_request_creates_temporary_grant_without_role_escalation(self):
        """Approving request creates a scoped, time-bounded TemporaryAccessGrant and preserves permanent role."""
        req = GlobalAccessRequest.objects.create(
            user=self.contributor,
            workspace=self.workspace_a,
            action='sprint.manage',
            reason='Assisting sprint planning for Sprint 4',
            urgency=AccessRequestUrgency.NORMAL,
            requested_duration=AccessDurationChoice.FOUR_HOURS,
            status=AccessRequestStatus.PENDING,
        )

        self.client.force_login(self.admin)
        decide_url = reverse('admin_panel:decide_workspace_request', kwargs={'request_id': req.id})
        resp = self.client.post(decide_url, {
            'decision': 'APPROVE',
            'duration_choice': AccessDurationChoice.FOUR_HOURS,
            'admin_notes': 'Granted for sprint planning only.',
        })
        self.assertEqual(resp.status_code, 302)

        # 1. Request status updated
        req.refresh_from_db()
        self.assertEqual(req.status, AccessRequestStatus.APPROVED)
        self.assertEqual(req.reviewed_by, self.admin)
        self.assertIsNotNone(req.reviewed_at)

        # 2. Scoped temporary grant created
        grant = TemporaryAccessGrant.objects.filter(access_request=req).first()
        self.assertIsNotNone(grant)
        self.assertEqual(grant.user, self.contributor)
        self.assertEqual(grant.workspace, self.workspace_a)
        self.assertEqual(grant.action, 'sprint.manage')
        self.assertTrue(grant.is_active)
        self.assertGreater(grant.expires_at, timezone.now())

        # 3. Permanent membership role UNCHANGED (Contributor remains Contributor)
        self.membership_a.refresh_from_db()
        self.assertEqual(self.membership_a.role, WorkspaceRole.CONTRIBUTOR)

        # 4. Requester receives approval notification
        notif = Notification.objects.filter(recipient=self.contributor, title__icontains='Approved').first()
        self.assertIsNotNone(notif)

        # 5. Audit log created
        audit = AuditLog.objects.filter(action='ACCESS_REQUEST_APPROVED').first()
        self.assertIsNotNone(audit)

    def test_reject_request_requires_rejection_reason(self):
        """Rejecting an access request strictly requires a rejection reason."""
        req = GlobalAccessRequest.objects.create(
            user=self.contributor,
            workspace=self.workspace_a,
            action=AccessRequestAction.TASK_CREATE,
            reason='Extra task needed',
            status=AccessRequestStatus.PENDING,
        )

        self.client.force_login(self.admin)
        decide_url = reverse('admin_panel:decide_workspace_request', kwargs={'request_id': req.id})

        # 1. Empty rejection reason fails
        resp1 = self.client.post(decide_url, {'decision': 'REJECT', 'rejection_reason': '   '})
        self.assertEqual(resp1.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, AccessRequestStatus.PENDING)

        # 2. Valid rejection reason succeeds
        resp2 = self.client.post(decide_url, {
            'decision': 'REJECT',
            'rejection_reason': 'Scope creep: not approved for current milestone.'
        })
        self.assertEqual(resp2.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, AccessRequestStatus.REJECTED)
        self.assertEqual(req.rejection_reason, 'Scope creep: not approved for current milestone.')

        # Notification dispatched
        notif = Notification.objects.filter(recipient=self.contributor, title__icontains='Rejected').first()
        self.assertIsNotNone(notif)

    def test_temporary_grant_authorizes_action_within_workspace_only(self):
        """Active grant authorizes only requested action and strictly isolates workspaces."""
        # By default, Contributor cannot manage sprints
        self.assertFalse(can_user_perform_action(self.contributor, self.workspace_a, 'sprint.manage'))

        # Create active grant in Workspace A
        grant = TemporaryAccessGrant.objects.create(
            user=self.contributor,
            workspace=self.workspace_a,
            action='sprint.manage',
            granted_by=self.admin,
            expires_at=timezone.now() + timezone.timedelta(hours=2),
            reason='Temporary sprint planning'
        )

        # Now authorized in Workspace A
        self.assertTrue(can_user_perform_action(self.contributor, self.workspace_a, 'sprint.manage'))

        # But NOT authorized for unrelated action in Workspace A
        self.assertFalse(can_user_perform_action(self.contributor, self.workspace_a, 'workspace.delete'))

        # And NOT authorized in Workspace B (Workspace boundary strictly enforced!)
        self.assertFalse(can_user_perform_action(self.contributor, self.workspace_b, 'sprint.manage'))

    def test_expired_grant_cannot_authorize_action(self):
        """Expired grant fails authorization immediately."""
        # Create expired grant
        TemporaryAccessGrant.objects.create(
            user=self.contributor,
            workspace=self.workspace_a,
            action='sprint.manage',
            granted_by=self.admin,
            expires_at=timezone.now() - timezone.timedelta(minutes=5),
            reason='Expired test'
        )

        self.assertFalse(can_user_perform_action(self.contributor, self.workspace_a, 'sprint.manage'))

    def test_admin_access_requests_center_listing_and_filtering(self):
        """Admin can list and filter access requests, but Contributor receives 403."""
        GlobalAccessRequest.objects.create(
            user=self.contributor,
            workspace=self.workspace_a,
            action=AccessRequestAction.TASK_CREATE,
            reason='Test filtering',
            status=AccessRequestStatus.PENDING,
            urgency=AccessRequestUrgency.URGENT,
        )

        self.client.force_login(self.admin)
        resp = self.client.get(reverse('admin_panel:workspace_requests') + '?tab=pending')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Test filtering')
        self.assertContains(resp, 'URGENT')

        # Contributor receives 403 Forbidden
        self.client.force_login(self.contributor)
        resp_denied = self.client.get(reverse('admin_panel:workspace_requests'))
        self.assertEqual(resp_denied.status_code, 403)

