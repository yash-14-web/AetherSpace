"""
Batch 6: Stack Trace Exposure Hardening Security Tests.
Validates that production-facing responses and API/AJAX endpoints never leak
internal implementation details, Python tracebacks, file paths, SQL queries,
secrets, or database connection information.

Remediates: py/stack-trace-exposure (CWE-209 / CWE-497).
"""

import json
from unittest.mock import patch
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import Http404

from core.middleware import (
    AetherSpaceGlobalErrorMiddleware,
    RateLimitExceeded,
    RequestTimeoutException,
    ServiceUnavailableException,
)
from core.views import error_403, error_500
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus

User = get_user_model()


class Batch6MiddlewareStackTraceExposureTests(TestCase):
    """
    Validates that AetherSpaceGlobalErrorMiddleware sanitizes all exception types
    when responding to AJAX / API requests and HTML requests.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = AetherSpaceGlobalErrorMiddleware(lambda req: None)
        self.user = User.objects.create_user(
            email="middleware.tester@aetherspace.dev",
            password="TestPassword123!",
            role="CONTRIBUTOR"
        )

    def test_rate_limit_exceeded_ajax_sanitized(self):
        """
        Alert 1: RateLimitExceeded must return controlled message, not str(exception).
        """
        sensitive_detail = "RateLimit: Client IP 10.0.0.1 exceeded 60req/min at /app/core/limits.py SECRET_KEY=xyz"
        exc = RateLimitExceeded(sensitive_detail, retry_after=45)

        request = self.factory.get('/api/test/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        response = self.middleware.process_exception(request, exc)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '45')

        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['status_code'], 429)
        self.assertEqual(data['retry_after'], 45)
        self.assertIn("Too Many Requests", data['error'])

        # Verify no sensitive details leaked
        raw_body = response.content.decode('utf-8')
        self.assertNotIn(sensitive_detail, raw_body)
        self.assertNotIn("SECRET_KEY", raw_body)
        self.assertNotIn("10.0.0.1", raw_body)
        self.assertNotIn("/app/core/limits.py", raw_body)

    def test_request_timeout_ajax_sanitized(self):
        """
        Alert 2: RequestTimeoutException must return controlled message, not str(exception).
        """
        sensitive_detail = "Timeout query after 30s: SELECT * FROM sensitive_tokens WHERE id=1; Host db.internal:5432"
        exc = RequestTimeoutException(sensitive_detail)

        request = self.factory.get('/api/test/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        response = self.middleware.process_exception(request, exc)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 408)

        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['status_code'], 408)
        self.assertIn("Request Timed Out", data['error'])

        # Verify no sensitive details leaked
        raw_body = response.content.decode('utf-8')
        self.assertNotIn(sensitive_detail, raw_body)
        self.assertNotIn("SELECT * FROM", raw_body)
        self.assertNotIn("db.internal", raw_body)

    def test_service_unavailable_ajax_sanitized(self):
        """
        Alert 3: ServiceUnavailableException must return controlled message, not str(exception).
        """
        sensitive_detail = "Supabase bucket connection failed: s3://aetherspace-vault/auth_keys/ with token Bearer abc123def456"
        exc = ServiceUnavailableException(sensitive_detail)

        request = self.factory.get('/api/test/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        response = self.middleware.process_exception(request, exc)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 503)

        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['status_code'], 503)
        self.assertIn("Service Unavailable", data['error'])

        # Verify no sensitive details leaked
        raw_body = response.content.decode('utf-8')
        self.assertNotIn(sensitive_detail, raw_body)
        self.assertNotIn("Bearer abc123def456", raw_body)
        self.assertNotIn("s3://", raw_body)

    def test_unhandled_500_ajax_sanitized(self):
        """
        Alert 4: Unhandled server exception must return safe JSON 500 with correlation error_id.
        """
        sensitive_detail = "django.db.utils.OperationalError: server closed the connection unexpectedly /app/aetherspace/db.py password=admin_pass_999"
        exc = RuntimeError(sensitive_detail)

        request = self.factory.get('/api/test/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        response = self.middleware.process_exception(request, exc)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 500)

        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['status_code'], 500)
        self.assertIn('error_id', data)
        self.assertTrue(data['error_id'].startswith('ERR-500-'))
        self.assertEqual(data['error'], 'Internal Server Error — Something went wrong on our end.')

        # Verify no sensitive details leaked
        raw_body = response.content.decode('utf-8')
        self.assertNotIn(sensitive_detail, raw_body)
        self.assertNotIn("password=admin_pass_999", raw_body)
        self.assertNotIn("django.db.utils", raw_body)
        self.assertNotIn("/app/aetherspace/db.py", raw_body)

    @override_settings(DEBUG=False)
    def test_unhandled_500_html_in_production_returns_controlled_error_page(self):
        """
        Alert 4 (HTML production mode): Unhandled server exception returns controlled 500 page.
        """
        sensitive_detail = "Traceback (most recent call last):\n  File '/app/aetherspace/secrets.py', line 42\nException: SECRET_KEY=prod_key"
        exc = RuntimeError(sensitive_detail)

        request = self.factory.get('/some-page/')
        request.user = self.user
        response = self.middleware.process_exception(request, exc)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 500)

        content = response.content.decode('utf-8')
        self.assertIn("Something Went Wrong", content)
        self.assertIn("ERR-500-", content)
        self.assertNotIn("Traceback (most recent call last)", content)
        self.assertNotIn("/app/aetherspace/secrets.py", content)
        self.assertNotIn("SECRET_KEY=prod_key", content)

    @override_settings(DEBUG=True)
    def test_unhandled_500_html_in_debug_returns_none_for_django_developer_debugging(self):
        """
        Verify that in local development DEBUG=True, HTML requests return None so Django's
        developer debugging remains fully available.
        """
        request = self.factory.get('/some-page/')
        exc = ValueError("Dev debug error")
        response = self.middleware.process_exception(request, exc)
        self.assertIsNone(response)

    def test_permission_denied_sanitized(self):
        """
        PermissionDenied handling does not expose multiline tracebacks or internal SQL.
        """
        malicious_msg = "Traceback (most recent call last):\n  File '/app/models.py', line 10\nSELECT * FROM auth_user"
        exc = PermissionDenied(malicious_msg)

        request = self.factory.get('/api/forbidden/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        response = self.middleware.process_exception(request, exc)

        self.assertEqual(response.status_code, 403)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn("Access Restricted", data['error'])
        self.assertNotIn("Traceback", data['error'])
        self.assertNotIn("SELECT * FROM", data['error'])


class Batch6UserSettingsThemeApiSecurityTests(TestCase):
    """
    Validates that user_settings.views.api_update_theme does not leak stack traces or internal errors.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="theme.tester@aetherspace.dev",
            password="TestPassword123!",
            role="CONTRIBUTOR"
        )
        self.client.login(email=self.user.email, password="TestPassword123!")

    def test_theme_api_unexpected_exception_returns_safe_json_500(self):
        """
        Alert 5: api_update_theme unexpected exception must return generic 500 message.
        """
        sensitive_msg = "OperationalError: connection to '192.168.1.50:5432' failed password=dbpass123 SELECT * FROM users"

        with patch('user_settings.views.UserProfile.objects.get_or_create', side_effect=RuntimeError(sensitive_msg)):
            response = self.client.post(
                reverse('user_settings:api_update_theme'),
                data=json.dumps({'theme': 'obsidian'}),
                content_type='application/json'
            )

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'An unexpected error occurred while updating theme settings.')

        # Verify sensitive information is NOT leaked in response
        raw_body = response.content.decode('utf-8')
        self.assertNotIn(sensitive_msg, raw_body)
        self.assertNotIn("192.168.1.50", raw_body)
        self.assertNotIn("password=dbpass123", raw_body)
        self.assertNotIn("SELECT * FROM", raw_body)

    def test_theme_api_invalid_json_returns_400_not_500(self):
        """
        Validates client error preservation (Section 14): malformed JSON produces 400 Bad Request.
        """
        response = self.client.post(
            reverse('user_settings:api_update_theme'),
            data="{invalid-json-body",
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'Invalid JSON body.')


