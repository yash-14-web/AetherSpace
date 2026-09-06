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
        self.assertRedirects(response, reverse('workspaces:dashboard'))
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 1209600)

    def test_login_view_post_success_without_remember_me(self):
        url = reverse('accounts:login')
        response = self.client.post(url, {
            'email': self.test_email,
            'password': self.test_password,
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('workspaces:dashboard'))
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
