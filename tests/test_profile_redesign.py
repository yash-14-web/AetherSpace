import json
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, UserProfile, UserRole, ApprovalStatus
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole


class ProfileRedesignAndLockedBannerTests(TestCase):
    def setUp(self):
        self.client = Client()

        # User 1: Primary Developer
        self.developer = User.objects.create_user(
            email='alex.dev@aetherspace.dev',
            password='testpassword123',
            full_name='Alex Rivera',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
            contributor_id='ID-20002C',
        )
        self.profile, _ = UserProfile.objects.get_or_create(user=self.developer)

        # User 2: Teammate in same workspace
        self.teammate = User.objects.create_user(
            email='sarah.mgr@aetherspace.dev',
            password='testpassword123',
            full_name='Sarah Chen',
            role=UserRole.MANAGER,
            approval_status=ApprovalStatus.APPROVED,
            contributor_id='ID-10001A',
        )
        self.teammate_profile, _ = UserProfile.objects.get_or_create(user=self.teammate)

        # User 3: Outsider in separate workspace
        self.outsider = User.objects.create_user(
            email='outsider@external.dev',
            password='testpassword123',
            full_name='Outsider User',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
        )
        self.outsider_profile, _ = UserProfile.objects.get_or_create(user=self.outsider)

        # Workspaces
        self.shared_workspace = Workspace.objects.create(
            name='Core Engineering Hub',
            slug='core-engineering-hub',
            owner=self.teammate,
        )
        self.private_workspace = Workspace.objects.create(
            name='Outsider Enclave',
            slug='outsider-enclave',
            owner=self.outsider,
        )

        # Shared memberships
        WorkspaceMembership.objects.create(
            workspace=self.shared_workspace,
            user=self.teammate,
            role=WorkspaceRole.MANAGER,
            functional_role='Engineering Lead',
            role_tag='Backend Architecture',
            status=MembershipStatus.ACTIVE,
        )
        WorkspaceMembership.objects.create(
            workspace=self.shared_workspace,
            user=self.developer,
            role=WorkspaceRole.CONTRIBUTOR,
            functional_role='Senior Frontend Engineer',
            role_tag='UI/UX Systems',
            status=MembershipStatus.ACTIVE,
        )

        # Isolated membership
        WorkspaceMembership.objects.create(
            workspace=self.private_workspace,
            user=self.outsider,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )

    # -------------------------------------------------------------------------
    # Banner & Header Redesign Tests
    # -------------------------------------------------------------------------
    def test_default_banner_renders_on_every_profile(self):
        """The shared default moonlit mountain banner must render on all profile pages."""
        self.client.force_login(self.developer)
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)

        # Permanent default scenic mountain asset must be used
        self.assertContains(response, 'default_banner_mountain.webp')

    def test_no_change_banner_or_upload_controls_present(self):
        """Change banner buttons and banner upload inputs must be completely absent."""
        self.client.force_login(self.developer)

        # On Profile Overview
        profile_resp = self.client.get(reverse('accounts:profile'))
        self.assertNotContains(profile_resp, 'Change Banner')
        self.assertNotContains(profile_resp, 'banner_file')

        # On Profile Edit page
        edit_resp = self.client.get(reverse('accounts:profile_edit'))
        self.assertNotContains(edit_resp, 'Change Banner')
        self.assertNotContains(edit_resp, 'name="banner_file"')
        self.assertNotContains(edit_resp, 'Cover Banner Photo')

    def test_avatar_upload_functionality_preserved(self):
        """Avatar upload forms and controls remain intact on the edit profile page."""
        self.client.force_login(self.developer)
        response = self.client.get(reverse('accounts:profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'avatar_file')
        self.assertContains(response, 'Upload Image')
        self.assertContains(response, 'preset_color')

    def test_identity_badges_and_workspace_row_rendering(self):
        """Identity section and workspace role row render clean, uncrowded data."""
        self.client.force_login(self.developer)
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)

        # Name and Badges
        self.assertContains(response, 'Alex Rivera')
        self.assertContains(response, 'ID-20002C')
        self.assertContains(response, 'CONTRIBUTOR')

        # Workspace details row: Job Title · Tagging Department · Workspace Name
        self.assertContains(response, 'Senior Frontend Engineer')
        self.assertContains(response, 'UI/UX Systems')
        self.assertContains(response, 'Core Engineering Hub')

    def test_long_display_names_and_empty_fields_handling(self):
        """Profiles with long names and missing optional fields render cleanly without errors."""
        long_name_user = User.objects.create_user(
            email='longname@aetherspace.dev',
            password='testpassword123',
            full_name='Dr. Maximilian Alexander Bartholomew Montgomery-Smith III',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
        )
        WorkspaceMembership.objects.create(
            workspace=self.shared_workspace,
            user=long_name_user,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE,
        )
        long_name_profile, _ = UserProfile.objects.get_or_create(user=long_name_user)
        long_name_profile.bio = ''
        long_name_profile.phone = ''
        long_name_profile.headline = ''
        long_name_profile.save()

        self.client.force_login(long_name_user)
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dr. Maximilian Alexander Bartholomew Montgomery-Smith III')
        self.assertContains(response, 'default_banner_mountain.webp')

    def test_public_profile_workspace_isolation_and_shared_workspaces(self):
        """Teammate profile displays shared workspaces and default banner; outsiders get 403."""
        self.client.force_login(self.developer)

        # Teammate in same workspace: 200 OK
        teammate_url = reverse('accounts:public_profile', kwargs={'user_id': self.teammate.id})
        resp = self.client.get(teammate_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'default_banner_mountain.webp')
        self.assertContains(resp, 'Sarah Chen')
        self.assertContains(resp, 'Core Engineering Hub')

        # Outsider with no shared workspace: 403 Forbidden
        outsider_url = reverse('accounts:public_profile', kwargs={'user_id': self.outsider.id})
        outsider_resp = self.client.get(outsider_url)
        self.assertEqual(outsider_resp.status_code, 403)

    # -------------------------------------------------------------------------
    # Editable Skills Tests
    # -------------------------------------------------------------------------
    def test_skills_displayed_from_persistent_data(self):
        """Saved skills from profile.preferences are displayed as tags on the profile page."""
        self.profile.set_skills(['Python', 'Django', 'Tailwind CSS'])
        self.profile.save()

        self.client.force_login(self.developer)
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Python')
        self.assertContains(response, 'Django')
        self.assertContains(response, 'Tailwind CSS')

    def test_authorized_user_can_add_skill_via_api(self):
        """Authorized user can add a skill via the JSON API endpoint."""
        self.profile.set_skills(['Python', 'Django'])
        self.profile.save()

        self.client.force_login(self.developer)
        url = reverse('accounts:profile_skills_update')
        payload = json.dumps({'action': 'add', 'skill': 'PostgreSQL'})
        response = self.client.post(url, data=payload, content_type='application/json')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('PostgreSQL', data['skills'])

        # Verify persistence
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.skills, ['Python', 'Django', 'PostgreSQL'])

    def test_authorized_user_can_remove_skill_via_api(self):
        """Authorized user can remove a skill via the JSON API endpoint."""
        self.profile.set_skills(['Python', 'Django', 'Docker'])
        self.profile.save()

        self.client.force_login(self.developer)
        url = reverse('accounts:profile_skills_update')
        payload = json.dumps({'action': 'remove', 'skill': 'Django'})
        response = self.client.post(url, data=payload, content_type='application/json')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertNotIn('Django', data['skills'])

        # Verify persistence
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.skills, ['Python', 'Docker'])

    def test_skills_validation_rejects_empty_and_deduplicates(self):
        """Skills updates reject whitespace and deduplicate items case-insensitively."""
        self.client.force_login(self.developer)
        url = reverse('accounts:profile_skills_update')
        payload = json.dumps({
            'skills': ['  ', 'Python', 'PYTHON', 'Django', '   PostgreSQL   ']
        })
        response = self.client.post(url, data=payload, content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        # Should contain Python only once, Django, and PostgreSQL (trimmed)
        self.assertEqual(self.profile.skills, ['Python', 'Django', 'PostgreSQL'])

    def test_skills_persist_via_profile_edit_form(self):
        """Updating skills via the standard edit profile form persists without altering other fields."""
        self.profile.headline = 'Lead Systems Architect'
        self.profile.bio = 'Experienced engineer focused on distributed systems.'
        self.profile.save()

        self.client.force_login(self.developer)
        url = reverse('accounts:profile_edit')
        response = self.client.post(url, data={
            'action': 'update_profile',
            'full_name': 'Alex Rivera',
            'headline': 'Lead Systems Architect',
            'bio': 'Experienced engineer focused on distributed systems.',
            'phone': '+1234567890',
            'timezone': 'UTC',
            'skills': 'Python, Django, React, GraphQL',
        })
        self.assertRedirects(response, reverse('accounts:profile'))

        # Verify skills and profile fields
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.skills, ['Python', 'Django', 'React', 'GraphQL'])
        self.assertEqual(self.profile.headline, 'Lead Systems Architect')
        self.assertEqual(self.profile.bio, 'Experienced engineer focused on distributed systems.')

    def test_teammate_cannot_edit_another_users_skills(self):
        """Other users cannot modify a teammate's skills."""
        self.profile.set_skills(['Python', 'Django'])
        self.profile.save()

        # Login as teammate (Sarah Chen)
        self.client.force_login(self.teammate)
        url = reverse('accounts:profile_skills_update')
        # Teammate tries to modify skills via endpoint: endpoint always operates on request.user's profile
        payload = json.dumps({'skills': ['HackedSkill']})
        response = self.client.post(url, data=payload, content_type='application/json')

        # Teammate's own profile gets updated, but developer's profile is untouched
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.skills, ['Python', 'Django'])
        self.assertNotIn('HackedSkill', self.profile.skills)

        # Teammate viewing Developer's public profile has no edit controls
        public_url = reverse('accounts:public_profile', kwargs={'user_id': self.developer.id})
        public_resp = self.client.get(public_url)
        self.assertEqual(public_resp.status_code, 200)
        self.assertNotContains(public_resp, 'Edit Skills')
        self.assertNotContains(public_resp, 'startEditing()')
