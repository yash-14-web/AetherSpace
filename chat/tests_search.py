from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole
from chat.views import get_chat_sidebar_context

User = get_user_model()


class PeopleSearchUXTests(TestCase):
    """
    Test suite for People Search UX requirements and security boundaries.
    Requirement: People MUST NOT be displayed when search query is empty.
    """

    def setUp(self):
        self.client = Client()

        # Primary user
        self.user = User.objects.create_user(
            email='alice@aetherspace.dev',
            password='TestPassword123!',
            first_name='Alice',
            last_name='Engineer',
            username='alice_eng'
        )

        # Teammate in same workspace
        self.bob = User.objects.create_user(
            email='bob@aetherspace.dev',
            password='TestPassword123!',
            first_name='Bob',
            last_name='Designer',
            username='bob_des'
        )

        # External registered user (different or no workspace)
        self.charlie = User.objects.create_user(
            email='charlie@external.dev',
            password='TestPassword123!',
            first_name='Charlie',
            last_name='Consultant',
            username='charlie_ext'
        )

        # Workspace
        self.workspace = Workspace.objects.create(
            name='Orion Project',
            slug='orion-project',
            owner=self.user
        )

        # Memberships
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.bob,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        self.search_url = reverse('chat:api_search_users', kwargs={'slug': self.workspace.slug})

    def test_search_empty_query_strictly_returns_empty_list(self):
        """
        Verify that an empty query, query with only spaces, or missing query parameter
        returns strictly an empty list and never leaks registered users.
        """
        self.client.force_login(self.user)

        # 1. Empty parameter
        response = self.client.get(self.search_url, {'q': ''})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['users'], [], "Empty search query must return an empty list of users.")

        # 2. Whitespace-only parameter
        response = self.client.get(self.search_url, {'q': '    '})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['users'], [], "Whitespace query must return an empty list of users.")

        # 3. Missing parameter
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['users'], [], "Missing query must return an empty list of users.")

    def test_search_matches_name_email_and_username(self):
        """
        Verify that searching by full name, email, or username returns matching users.
        """
        self.client.force_login(self.user)

        # Search by name
        response = self.client.get(self.search_url, {'q': 'Bob'})
        self.assertEqual(response.status_code, 200)
        users = response.json()['users']
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]['email'], 'bob@aetherspace.dev')
        self.assertTrue(users[0]['is_member'])
        self.assertEqual(users[0]['role_display'], 'Workspace Member')

        # Search by email
        response = self.client.get(self.search_url, {'q': 'charlie@external.dev'})
        self.assertEqual(response.status_code, 200)
        users = response.json()['users']
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]['email'], 'charlie@external.dev')
        self.assertFalse(users[0]['is_member'])
        self.assertEqual(users[0]['role_display'], 'Direct Chat')

        # Search by username
        response = self.client.get(self.search_url, {'q': 'bob_des'})
        self.assertEqual(response.status_code, 200)
        users = response.json()['users']
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]['email'], 'bob@aetherspace.dev')

    def test_search_excludes_current_authenticated_user(self):
        """
        Verify that the searching user never appears in their own search results.
        """
        self.client.force_login(self.user)
        response = self.client.get(self.search_url, {'q': 'alice'})
        self.assertEqual(response.status_code, 200)
        users = response.json()['users']
        user_ids = [u['id'] for u in users]
        self.assertNotIn(str(self.user.id), user_ids)

    def test_search_no_results_for_unmatched_query(self):
        """
        Verify that a non-matching query returns an empty list.
        """
        self.client.force_login(self.user)
        response = self.client.get(self.search_url, {'q': 'nonexistent_person_xyz_123'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['users'], [])

    def test_search_requires_workspace_membership(self):
        """
        Non-members of the workspace cannot access the workspace user search endpoint.
        """
        self.client.force_login(self.charlie)  # Charlie is not in Orion Project
        response = self.client.get(self.search_url, {'q': 'Bob'})
        # Should redirect or return 403 based on @workspace_member_required
        self.assertIn(response.status_code, [302, 403])

    def test_chat_sidebar_context_does_not_preload_database_users(self):
        """
        Verify that get_chat_sidebar_context does not serialize/dump database users into page context.
        """
        context = get_chat_sidebar_context(self.workspace, self.user)
        self.assertNotIn('formatted_db_users', context, "Database users must not be preloaded into chat sidebar context.")
