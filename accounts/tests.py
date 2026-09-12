from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from .models import User, UserProfile, UserRole
from .tokens import account_verification_token


class AccountsModelAndViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.test_email = "alex@aetherspace.dev"
        self.test_password = "SecurePassword123!"
        self.user = User.objects.create_user(
            email=self.test_email,
            password=self.test_password,
            full_name="Alex River"
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            headline="Senior Full Stack Engineer"
        )

    def test_custom_user_creation_and_uuid(self):
        self.assertEqual(self.user.email, self.test_email)
        self.assertEqual(self.user.username, self.test_email)
        self.assertEqual(self.user.full_name, "Alex River")
        self.assertIsNotNone(self.user.id)
        self.assertTrue(self.user.check_password(self.test_password))
        self.assertEqual(str(self.user), "Alex River")
        self.assertEqual(self.user.profile.headline, "Senior Full Stack Engineer")
        self.assertEqual(self.user.role, UserRole.CONTRIBUTOR)
        self.assertTrue(self.user.is_contributor_role)
        self.assertFalse(self.user.is_manager_role)
        self.assertFalse(self.user.is_admin_role)
        self.assertFalse(self.user.is_verified)

    def test_superuser_creation(self):
        admin = User.objects.create_superuser(
            email="admin@aetherspace.dev",
            password="AdminPassword123!"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_verified)
        self.assertEqual(admin.role, UserRole.ADMIN)
        self.assertTrue(admin.is_admin_role)

    def test_login_view_get(self):
        url = reverse('accounts:login')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome back!")

    def test_login_view_post_success_with_remember_me(self):
        url = reverse('accounts:login')
        response = self.client.post(url, {
            'email': self.test_email,
            'password': self.test_password,
            'remember_me': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('workspaces:dashboard'), target_status_code=302)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_login_view_post_success_without_remember_me(self):
        url = reverse('accounts:login')
        response = self.client.post(url, {
            'email': self.test_email,
            'password': self.test_password,
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('workspaces:dashboard'), target_status_code=302)
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_login_view_post_invalid_password(self):
        url = reverse('accounts:login')
        response = self.client.post(url, {
            'email': self.test_email,
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email address or password.")

    def test_login_view_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        url = reverse('accounts:login')
        response = self.client.post(url, {
            'email': self.test_email,
            'password': self.test_password,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email address or password.")

    def test_register_view_get(self):
        url = reverse('accounts:register')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create your account")

    def test_register_view_post_success(self):
        url = reverse('accounts:register')
        response = self.client.post(url, {
            'full_name': 'Morgan Vance',
            'email': 'morgan@aetherspace.dev',
            'password': 'ComplexPassword88!',
            'confirm_password': 'ComplexPassword88!',
            'agree_terms': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:verification'))
        new_user = User.objects.filter(email='morgan@aetherspace.dev').first()
        self.assertIsNotNone(new_user)
        self.assertEqual(new_user.full_name, 'Morgan Vance')
        self.assertEqual(new_user.role, UserRole.CONTRIBUTOR)
        self.assertFalse(new_user.is_verified)
        self.assertIsNotNone(new_user.profile)

    def test_register_view_post_duplicate_email(self):
        url = reverse('accounts:register')
        response = self.client.post(url, {
            'full_name': 'Another Alex',
            'email': self.test_email,
            'password': 'ComplexPassword88!',
            'confirm_password': 'ComplexPassword88!',
            'agree_terms': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this email address already exists.")

    def test_register_view_post_mismatched_passwords(self):
        url = reverse('accounts:register')
        response = self.client.post(url, {
            'full_name': 'Taylor Reed',
            'email': 'taylor@aetherspace.dev',
            'password': 'ComplexPassword88!',
            'confirm_password': 'DifferentPassword99!',
            'agree_terms': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match.")

    def test_register_view_post_missing_terms(self):
        url = reverse('accounts:register')
        response = self.client.post(url, {
            'full_name': 'Jordan Lee',
            'email': 'jordan@aetherspace.dev',
            'password': 'ComplexPassword88!',
            'confirm_password': 'ComplexPassword88!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You must agree to the Terms of Service")

    def test_logout_view(self):
        self.client.login(username=self.test_email, password=self.test_password)
        url = reverse('accounts:logout')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:login'))

    def test_forgot_password_view_post(self):
        url = reverse('accounts:forgot_password')
        response = self.client.post(url, {'email': self.test_email})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recovery email dispatched")

    def test_reset_password_confirm_view_valid_and_invalid(self):
        # Generate valid token
        token = default_token_generator.make_token(self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))

        # Test valid token GET
        url = reverse('accounts:reset_password_confirm', kwargs={'uidb64': uidb64, 'token': token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reset your password")

        # Test valid token POST password change
        response = self.client.post(url, {
            'password': 'BrandNewPassword999!',
            'confirm_password': 'BrandNewPassword999!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:login'))

        # Check updated password
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPassword999!'))

        # Re-using the same token should now be invalid
        response_invalid = self.client.get(url)
        self.assertEqual(response_invalid.status_code, 200)
        self.assertContains(response_invalid, "Link Invalid or Expired")

    def test_account_verification_flow(self):
        # Generate verification token
        token = account_verification_token.make_token(self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))

        # Test invalid token
        invalid_url = reverse('accounts:verify_email_confirm', kwargs={'uidb64': uidb64, 'token': 'fake-token-123'})
        response = self.client.get(invalid_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This verification link is invalid or has expired")

        # Test valid token confirmation
        valid_url = reverse('accounts:verify_email_confirm', kwargs={'uidb64': uidb64, 'token': token})
        response = self.client.get(valid_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('core:landing'))

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)


class Phase12ProfileModuleTest(TestCase):
    def setUp(self):
        from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
        from tasks.models import Task, TaskStatus, TaskPriority, TaskActivity
        from bugs.models import Bug, BugStatus, BugSeverity, BugPriority, BugActivity
        from PIL import Image
        import io
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client = Client()
        self.password = "UserPassword123!"

        # Create primary test user
        self.user = User.objects.create_user(
            email="yaswanth@aetherspace.dev",
            password=self.password,
            full_name="Yaswanth M"
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            headline="Lead Systems Architect",
            bio="Building high-performance agile workspace platforms.",
            phone="+1 (555) 123-4567"
        )

        # Create teammate user
        self.teammate = User.objects.create_user(
            email="sarah.teammate@aetherspace.dev",
            password=self.password,
            full_name="Sarah Chen"
        )
        self.teammate_profile = UserProfile.objects.create(
            user=self.teammate,
            headline="Product Designer"
        )

        # Create stranger user (no shared workspace)
        self.stranger = User.objects.create_user(
            email="stranger@other.dev",
            password=self.password,
            full_name="Stranger User"
        )

        # Create workspace and add user and teammate
        self.workspace = Workspace.objects.create(
            name="Orion Space",
            slug="orion-space",
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status='ACTIVE'
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.teammate,
            role=WorkspaceRole.CONTRIBUTOR,
            status='ACTIVE'
        )

        # Create sample tasks
        self.task1 = Task.objects.create(
            task_code="619347",
            workspace=self.workspace,
            title="Design Profile Mockup Screens",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            assignee=self.user,
            reporter=self.teammate
        )
        self.task2 = Task.objects.create(
            task_code="619348",
            workspace=self.workspace,
            title="Implement Avatar Compression",
            status=TaskStatus.DONE,
            priority=TaskPriority.URGENT,
            assignee=self.user,
            reporter=self.user
        )

        # Create sample bugs
        self.bug1 = Bug.objects.create(
            bug_code="B-882316",
            workspace=self.workspace,
            title="Profile modal z-index glitch",
            status=BugStatus.OPEN,
            severity=BugSeverity.SEV2,
            priority=BugPriority.HIGH,
            assignee=self.user,
            reporter=self.teammate
        )

        # Create sample activity
        TaskActivity.objects.create(
            task=self.task1,
            actor=self.user,
            action='STATUS_CHANGED',
            message="Moved task to In Progress"
        )

    def test_my_profile_requires_authentication(self):
        url = reverse('accounts:profile')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login/', resp.url)

    def test_core_profile_redirects_to_accounts_profile(self):
        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.get(reverse('core:profile'))
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('accounts:profile'))

    def test_my_profile_overview_loads_with_metrics_and_tabs(self):
        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.get(reverse('accounts:profile'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Yaswanth M")
        self.assertContains(resp, "Lead Systems Architect")
        self.assertContains(resp, "Building high-performance agile workspace platforms.")
        self.assertContains(resp, "Assigned Tasks")
        self.assertContains(resp, "Assigned Defects")
        self.assertContains(resp, "Workspaces")
        self.assertContains(resp, "Total Activity")
        self.assertContains(resp, "#619347")
        self.assertContains(resp, "B-882316")

    def test_edit_profile_get_view(self):
        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.get(reverse('accounts:profile_edit'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Yaswanth M")
        self.assertContains(resp, "Lead Systems Architect")
        self.assertContains(resp, "Upload & Compress Avatar")

    def test_edit_profile_post_updates_information(self):
        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.post(reverse('accounts:profile_edit'), {
            'action': 'update_profile',
            'full_name': 'Yaswanth M Updated',
            'headline': 'Chief Architect & Founder',
            'bio': 'Updated bio content here.',
            'phone': '+1 (555) 999-8888',
            'timezone': 'Asia/Kolkata',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('accounts:profile'))

        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, 'Yaswanth M Updated')
        self.assertEqual(self.user.timezone, 'Asia/Kolkata')
        self.assertEqual(self.user.profile.headline, 'Chief Architect & Founder')
        self.assertEqual(self.user.profile.bio, 'Updated bio content here.')
        self.assertEqual(self.user.profile.phone, '+1 (555) 999-8888')

    def test_avatar_upload_under_500kb_success(self):
        from PIL import Image
        import io
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Generate a small 100x100 RGB image in memory
        img = Image.new('RGB', (100, 100), color=(73, 109, 137))
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='JPEG', quality=80)
        img_bytes = img_buffer.getvalue()

        upload_file = SimpleUploadedFile(
            name="avatar.jpg",
            content=img_bytes,
            content_type="image/jpeg"
        )

        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.post(reverse('accounts:profile_edit'), {
            'action': 'update_avatar',
            'avatar_file': upload_file,
        })
        self.assertEqual(resp.status_code, 302)

        self.user.refresh_from_db()
        self.assertTrue(bool(self.user.avatar))
        self.assertTrue(self.user.avatar.endswith('.jpg'))

    def test_avatar_upload_over_500kb_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Create a dummy file of 600 KB
        large_bytes = b"0" * (600 * 1024)
        upload_file = SimpleUploadedFile(
            name="large_photo.jpg",
            content=large_bytes,
            content_type="image/jpeg"
        )

        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.post(reverse('accounts:profile_edit'), {
            'action': 'update_avatar',
            'avatar_file': upload_file,
        })
        self.assertEqual(resp.status_code, 302)

        self.user.refresh_from_db()
        # Should not have updated to a large photo
        self.assertNotIn('large_photo', self.user.avatar)

    def test_avatar_link_external_url(self):
        self.client.login(email=self.user.email, password=self.password)
        url_input = "https://avatars.githubusercontent.com/u/1234567?v=4"
        resp = self.client.post(reverse('accounts:profile_edit'), {
            'action': 'update_avatar',
            'avatar_url': url_input,
        })
        self.assertEqual(resp.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, url_input)

    def test_avatar_apply_preset_color(self):
        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.post(reverse('accounts:profile_edit'), {
            'action': 'update_avatar',
            'preset_color': 'teal',
        })
        self.assertEqual(resp.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, 'preset:teal')

    def test_avatar_remove_restores_initials(self):
        self.user.avatar = "https://example.com/avatar.jpg"
        self.user.save()

        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.post(reverse('accounts:profile_avatar_remove'))
        self.assertEqual(resp.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, "")

    def test_profile_tasks_view_filters(self):
        self.client.login(email=self.user.email, password=self.password)

        # 1. All tasks
        resp = self.client.get(reverse('accounts:profile_tasks'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Design Profile Mockup Screens")
        self.assertContains(resp, "Implement Avatar Compression")

        # 2. Filter by status IN_PROGRESS
        resp_filter = self.client.get(reverse('accounts:profile_tasks') + "?status=IN_PROGRESS")
        self.assertEqual(resp_filter.status_code, 200)
        self.assertContains(resp_filter, "Design Profile Mockup Screens")
        self.assertNotContains(resp_filter, "Implement Avatar Compression")

        # 3. Search query
        resp_q = self.client.get(reverse('accounts:profile_tasks') + "?q=Avatar")
        self.assertEqual(resp_q.status_code, 200)
        self.assertContains(resp_q, "Implement Avatar Compression")
        self.assertNotContains(resp_q, "Design Profile Mockup Screens")

    def test_profile_bugs_view_filters(self):
        self.client.login(email=self.user.email, password=self.password)

        resp = self.client.get(reverse('accounts:profile_bugs'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "B-882316")
        self.assertContains(resp, "Profile modal z-index glitch")

        # Filter by severity SEV2
        resp_sev = self.client.get(reverse('accounts:profile_bugs') + "?severity=SEV2")
        self.assertEqual(resp_sev.status_code, 200)
        self.assertContains(resp_sev, "B-882316")

        # Filter by non-matching severity
        resp_none = self.client.get(reverse('accounts:profile_bugs') + "?severity=SEV1")
        self.assertEqual(resp_none.status_code, 200)
        self.assertNotContains(resp_none, "B-882316")

    def test_profile_activity_stream(self):
        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.get(reverse('accounts:profile_activity'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Text-based chronological audit")
        self.assertContains(resp, "Moved task to In Progress")

    def test_workspace_roles_view(self):
        self.client.login(email=self.user.email, password=self.password)
        resp = self.client.get(reverse('accounts:profile_roles'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Orion Space")
        self.assertContains(resp, "Admin")
        self.assertContains(resp, "Launch Workspace")

    def test_public_profile_allowed_for_teammate(self):
        self.client.login(email=self.user.email, password=self.password)
        url = reverse('accounts:public_profile', kwargs={'user_id': self.teammate.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sarah Chen")
        self.assertContains(resp, "Product Designer")
        self.assertContains(resp, "Start Direct Chat")

    def test_public_profile_forbidden_for_stranger(self):
        self.client.login(email=self.user.email, password=self.password)
        url = reverse('accounts:public_profile', kwargs={'user_id': self.stranger.id})
        resp = self.client.get(url)
        # Should be blocked with HTTP 403 Forbidden
        self.assertEqual(resp.status_code, 403)

