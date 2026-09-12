from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
import json

from accounts.models import UserProfile, UserRole
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from tasks.models import Task, TaskStatus, TaskPriority
from bugs.models import Bug, BugStatus, BugSeverity
from admin_panel.models import AuditLog

User = get_user_model()


class UserSettingsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "Secur3P@ssw0rd!123"
        
        # Create normal contributor user
        self.user = User.objects.create_user(
            email="contributor@aetherspace.dev",
            password=self.password,
            full_name="Alice Contributor",
            role=UserRole.CONTRIBUTOR
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            headline="Frontend Engineer",
            preferences={'theme': 'obsidian'}
        )

        # Create workspace admin user
        self.admin_user = User.objects.create_user(
            email="admin@aetherspace.dev",
            password=self.password,
            full_name="Bob Admin",
            role=UserRole.ADMIN
        )
        self.admin_profile = UserProfile.objects.create(
            user=self.admin_user,
            preferences={'theme': 'obsidian'}
        )

        # Create Workspace
        self.workspace = Workspace.objects.create(
            name="Quantum Core",
            slug="quantum-core",
            description="Quantum core workspace",
            owner=self.admin_user,
            max_seats=15,
            storage_quota_mb=50
        )

        # Add memberships
        self.admin_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        self.user_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

    def test_unauthenticated_redirect(self):
        """Unauthenticated access to settings redirects to login."""
        response = self.client.get(reverse('user_settings:account'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)

    def test_account_settings_view_and_update(self):
        """Authenticated user can view and update account settings."""
        self.client.login(email=self.user.email, password=self.password)
        response = self.client.get(reverse('user_settings:account'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Contributor")

        # Update full name
        post_response = self.client.post(reverse('user_settings:account'), {
            'full_name': 'Alice Updated',
            'email': self.user.email,
            'timezone': 'America/New_York'
        }, follow=True)
        self.assertEqual(post_response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, 'Alice Updated')
        self.assertEqual(self.user.timezone, 'America/New_York')

    def test_profile_settings_update(self):
        """User can update public profile details."""
        self.client.login(email=self.user.email, password=self.password)
        response = self.client.post(reverse('user_settings:profile'), {
            'headline': 'Staff Engineer',
            'phone': '+1234567890',
            'bio': 'Passionate about distributed systems.',
            'avatar_url': 'https://example.com/avatar.png'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.headline, 'Staff Engineer')
        self.assertEqual(self.profile.bio, 'Passionate about distributed systems.')

    def test_appearance_settings_and_api(self):
        """User can change appearance and theme via form and AJAX API."""
        self.client.login(email=self.user.email, password=self.password)
        
        # Test AJAX API
        api_response = self.client.post(
            reverse('user_settings:api_update_theme'),
            data=json.dumps({'theme': 'slate'}),
            content_type='application/json'
        )
        self.assertEqual(api_response.status_code, 200)
        data = api_response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['theme'], 'slate')

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.preferences.get('theme'), 'slate')

    def test_notification_settings_update(self):
        """User can update notification preferences."""
        self.client.login(email=self.user.email, password=self.password)
        response = self.client.post(reverse('user_settings:notifications'), {
            'email_frequency': 'daily',
            'task_alerts': 'on',
            'bug_alerts': 'on',
            'chat_mentions': 'on',
            'meeting_reminders': 'on'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        notifs = self.profile.preferences.get('notifications', {})
        self.assertEqual(notifs.get('email_frequency'), 'daily')
        self.assertTrue(notifs.get('task_alerts'))

    def test_workspace_settings_strict_rbac(self):
        """Contributors cannot edit workspace settings; Workspace Admins can."""
        # 1. Contributor tries to edit workspace
        self.client.login(email=self.user.email, password=self.password)
        forbidden_response = self.client.post(
            reverse('user_settings:workspace_detail', kwargs={'slug': self.workspace.slug}),
            {'name': 'Hacked Workspace', 'max_seats': 50, 'storage_quota_mb': 200}
        )
        self.assertEqual(forbidden_response.status_code, 403)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, "Quantum Core")

        # 2. Admin edits workspace
        self.client.login(email=self.admin_user.email, password=self.password)
        allowed_response = self.client.post(
            reverse('user_settings:workspace_detail', kwargs={'slug': self.workspace.slug}),
            {'name': 'Quantum Core Renovated', 'max_seats': 20, 'storage_quota_mb': 100},
            follow=True
        )
        self.assertEqual(allowed_response.status_code, 200)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, "Quantum Core Renovated")
        self.assertEqual(self.workspace.max_seats, 20)

    def test_global_search_by_task_and_bug_id(self):
        """Global omnibar search can find tasks and bugs by 6-digit ID and code."""
        self.client.login(email=self.user.email, password=self.password)

        # Create Task with 6-digit ID
        task = Task.objects.create(
            workspace=self.workspace,
            task_code="619347",
            title="Implement Realtime Voice Signaling",
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            reporter=self.admin_user,
            assignee=self.user
        )

        # Create Bug with code
        bug = Bug.objects.create(
            workspace=self.workspace,
            bug_code="B-882316",
            title="Null pointer in audio packet jitter buffer",
            status=BugStatus.OPEN,
            severity=BugSeverity.SEV1,
            reporter=self.user
        )

        # Search by exact task ID 619347
        res1 = self.client.get(reverse('core:global_search_api') + '?q=619347')
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertGreater(len(data1['results']), 0)
        task_match = next((item for item in data1['results'] if item['type'] == 'task'), None)
        self.assertIsNotNone(task_match)
        self.assertEqual(task_match['code'], '#619347')
        self.assertEqual(task_match['title'], 'Implement Realtime Voice Signaling')

        # Search with hash prefix #619347
        res2 = self.client.get(reverse('core:global_search_api') + '?q=%23619347')
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(any(i['code'] == '#619347' for i in data2['results']))

        # Search by bug code B-882316
        res3 = self.client.get(reverse('core:global_search_api') + '?q=B-882316')
        self.assertEqual(res3.status_code, 200)
        data3 = res3.json()
        bug_match = next((item for item in data3['results'] if item['type'] == 'bug'), None)
        self.assertIsNotNone(bug_match)
        self.assertEqual(bug_match['code'], 'B-882316')

        # Search by raw numeric bug code 882316
        res4 = self.client.get(reverse('core:global_search_api') + '?q=882316')
        self.assertEqual(res4.status_code, 200)
        data4 = res4.json()
        self.assertTrue(any(i['code'] == 'B-882316' for i in data4['results']))

    def test_integrations_settings_renders_without_reverse_error(self):
        """Settings Integrations view renders cleanly without NoReverseMatch errors."""
        self.client.login(email=self.user.email, password=self.password)
        response = self.client.get(reverse('user_settings:integrations'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platform Integrations")
        self.assertContains(response, "WebRTC / Jitsi Meet")
        self.assertContains(response, "whsec_")

    def test_profile_banner_url_preset_and_removal(self):
        """User can link external banner photo, apply gradient preset, and remove banner."""
        self.client.login(email=self.user.email, password=self.password)

        # 1. Update banner with external URL
        test_url = "https://images.unsplash.com/photo-1518770660439-4636190af475"
        resp1 = self.client.post(reverse('user_settings:profile'), {
            'headline': 'Full-Stack Developer',
            'banner_url': test_url,
        }, follow=True)
        self.assertEqual(resp1.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.banner, test_url)

        # 2. Update banner with gradient preset
        resp2 = self.client.post(reverse('user_settings:profile'), {
            'headline': 'Full-Stack Developer',
            'banner_preset': 'cyberpunk',
        }, follow=True)
        self.assertEqual(resp2.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.banner, 'preset:cyberpunk')

        # 3. Remove banner
        resp3 = self.client.post(reverse('user_settings:profile'), {
            'action': 'remove_banner'
        }, follow=True)
        self.assertEqual(resp3.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.banner, '')

