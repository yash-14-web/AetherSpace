import json
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from workspaces.models import (
    Workspace, WorkspaceMembership, WorkspaceRole, WorkspaceStatus,
    WorkspaceInvitation, WorkspaceAccessRequest, AccessRequestStatus,
    InvitationStatus, MembershipStatus
)
from files.models import StoredFile
from admin_panel.models import AuditLog, AdminAlert, AlertSeverity, AlertCategory, AuditActionStatus
from admin_panel.services import StorageSyncService, AuditLogService, SystemHealthService, DataExportService


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
        """Storage sync audit runs and records audit log."""
        url = reverse('admin_panel:storage_sync_audit')
        response = self.client.get(url)
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
        """Metadata JSON download returns application/json attachment."""
        url = reverse('admin_panel:export_data')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('attachment;', response['Content-Disposition'])

        payload = json.loads(response.content)
        self.assertIn('exported_at', payload)
        self.assertIn('users', payload)
        self.assertIn('workspaces', payload)
