from django.test import TestCase, Client
from django.urls import reverse

from accounts.models import User, UserRole, ApprovalStatus
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus


class WorkspaceRBACPhase16Tests(TestCase):
    def setUp(self):
        self.client = Client()

        self.admin = User.objects.create_user(
            email='admin@aetherspace.dev',
            username='admin_user',
            password='Password123!',
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )
        self.manager = User.objects.create_user(
            email='manager@aetherspace.dev',
            username='manager_user',
            password='Password123!',
            role=UserRole.MANAGER,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )
        self.contributor = User.objects.create_user(
            email='contributor@aetherspace.dev',
            username='contributor_user',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )

    def test_contributor_cannot_access_workspace_create(self):
        """Contributors must receive 403 Forbidden when trying to access workspace create view."""
        self.client.force_login(self.contributor)
        url = reverse('workspaces:create')

        # GET request
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)
        self.assertIn(b"Only Administrators and Managers can create workspaces", resp.content)

        # POST request
        resp_post = self.client.post(url, {'name': 'Rogue Workspace', 'slug': 'rogue-ws', 'max_seats': 10})
        self.assertEqual(resp_post.status_code, 403)
        self.assertFalse(Workspace.objects.filter(slug='rogue-ws').exists())

    def test_manager_can_create_workspace(self):
        """Managers are authorized to access and create workspaces."""
        self.client.force_login(self.manager)
        url = reverse('workspaces:create')

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        resp_post = self.client.post(url, {'name': 'Manager Workspace', 'slug': 'manager-ws', 'max_seats': 15})
        self.assertEqual(resp_post.status_code, 302)
        self.assertTrue(Workspace.objects.filter(slug='manager-ws').exists())

    def test_contributor_with_zero_workspaces_dashboard_routing(self):
        """Contributor with 0 workspaces must not be redirected to workspaces:create."""
        self.client.force_login(self.contributor)
        url = reverse('workspaces:dashboard_router')

        resp = self.client.get(url)
        # Should render no_workspaces template directly (200 OK) instead of redirecting to workspaces:create
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No Workspace Memberships")
