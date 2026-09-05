from django.test import TestCase, Client
from django.urls import reverse
from .models import User, UserProfile


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

    def test_superuser_creation(self):
        admin = User.objects.create_superuser(
            email="admin@aetherspace.dev",
            password="AdminPassword123!"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_login_view_get(self):
        url = reverse('accounts:login')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign In to Workspace")

    def test_login_view_post_success(self):
        url = reverse('accounts:login')
        response = self.client.post(url, {
            'email': self.test_email,
            'password': self.test_password,
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('core:landing'))

    def test_login_view_post_invalid(self):
        url = reverse('accounts:login')
        response = self.client.post(url, {
            'email': self.test_email,
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email address or password.")

    def test_register_view_get(self):
        url = reverse('accounts:register')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Join AetherSpace")

    def test_register_view_post_success(self):
        url = reverse('accounts:register')
        response = self.client.post(url, {
            'full_name': 'Morgan Vance',
            'email': 'morgan@aetherspace.dev',
            'password': 'NewPassword123!',
            'confirm_password': 'NewPassword123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='morgan@aetherspace.dev').exists())

    def test_logout_view(self):
        self.client.login(username=self.test_email, password=self.test_password)
        url = reverse('accounts:logout')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:login'))
