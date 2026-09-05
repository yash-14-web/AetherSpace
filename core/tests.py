from django.test import TestCase, Client
from django.urls import reverse


class CoreViewsTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_landing_page_renders_successfully(self):
        url = reverse('core:landing')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AetherSpace")
        self.assertContains(response, "Your Team.")
        self.assertContains(response, "Your Workspace.")
        self.assertContains(response, "AetherSpace.")
        self.assertContains(response, "Task Management")
        self.assertContains(response, "Bug Tracking")
        self.assertContains(response, "Team Chat")
        self.assertContains(response, "Meet Hub")
        self.assertContains(response, "Calendar & Agenda")
        self.assertContains(response, "Files & Sharing")
        self.assertContains(response, "Collaborate Seamlessly")
        self.assertContains(response, "Secure & Private")
        self.assertContains(response, "Get Started Free")

    def test_custom_400_error_view(self):
        url = reverse('core:test_400')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Invalid Request", status_code=400)
        self.assertContains(response, "400", status_code=400)

    def test_custom_403_error_view_with_request_access(self):
        url = reverse('core:test_403')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Access Restricted", status_code=403)
        self.assertContains(response, "Request Access", status_code=403)

    def test_custom_404_error_view(self):
        url = reverse('core:test_404')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page Not Found", status_code=404)
        self.assertContains(response, "Return to Dashboard", status_code=404)

    def test_custom_500_error_view(self):
        url = reverse('core:test_500')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Internal Server Error", status_code=500)
        self.assertContains(response, "Reload Page", status_code=500)
