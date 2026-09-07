import re
from datetime import date
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from workspaces.models import (
    Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus, WorkspaceModule
)
from .models import (
    Bug, BugActivity, BugComment, BugStatus, BugPriority,
    BugSeverity, BugEnvironment
)
from .services import generate_unique_bug_code, create_bug, update_bug, change_bug_status

User = get_user_model()


class BugTrackingTests(TestCase):
    """
    Comprehensive test suite covering Phase 6 Bug Tracking module:
    - B-###### 6-digit ID generation & collision safety
    - Bug creation, editing, status transitions
    - Granular activity audit logging
    - Multi-tenant workspace isolation
    - Strict RBAC deletion permissions
    - Filtering & search
    - Comments discussion
    - My Bugs cross-workspace view
    - Bug Dashboard metrics
    """

    def setUp(self):
        self.client = Client()

        # Admin user
        self.admin_user = User.objects.create_user(
            email='admin@aetherspace.dev',
            password='AdminPassword123!',
            full_name='Admin User'
        )

        # Manager user
        self.manager_user = User.objects.create_user(
            email='manager@aetherspace.dev',
            password='ManagerPassword123!',
            full_name='Manager User'
        )

        # Contributor user
        self.contributor_user = User.objects.create_user(
            email='contributor@aetherspace.dev',
            password='ContributorPassword123!',
            full_name='Contributor User'
        )

        # Outsider user (belongs to no workspace)
        self.outsider_user = User.objects.create_user(
            email='outsider@aetherspace.dev',
            password='OutsiderPassword123!',
            full_name='Outsider User'
        )

        # Workspace 1
        self.workspace1 = Workspace.objects.create(
            name='Alpha Project',
            slug='alpha-project',
            owner=self.admin_user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace1,
            user=self.admin_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace1,
            user=self.manager_user,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace1,
            user=self.contributor_user,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Workspace 2 (for isolation testing)
        self.workspace2 = Workspace.objects.create(
            name='Beta Project',
            slug='beta-project',
            owner=self.admin_user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace2,
            user=self.admin_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

        # Workspace 1 Modules
        self.module_auth = WorkspaceModule.objects.create(
            workspace=self.workspace1,
            name='Authentication',
            description='User login, registration, sessions'
        )
        self.module_files = WorkspaceModule.objects.create(
            workspace=self.workspace1,
            name='Files',
            description='Storage and media assets'
        )
        self.module_ui = WorkspaceModule.objects.create(
            workspace=self.workspace1,
            name='UI/UX',
            description='Design and responsiveness'
        )
        self.module_settings = WorkspaceModule.objects.create(
            workspace=self.workspace1,
            name='Settings',
            description='Project configurations'
        )

        # Workspace 2 Module
        self.module_w2 = WorkspaceModule.objects.create(
            workspace=self.workspace2,
            name='Billing',
            description='Invoicing and payment processing'
        )

    # 1. Bug ID Format & Collision Safety
    def test_bug_id_format(self):
        code = generate_unique_bug_code()
        self.assertTrue(re.match(r'^B-[0-9]{6}$', code), f"Invalid format: {code}")

    def test_bug_id_collision_safety(self):
        # Create an existing bug with known code 'B-123456'
        Bug.objects.create(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Collision Seed Defect',
            bug_code='B-123456'
        )

        # Mock secrets.randbelow so it first returns 23456 (generating 'B-123456' which exists)
        # then returns 23457 (generating 'B-123457' which does NOT exist)
        with patch('secrets.randbelow') as mock_rand:
            mock_rand.side_effect = [23456, 23457]
            generated_code = generate_unique_bug_code()
            # Must detect collision with existing bug, skip it, and return the next unique candidate
            self.assertEqual(generated_code, 'B-123457')
            self.assertEqual(mock_rand.call_count, 2)

    # 2. Service Creation & Activity Log
    def test_create_bug_service(self):
        bug = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Staging 500 error on checkout',
            description='Server throws 500 error during checkout payment.',
            steps_to_reproduce='1. Add item\n2. Click Checkout',
            expected_result='Order confirmed',
            actual_result='500 Server Error',
            status=BugStatus.OPEN,
            priority=BugPriority.CRITICAL,
            severity=BugSeverity.SEV1,
            module=self.module_auth,
            assignee=self.contributor_user
        )

        self.assertTrue(re.match(r'^B-[0-9]{6}$', bug.bug_code))
        self.assertEqual(bug.status, BugStatus.OPEN)
        self.assertEqual(bug.priority, BugPriority.CRITICAL)
        self.assertEqual(bug.severity, BugSeverity.SEV1)
        self.assertEqual(bug.module, self.module_auth)
        self.assertEqual(bug.assignee, self.contributor_user)

        # Verify initial activities
        activities = bug.activities.all()
        self.assertTrue(activities.filter(action=BugActivity.Action.CREATED).exists())
        self.assertTrue(activities.filter(action=BugActivity.Action.ASSIGNED).exists())

    # 3. Update Bug & Granular Audit Log
    def test_update_bug_service(self):
        bug = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Initial Title',
            status=BugStatus.OPEN,
            priority=BugPriority.MEDIUM
        )

        update_bug(
            bug=bug,
            actor=self.manager_user,
            title='Updated Title',
            status=BugStatus.IN_PROGRESS,
            priority=BugPriority.HIGH,
            assignee=self.contributor_user
        )

        bug.refresh_from_db()
        self.assertEqual(bug.title, 'Updated Title')
        self.assertEqual(bug.status, BugStatus.IN_PROGRESS)
        self.assertEqual(bug.priority, BugPriority.HIGH)
        self.assertEqual(bug.assignee, self.contributor_user)

        # Verify activity logs
        self.assertTrue(bug.activities.filter(action=BugActivity.Action.STATUS_CHANGED).exists())
        self.assertTrue(bug.activities.filter(action=BugActivity.Action.PRIORITY_CHANGED).exists())
        self.assertTrue(bug.activities.filter(action=BugActivity.Action.ASSIGNED).exists())

    # 4. Status Transition
    def test_change_bug_status_service(self):
        bug = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Test status flow'
        )

        change_bug_status(bug, BugStatus.RESOLVED, self.manager_user)
        bug.refresh_from_db()
        self.assertEqual(bug.status, BugStatus.RESOLVED)

        status_activity = bug.activities.filter(action=BugActivity.Action.STATUS_CHANGED).first()
        self.assertIsNotNone(status_activity)
        self.assertIn('Resolved', status_activity.message)

    # 5. Authentication Enforcement
    def test_unauthenticated_access_redirects(self):
        # Accessing bug views without logging in must redirect to auth
        resp = self.client.get(reverse('bugs:bug_list', kwargs={'slug': self.workspace1.slug}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login/', resp.url)

        resp = self.client.get(reverse('bugs:my_bugs'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login/', resp.url)

    # 6. Workspace Isolation
    def test_workspace_isolation(self):
        # Bug belongs to Workspace 2
        bug_w2 = create_bug(
            workspace=self.workspace2,
            reporter=self.admin_user,
            title='Secret bug in Workspace 2'
        )

        # Contributor belongs only to Workspace 1
        self.client.force_login(self.contributor_user)

        # Cannot access Workspace 2 bug list (403 or redirect)
        resp = self.client.get(reverse('bugs:bug_list', kwargs={'slug': self.workspace2.slug}))
        self.assertEqual(resp.status_code, 403)

        # Cannot access Workspace 2 bug detail
        resp = self.client.get(reverse('bugs:bug_detail', kwargs={'slug': self.workspace2.slug, 'bug_code': bug_w2.bug_code}))
        self.assertEqual(resp.status_code, 403)

    # 7. Bug Creation View (POST)
    def test_bug_create_view(self):
        self.client.force_login(self.admin_user)
        url = reverse('bugs:bug_create', kwargs={'slug': self.workspace1.slug})

        post_data = {
            'title': 'Memory leak on file upload',
            'description': 'Repeated uploads cause container RAM spikes.',
            'steps_to_reproduce': '1. Upload 10 files\n2. Observe RAM',
            'expected_result': 'RAM reclaimed',
            'actual_result': 'OOM crash',
            'module': str(self.module_files.id),
            'priority': BugPriority.HIGH,
            'severity': BugSeverity.SEV2,
            'environment': BugEnvironment.STAGING,
            'status': BugStatus.OPEN,
            'sprint': 'Sprint 02',
            'labels': 'backend, memory',
        }

        resp = self.client.post(url, data=post_data)
        self.assertEqual(resp.status_code, 302)

        bug = Bug.objects.filter(workspace=self.workspace1, title='Memory leak on file upload').first()
        self.assertIsNotNone(bug)
        self.assertTrue(re.match(r'^B-[0-9]{6}$', bug.bug_code))
        self.assertEqual(bug.priority, BugPriority.HIGH)
        self.assertEqual(bug.module, self.module_files)

    # 8. RBAC Deletion Permissions
    def test_rbac_delete_permissions(self):
        bug = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Defect to test deletion'
        )
        delete_url = reverse('bugs:bug_delete', kwargs={'slug': self.workspace1.slug, 'bug_code': bug.bug_code})

        # Contributor attempts deletion -> 403 Forbidden
        self.client.force_login(self.contributor_user)
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Bug.objects.filter(id=bug.id).exists())

        # Manager attempts deletion -> Allowed
        self.client.force_login(self.manager_user)
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Bug.objects.filter(id=bug.id).exists())

    # 9. Filtering and Search
    def test_bug_filtering(self):
        self.client.force_login(self.admin_user)
        b1 = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='UI alignment issue on navbar',
            status=BugStatus.OPEN,
            priority=BugPriority.LOW,
            module=self.module_ui
        )
        b2 = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Database connection pool timeout',
            status=BugStatus.RESOLVED,
            priority=BugPriority.CRITICAL,
            module=self.module_settings
        )

        list_url = reverse('bugs:bug_list', kwargs={'slug': self.workspace1.slug})

        # Filter by status=OPEN
        resp = self.client.get(list_url + '?status=OPEN')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, b1.bug_code)
        self.assertNotContains(resp, b2.bug_code)

        # Filter by priority=CRITICAL
        resp = self.client.get(list_url + '?priority=CRITICAL')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, b2.bug_code)
        self.assertNotContains(resp, b1.bug_code)

        # Filter by module name
        resp = self.client.get(list_url + f'?module={self.module_ui.name}')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, b1.bug_code)
        self.assertNotContains(resp, b2.bug_code)

        # Search query by text
        resp = self.client.get(list_url + '?q=alignment')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, b1.bug_code)
        self.assertNotContains(resp, b2.bug_code)

    # 10. Comments Thread
    def test_bug_comments(self):
        bug = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Bug for comment testing'
        )

        self.client.force_login(self.contributor_user)
        comment_url = reverse('bugs:bug_comment_add', kwargs={'slug': self.workspace1.slug, 'bug_code': bug.bug_code})

        resp = self.client.post(comment_url, {'content': 'I investigated the stack trace.'})
        self.assertEqual(resp.status_code, 302)

        comment = bug.comments.first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.author, self.contributor_user)
        self.assertEqual(comment.content, 'I investigated the stack trace.')

        # Activity was logged
        self.assertTrue(bug.activities.filter(action=BugActivity.Action.COMMENTED).exists())

    # 11. My Bugs View
    def test_my_bugs_view(self):
        self.client.force_login(self.contributor_user)

        b_assigned = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Assigned to contributor',
            assignee=self.contributor_user
        )
        b_reported = create_bug(
            workspace=self.workspace1,
            reporter=self.contributor_user,
            title='Reported by contributor',
            assignee=self.admin_user
        )

        my_bugs_url = reverse('bugs:my_bugs')

        # Assigned tab
        resp = self.client.get(my_bugs_url + '?tab=assigned')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, b_assigned.bug_code)
        self.assertNotContains(resp, b_reported.bug_code)

        # Reported tab
        resp = self.client.get(my_bugs_url + '?tab=reported')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, b_reported.bug_code)
        self.assertNotContains(resp, b_assigned.bug_code)

    # 12. Bug Dashboard View
    def test_bug_dashboard_view(self):
        self.client.force_login(self.admin_user)
        b = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Critical DB issue',
            status=BugStatus.OPEN,
            priority=BugPriority.CRITICAL
        )

        dash_url = reverse('bugs:bug_dashboard', kwargs={'slug': self.workspace1.slug})
        resp = self.client.get(dash_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Bug Dashboard')
        self.assertContains(resp, b.bug_code)
        self.assertEqual(resp.context['total_bugs'], 1)
        self.assertEqual(resp.context['open_count'], 1)

    # 13. Cross-Workspace Module Isolation & Validation
    def test_cross_workspace_module_validation(self):
        from django.core.exceptions import ValidationError
        # Attempt to attach workspace2's module to a bug in workspace1
        bug = Bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Mismatched workspace bug',
            module=self.module_w2
        )
        with self.assertRaises(ValidationError):
            bug.full_clean()

    # 14. Workspace Module Management RBAC (Admin/Manager vs Contributor)
    def test_workspace_module_management_rbac(self):
        # Contributor cannot create a module
        self.client.force_login(self.contributor_user)
        create_url = reverse('workspaces:module_create', kwargs={'slug': self.workspace1.slug})
        resp = self.client.post(create_url, {'name': 'Analytics', 'description': 'Metrics subsystem'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(WorkspaceModule.objects.filter(workspace=self.workspace1, name='Analytics').exists())

        # Contributor cannot edit a module
        edit_url = reverse('workspaces:module_edit', kwargs={'slug': self.workspace1.slug, 'module_id': self.module_auth.id})
        resp = self.client.post(edit_url, {'name': 'Hacked Auth', 'description': 'Malicious update'})
        self.assertEqual(resp.status_code, 403)

        # Contributor cannot delete a module
        delete_url = reverse('workspaces:module_delete', kwargs={'slug': self.workspace1.slug, 'module_id': self.module_auth.id})
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(WorkspaceModule.objects.filter(id=self.module_auth.id).exists())

        # Manager can create a module
        self.client.force_login(self.manager_user)
        resp = self.client.post(create_url, {'name': 'Analytics', 'description': 'Metrics subsystem', 'is_active': True})
        self.assertEqual(resp.status_code, 302)
        new_mod = WorkspaceModule.objects.filter(workspace=self.workspace1, name='Analytics').first()
        self.assertIsNotNone(new_mod)

        # Manager can edit a module
        edit_url = reverse('workspaces:module_edit', kwargs={'slug': self.workspace1.slug, 'module_id': new_mod.id})
        resp = self.client.post(edit_url, {'name': 'Advanced Analytics', 'description': 'Updated scope', 'is_active': True})
        self.assertEqual(resp.status_code, 302)
        new_mod.refresh_from_db()
        self.assertEqual(new_mod.name, 'Advanced Analytics')

        # Manager can delete a module
        delete_url = reverse('workspaces:module_delete', kwargs={'slug': self.workspace1.slug, 'module_id': new_mod.id})
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(WorkspaceModule.objects.filter(id=new_mod.id).exists())

    # 15. Workspace Module Deletion Safety (SET_NULL on bugs)
    def test_workspace_module_deletion_safety(self):
        # Create a module to delete
        temp_module = WorkspaceModule.objects.create(
            workspace=self.workspace1,
            name='Temporary Feature'
        )
        bug = create_bug(
            workspace=self.workspace1,
            reporter=self.admin_user,
            title='Bug in temporary feature',
            module=temp_module
        )
        self.assertEqual(bug.module, temp_module)

        # Delete module via manager
        self.client.force_login(self.manager_user)
        delete_url = reverse('workspaces:module_delete', kwargs={'slug': self.workspace1.slug, 'module_id': temp_module.id})
        resp = self.client.post(delete_url)
        self.assertEqual(resp.status_code, 302)

        # Module is deleted, but Bug still exists with module=None
        self.assertFalse(WorkspaceModule.objects.filter(id=temp_module.id).exists())
        bug.refresh_from_db()
        self.assertIsNone(bug.module)
        self.assertEqual(bug.title, 'Bug in temporary feature')

