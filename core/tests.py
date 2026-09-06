from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus

User = get_user_model()


class CoreViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"
        self.user = User.objects.create_user(
            email="nav.tester@aetherspace.dev",
            password=self.password,
            full_name="Nav Tester"
        )
        self.workspace = Workspace.objects.create(
            name="Nav Workspace",
            slug="nav-workspace",
            description="Testing navigation shell",
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    def test_landing_page_renders_successfully(self):
        url = reverse('core:landing')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AetherSpace")
        self.assertContains(response, "Your Team.")
        self.assertContains(response, "Get Started Free")

    def test_navigation_routes_require_authentication(self):
        destinations = [
            'core:calendar',
            'core:files',
            'core:meetings',
            'core:chat',
            'core:time_tracking',
            'core:notifications',
            'core:profile',
        ]
        for dest in destinations:
            url = reverse(dest)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, f"{dest} should redirect unauthenticated user")
            self.assertIn('/auth/login/', response.url)

    def test_authenticated_user_can_access_navigation_destinations(self):
        self.client.login(email="nav.tester@aetherspace.dev", password=self.password)
        destinations = [
            ('core:calendar', 'Calendar & Agenda'),
            ('core:files', 'Files & Storage'),
            ('core:meetings', 'Meet Hub'),
            ('core:chat', 'Team Chat & Channels'),
            ('core:time_tracking', 'Time Tracking & Logs'),
            ('core:notifications', 'Notifications Center'),
            ('core:profile', 'User Profile & Preferences'),
        ]
        for dest, expected_title in destinations:
            url = reverse(dest)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"Failed accessing {dest}")
            self.assertEqual(response.context['module_title'], expected_title)
            self.assertContains(response, expected_title.replace('&', '&amp;'))

    def test_workspace_project_details_and_chat_access(self):
        self.client.login(email="nav.tester@aetherspace.dev", password=self.password)
        
        # Project Details
        proj_url = reverse('workspaces:project_details', kwargs={'slug': self.workspace.slug})
        response = self.client.get(proj_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project Details")
        self.assertContains(response, "Tech Stack")

        # Workspace Chat
        chat_url = reverse('workspaces:workspace_chat', kwargs={'slug': self.workspace.slug})
        response = self.client.get(chat_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Team Chat")

    def test_custom_error_views(self):
        for code, name, text in [
            (400, 'core:test_400', "Invalid Request"),
            (403, 'core:test_403', "Access Restricted"),
            (404, 'core:test_404', "Page Not Found"),
            (500, 'core:test_500', "Internal Server Error"),
        ]:
            url = reverse(name)
            response = self.client.get(url)
            self.assertEqual(response.status_code, code)
            self.assertContains(response, text, status_code=code)
