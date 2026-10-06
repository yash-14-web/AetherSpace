"""
Batch 9: CodeQL Final Two URL-Redirection Remediation Tests.
Validates that safe_redirect and redirect_to_login_with_next strictly enforce
redirection barriers, prevent untrusted user-controlled redirects (CWE-601 / py/url-redirection),
and correctly fall back to safe internal destinations.
"""

from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from core.utils import safe_redirect, safe_redirect_target, redirect_to_login_with_next


@override_settings(ALLOWED_HOSTS=['testserver', 'app.aetherspace.dev'])
class Batch9CodeQLUrlRedirectionSecurityTests(TestCase):
    """
    Test suite for the final two CodeQL url-redirection findings (#54, #55).
    Verifies the 20 required security test cases.
    """

    def setUp(self):
        self.rf = RequestFactory()
        self.request = self.rf.get('/dashboard/', HTTP_HOST='testserver')
        self.request_custom = self.rf.get('/tasks/', HTTP_HOST='app.aetherspace.dev')
        self.login_url = reverse('accounts:login')

    # -------------------------------------------------------------------------
    # safe_redirect tests (Tests 1 - 14)
    # -------------------------------------------------------------------------

    def test_01_safe_internal_redirect(self):
        """1. safe internal redirect."""
        for path in ['/', '/dashboard/', '/workspaces/', '/workspaces/aetherspace-core/', '/tasks/', '/bugs/', '/calendar/', '/chat/']:
            resp = safe_redirect(self.request, path, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, path)

    def test_02_safe_same_host_redirect(self):
        """2. safe same-host redirect."""
        resp1 = safe_redirect(self.request, 'http://testserver/dashboard/', fallback='/fallback/')
        self.assertEqual(resp1.status_code, 302)
        self.assertEqual(resp1.url, 'http://testserver/dashboard/')

        resp2 = safe_redirect(self.request_custom, 'http://app.aetherspace.dev/tasks/619347/', fallback='/fallback/')
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(resp2.url, 'http://app.aetherspace.dev/tasks/619347/')

    def test_03_external_https_rejection(self):
        """3. external HTTPS rejection."""
        targets = [
            'https://evil.example',
            'https://evil.example/login',
            'https://attacker.com/steal-creds?next=/dashboard/',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('evil.example', resp.url)
            self.assertNotIn('attacker.com', resp.url)

    def test_04_external_http_rejection(self):
        """4. external HTTP rejection."""
        targets = [
            'http://evil.example',
            'http://evil.example/aetherspace',
            'http://attacker.com/phish',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('evil.example', resp.url)

    def test_05_protocol_relative_rejection(self):
        """5. protocol-relative rejection."""
        targets = [
            '//evil.example',
            '//evil.example/path',
            '//attacker.com',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('evil.example', resp.url)

    def test_06_triple_slash_rejection(self):
        """6. triple-slash rejection."""
        targets = [
            '///evil.example',
            '///attacker.com/payload',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('evil.example', resp.url)

    def test_07_backslash_rejection(self):
        """7. backslash rejection."""
        targets = [
            r'\evil.example',
            r'/\evil.example',
            r'\\evil.example',
            r'/\\evil.example',
            r'https:\evil.example',
            r'/dashboard/\evil.example',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('evil.example', resp.url)

    def test_08_encoded_backslash_rejection(self):
        """8. encoded backslash rejection."""
        targets = [
            '/%5cevil.example',
            '%5c%5cevil.example',
            '/%255cevil.example',
            '%2f%2fevil.example',
            '/%5Cevil.example',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('evil.example', resp.url)

    def test_09_javascript_rejection(self):
        """9. javascript rejection."""
        targets = [
            'javascript:alert(1)',
            'javascript:alert(document.cookie)',
            'JAVASCRIPT:void(0)',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('javascript', resp.url.lower())

    def test_10_data_rejection(self):
        """10. data rejection."""
        targets = [
            'data:text/html,<script>alert(1)</script>',
            'data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('data:', resp.url.lower())

    def test_11_vbscript_rejection(self):
        """11. vbscript rejection."""
        targets = [
            'vbscript:msgbox(1)',
            'VBSCRIPT:alert',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('vbscript:', resp.url.lower())

    def test_12_malformed_scheme_rejection(self):
        """12. malformed scheme rejection."""
        targets = [
            'https:/evil.example',
            'https:///evil.example',
            'http:/evil.example/test',
            'file:///etc/passwd',
            'htp://evil.example',
        ]
        for target in targets:
            resp = safe_redirect(self.request, target, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')
            self.assertNotIn('evil.example', resp.url)

    def test_13_empty_target_fallback(self):
        """13. empty target fallback."""
        for empty_val in ['', '   ', '\t', '\n']:
            resp = safe_redirect(self.request, empty_val, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, '/fallback/')

        # Default fallback when none specified is '/'
        resp_default = safe_redirect(self.request, '')
        self.assertEqual(resp_default.status_code, 302)
        self.assertEqual(resp_default.url, '/')

    def test_14_none_target_fallback(self):
        """14. None target fallback."""
        resp = safe_redirect(self.request, None, fallback='/fallback/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/fallback/')

        resp_default = safe_redirect(self.request, None)
        self.assertEqual(resp_default.status_code, 302)
        self.assertEqual(resp_default.url, '/')

    # -------------------------------------------------------------------------
    # redirect_to_login_with_next tests (Tests 15 - 20)
    # -------------------------------------------------------------------------

    def test_15_normal_authenticated_safe_path_becomes_valid_next(self):
        """15. normal authenticated-safe path becomes valid next."""
        safe_paths = [
            '/dashboard/',
            '/workspaces/core-team/',
            '/tasks/619347/',
            '/bugs/B-882316/',
            '/calendar/',
            '/chat/',
        ]
        for path in safe_paths:
            req = self.rf.get(path, HTTP_HOST='testserver')
            resp = redirect_to_login_with_next(req)
            self.assertEqual(resp.status_code, 302)
            expected_target = f"{self.login_url}?next={path}"
            self.assertEqual(resp.url, expected_target)

    def test_16_external_request_path_cannot_become_external_next(self):
        """16. external request.path cannot become external next."""
        external_paths = [
            'https://evil.example',
            'http://attacker.com/phish',
            '//evil.example',
        ]
        for evil_path in external_paths:
            req = self.rf.get('/test/', HTTP_HOST='testserver')
            req.path = evil_path
            resp = redirect_to_login_with_next(req)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, self.login_url)
            self.assertNotIn('evil.example', resp.url)
            self.assertNotIn('attacker.com', resp.url)

    def test_17_protocol_relative_path_rejected(self):
        """17. protocol-relative path rejected."""
        proto_rel_paths = [
            '//evil.example',
            '//attacker.com/leak',
            '///triple.slash',
        ]
        for pr_path in proto_rel_paths:
            req = self.rf.get('/test/', HTTP_HOST='testserver')
            req.path = pr_path
            resp = redirect_to_login_with_next(req)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, self.login_url)
            self.assertNotIn('evil.example', resp.url)
            self.assertNotIn('attacker.com', resp.url)

    def test_18_backslash_path_rejected(self):
        """18. backslash path rejected."""
        backslash_paths = [
            r'/\evil.example',
            r'/\\evil.example',
            r'\evil.example',
            r'/dashboard\evil.example',
            '/%5cevil.example',
        ]
        for bs_path in backslash_paths:
            req = self.rf.get('/test/', HTTP_HOST='testserver')
            req.path = bs_path
            resp = redirect_to_login_with_next(req)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, self.login_url)
            self.assertNotIn('evil.example', resp.url)

    def test_19_login_url_remains_valid(self):
        """19. login URL remains valid."""
        req = self.rf.get('/workspaces/', HTTP_HOST='testserver')
        resp = redirect_to_login_with_next(req)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith(self.login_url))

    def test_20_fallback_login_redirect_works(self):
        """20. fallback login redirect works when path is empty or request is None."""
        # None request
        resp_none = redirect_to_login_with_next(None)
        self.assertEqual(resp_none.status_code, 302)
        self.assertEqual(resp_none.url, self.login_url)

        # Empty path
        req_empty = self.rf.get('', HTTP_HOST='testserver')
        req_empty.path = ''
        resp_empty = redirect_to_login_with_next(req_empty)
        self.assertEqual(resp_empty.status_code, 302)
        self.assertEqual(resp_empty.url, self.login_url)

        # Whitespace-only path
        req_ws = self.rf.get('/   ', HTTP_HOST='testserver')
        req_ws.path = '   '
        resp_ws = redirect_to_login_with_next(req_ws)
        self.assertEqual(resp_ws.status_code, 302)
        self.assertEqual(resp_ws.url, self.login_url)