class Batch6WorkspacesAccessRequestSecurityTests(TestCase):
    """
    Validates that workspaces.views.submit_access_request does not leak stack traces or internal errors.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="request.tester@aetherspace.dev",
            password="TestPassword123!",
            role="CONTRIBUTOR"
        )
        self.workspace = Workspace.objects.create(
            name="Security Test WS",
            slug="security-test-ws",
            owner=self.user
        )
        self.client.login(email=self.user.email, password="TestPassword123!")

    def test_submit_access_request_ajax_exception_returns_safe_json_500(self):
        """
        Alert 6: submit_access_request unexpected exception must return generic JSON 500 message.
        """
        sensitive_msg = "django.db.utils.IntegrityError: duplicate key value /app/aetherspace/models.py SECRET_KEY=vault_secret_999"

        with patch('workspaces.views.GlobalAccessRequest.objects.create', side_effect=Exception(sensitive_msg)):
            response = self.client.post(
                reverse('workspaces:submit_access_request'),
                data={
                    'workspace_slug': self.workspace.slug,
                    'action': 'workspace.access',
                    'reason': 'Need access for security compliance testing',
                    'goal_description': 'Emergency audit of workspace assets',
                    'urgency': 'NORMAL',
                    'duration': '1_DAY',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )

        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(
            data['message'],
            "Failed to submit access request due to an internal server error. Please try again later."
        )

        # Verify sensitive information is NOT leaked in response
        raw_body = response.content.decode('utf-8')
        self.assertNotIn(sensitive_msg, raw_body)
        self.assertNotIn("SECRET_KEY=vault_secret_999", raw_body)
        self.assertNotIn("/app/aetherspace/models.py", raw_body)
        self.assertNotIn("IntegrityError", raw_body)

    def test_submit_access_request_html_exception_returns_safe_flash_message(self):
        """
        Alert 6 (HTML form): submit_access_request unexpected exception displays generic flash message.
        """
        sensitive_msg = "Database connection pool exhausted: postgresql://admin:secret_pass@db.local:5432/aetherspace"

        with patch('workspaces.views.GlobalAccessRequest.objects.create', side_effect=Exception(sensitive_msg)):
            response = self.client.post(
                reverse('workspaces:submit_access_request'),
                data={
                    'workspace_slug': self.workspace.slug,
                    'action': 'workspace.access',
                    'reason': 'Need access for security compliance testing',
                    'goal_description': 'Emergency audit of workspace assets',
                    'urgency': 'NORMAL',
                    'duration': '1_DAY',
                },
                follow=True
            )

        self.assertEqual(response.status_code, 200)
        messages_list = list(response.context['messages'])
        self.assertTrue(any("internal server error" in str(m) for m in messages_list))

        # Verify no sensitive connection string or password in rendered HTML
        content = response.content.decode('utf-8')
        self.assertNotIn(sensitive_msg, content)
        self.assertNotIn("secret_pass", content)
        self.assertNotIn("postgresql://", content)
        self.assertNotIn("db.local:5432", content)


class Batch6SensitiveDataLeakageMatrixTests(TestCase):
    """
    Simulates high-risk sensitive patterns across error handling paths:
    - "/app/aetherspace/secrets.py"
    - "SECRET_KEY=..."
    - "password=..."
    - "SELECT * FROM users"
    - "Traceback (most recent call last):"
    - "django.db.utils..."
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = AetherSpaceGlobalErrorMiddleware(lambda req: None)
        self.user = User.objects.create_user(
            email="sensitive.tester@aetherspace.dev",
            password="TestPassword123!",
            role="CONTRIBUTOR"
        )

    def test_sensitive_tokens_matrix_ajax(self):
        sensitive_payloads = [
            "/app/aetherspace/secrets.py",
            "SECRET_KEY=super_confidential_production_key_44321",
            "password=super_secret_master_admin_password",
            "SELECT * FROM users WHERE is_superuser=TRUE",
            "Traceback (most recent call last):\n  File 'manage.py', line 12",
            "django.db.utils.DatabaseError: Connection pool timed out",
        ]

        for payload in sensitive_payloads:
            exc = RuntimeError(f"Simulated failure containing: {payload}")
            request = self.factory.get('/api/data/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            response = self.middleware.process_exception(request, exc)

            self.assertEqual(response.status_code, 500)
            body = response.content.decode('utf-8')
            self.assertNotIn(payload, body, f"Sensitive payload '{payload}' leaked in JSON response!")
            self.assertNotIn("Simulated failure", body)
            self.assertIn("Internal Server Error", body)

    @override_settings(DEBUG=False)
    def test_sensitive_tokens_matrix_html_500(self):
        sensitive_payloads = [
            "/app/aetherspace/secrets.py",
            "SECRET_KEY=super_confidential_production_key_44321",
            "password=super_secret_master_admin_password",
            "SELECT * FROM users WHERE is_superuser=TRUE",
            "Traceback (most recent call last):\n  File 'manage.py', line 12",
            "django.db.utils.DatabaseError: Connection pool timed out",
        ]

        for payload in sensitive_payloads:
            exc = RuntimeError(f"Simulated failure containing: {payload}")
            request = self.factory.get('/web-page/')
            request.user = self.user
            response = self.middleware.process_exception(request, exc)

            self.assertEqual(response.status_code, 500)
            body = response.content.decode('utf-8')
            self.assertNotIn(payload, body, f"Sensitive payload '{payload}' leaked in HTML response!")
            self.assertNotIn("Simulated failure", body)
            self.assertIn("ERR-500-", body)

    def test_error_403_does_not_render_traceback_or_sql(self):
        request = self.factory.get('/workspaces/secret-ws/')
        request.user = User(email="test@user.dev")

        dirty_exception = Exception("Traceback (most recent call last):\nFile 'foo.py'\nSELECT * FROM sensitive_table")
        response = error_403(request, exception=dirty_exception)

        self.assertEqual(response.status_code, 403)
        body = response.content.decode('utf-8')
        self.assertNotIn("Traceback", body)
        self.assertNotIn("SELECT * FROM", body)
        self.assertIn("Access Restricted", body)


class Batch6DefenseInDepthSanitizationTests(TestCase):
    """
    Validates defense-in-depth sanitization across tasks, bugs, and admin panel.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="defense.tester@aetherspace.dev",
            password="TestPassword123!",
            role="ADMIN"
        )
        self.workspace = Workspace.objects.create(
            name="Defense Test WS",
            slug="defense-test-ws",
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        self.client.login(email=self.user.email, password="TestPassword123!")

    def test_admin_backup_restore_corrupt_payload_sanitization(self):
        """
        Verify corrupt base64 payload returns generic message and does not leak decode exception.
        """
        response = self.client.post(
            reverse('admin_panel:confirm_backup_restore'),
            data={
                'payload_b64': '!!!INVALID_BASE64_WITH_ILLEGAL_CHARS!!!',
                'target_workspace_slug': self.workspace.slug,
            },
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode('utf-8')
        self.assertIn("Corrupt backup payload data. Unable to decode backup file.", content)
        self.assertNotIn("binascii.Error", content)
        self.assertNotIn("Incorrect padding", content)
