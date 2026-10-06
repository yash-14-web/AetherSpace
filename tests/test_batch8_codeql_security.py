"""
Batch 8: Remote CodeQL Remediation Security Tests.
Validates the complete remediation of the 12 remote CodeQL findings:
- Finding #38 (HIGH): py/polynomial-redos in rich_text.py
- Finding #53 (Medium): py/url-redirection in core/utils.py
- Finding #16 (Medium): py/url-redirection in workspaces/views.py:761
- Finding #8  (Medium): py/url-redirection in workspaces/permissions.py:100
- Finding #7  (Medium): py/url-redirection in workspaces/permissions.py:76
- Finding #6  (Medium): py/url-redirection in workspaces/permissions.py:50
- Finding #5  (Medium): py/url-redirection in admin_panel/permissions.py:29
- Finding #50 (Medium): py/stack-trace-exposure in chat/views.py:459
- Finding #51 (Medium): py/stack-trace-exposure in chat/views.py:484
- Finding #52 (Medium): py/stack-trace-exposure in chat/views.py:667
- Finding #4  (Medium): py/stack-trace-exposure in chat/views.py:669
- Finding #3  (Medium): py/stack-trace-exposure in chat/views.py:625
"""

import json
import logging
import time
from unittest.mock import patch

from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse

from core.templatetags.rich_text import (
    render_rich_text,
    normalize_standalone_task_brackets,
    transform_mentions,
)
from core.utils import (
    safe_redirect,
    safe_redirect_target,
    redirect_to_login_with_next,
)
from workspaces.models import (
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
    MembershipStatus,
    WorkspaceInvitation,
)
from workspaces.permissions import (
    workspace_member_required,
    workspace_admin_required,
    workspace_manager_required,
)
from admin_panel.permissions import platform_admin_required
from chat.models import Channel, ChannelMembership, Message

User = get_user_model()


class Batch8ReDoSZeroPolynomialComplexityTests(TestCase):
    """
    Finding #38: py/polynomial-redos in core/templatetags/rich_text.py
    Validates deterministic linear O(N) performance on large, adversarial,
    and malformed inputs with 20,000+ characters.
    """

    def test_task_bracket_linear_complexity_adversarial_repeats(self):
        """Verify 20k+ character payloads process in linear time without backtracking."""
        adversarial_payloads = [
            "[ ] " * 5000,                                 # 20,000 chars repeated valid-like brackets
            "   [x]   " * 3000,                            # 27,000 chars spaces and brackets
            "[" * 25000,                                   # 25,000 unclosed brackets
            "[ ]" + (" " * 25000) + "trailing",            # Long line with massive whitespace
            "\n".join(["   [ ] Task item number " + str(i) for i in range(1500)]),  # 1500 lines
            "\n".join(["[ ]   \t  " * 10 for _ in range(500)]),
        ]

        for idx, payload in enumerate(adversarial_payloads):
            start = time.perf_counter()
            result = normalize_standalone_task_brackets(payload)
            elapsed = time.perf_counter() - start
            # Must process within 250ms (linear execution on O(N) string ops takes < 15ms)
            self.assertLess(
                elapsed,
                0.25,
                f"Adversarial payload #{idx} (len {len(payload)}) exceeded linear time bound: took {elapsed:.4f}s"
            )
            self.assertIsInstance(result, str)

    def test_rich_text_pipeline_with_adversarial_input(self):
        """Full render_rich_text pipeline completes rapidly on 20k+ character input."""
        lines = []
        for i in range(300):
            lines.extend([
                "### Section " + str(i),
                "[ ] Checkbox item " + str(i),
                "[x] Completed item " + str(i),
                "Some text with [brackets] and @marcus_aether"
            ])
        large_markdown = "\n".join(lines)  # ~25,000 chars

        start = time.perf_counter()
        html = render_rich_text(large_markdown)
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 1.0, f"Full markdown pipeline took too long: {elapsed:.4f}s")
        self.assertIn('class="task-list-item', html)
        self.assertIn('type="checkbox"', html)

    def test_task_bracket_normalization_behavior(self):
        """Verifies exact functional correctness of normalize_standalone_task_brackets."""
        # Unchecked
        self.assertEqual(normalize_standalone_task_brackets("[ ] Todo"), "- [ ] Todo")
        self.assertEqual(normalize_standalone_task_brackets("  [ ] Indented"), "- [ ] Indented")

        # Checked (lower and upper)
        self.assertEqual(normalize_standalone_task_brackets("[x] Done"), "- [x] Done")
        self.assertEqual(normalize_standalone_task_brackets("[X] Done cap"), "- [X] Done cap")

        # Already a list item - should NOT double hyphen
        self.assertEqual(normalize_standalone_task_brackets("- [ ] Already list"), "- [ ] Already list")
        self.assertEqual(normalize_standalone_task_brackets("* [ ] Star list"), "* [ ] Star list")

        # Malformed - must not crash or transform incorrectly
        self.assertEqual(normalize_standalone_task_brackets("[] Not task"), "[] Not task")
        self.assertEqual(normalize_standalone_task_brackets("[ ]", ), "[ ]")
        self.assertEqual(normalize_standalone_task_brackets("[abc] regular bracket"), "[abc] regular bracket")

    def test_unicode_and_mention_syntax_preservation(self):
        """Verify mentions, punctuation, and Unicode characters are preserved correctly."""
        text = "Hello @marcus_aether and @renée! [ ] Review PR for #619347"
        normalized = normalize_standalone_task_brackets(text)
        self.assertIn("@marcus_aether", normalized)
        self.assertIn("@renée", normalized)
        self.assertIn("#619347", normalized)

        # HTML rendering
        rendered = render_rich_text(text)
        self.assertIn("marcus_aether", rendered)
        self.assertIn("renée", rendered)


@override_settings(ALLOWED_HOSTS=['testserver', 'app.aetherspace.dev', 'localhost', '127.0.0.1'])
class Batch8SafeRedirectCodeQLBarrierTests(TestCase):
    """
    Finding #53: py/url-redirection in core/utils.py:92
    Validates safe_redirect, safe_redirect_target, and redirect_to_login_with_next.
    """

    def setUp(self):
        self.rf = RequestFactory()
        self.request = self.rf.get('/test/', HTTP_HOST='testserver')
        self.login_url = reverse('accounts:login')

    def test_safe_redirect_allowed_internal_paths(self):
        for path in ['/', '/dashboard/', '/workspaces/', '/chat/w/alpha/']:
            resp = safe_redirect(self.request, path, fallback='/')
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp.url, path)

    def test_safe_redirect_same_host_url(self):
        resp = safe_redirect(self.request, 'http://testserver/dashboard/', fallback='/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, 'http://testserver/dashboard/')

    def test_safe_redirect_malicious_external_rejected(self):
        malicious = [
            'https://evil.example',
            'http://evil.example/login',
            '//evil.example',
            '///evil.example',
            r'/\\evil.example',
            r'\\evil.example',
            'javascript:alert(1)',
            'data:text/html,<script>alert(1)</script>',
            'vbscript:msgbox',
            'https:/evil.example',
            'https:///evil.example',
            'http://attacker.com?next=/dashboard/',
        ]
        for url in malicious:
            resp = safe_redirect(self.request, url, fallback='/fallback/')
            self.assertEqual(resp.status_code, 302)
            self.assertNotIn('evil.example', resp.url)
            self.assertNotIn('attacker.com', resp.url)
            self.assertNotIn('javascript', resp.url)
            self.assertEqual(resp.url, '/fallback/')

    def test_safe_redirect_empty_or_none(self):
        resp1 = safe_redirect(self.request, '', fallback='/fallback/')
        self.assertEqual(resp1.url, '/fallback/')
        resp2 = safe_redirect(self.request, None, fallback='/fallback/')
        self.assertEqual(resp2.url, '/fallback/')

    def test_redirect_to_login_with_next_sanitization(self):
        """redirect_to_login_with_next must sanitize request.path and guard redirect."""
        # Safe internal path
        req_safe = self.rf.get('/workspaces/test-ws/settings/', HTTP_HOST='testserver')
        resp = redirect_to_login_with_next(req_safe)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'{self.login_url}?next=/workspaces/test-ws/settings/', resp.url)

        # Malicious protocol-relative path
        req_evil = self.rf.get('/test/', HTTP_HOST='testserver')
        req_evil.path = '//evil.example'
        resp_evil = redirect_to_login_with_next(req_evil)
        self.assertEqual(resp_evil.status_code, 302)
        self.assertNotIn('evil.example', resp_evil.url)
        self.assertEqual(resp_evil.url, self.login_url)

        # Malicious backslash path
        req_evil2 = self.rf.get('/test/', HTTP_HOST='testserver')
        req_evil2.path = r'/\\evil.example'
        resp_evil2 = redirect_to_login_with_next(req_evil2)
        self.assertEqual(resp_evil2.status_code, 302)
        self.assertNotIn('evil.example', resp_evil2.url)
        self.assertEqual(resp_evil2.url, self.login_url)


@override_settings(ALLOWED_HOSTS=['testserver', 'app.aetherspace.dev'])
class Batch8PermissionRedirectTests(TestCase):
    """
    Findings #5, #6, #7, #8, #16: py/url-redirection in permission decorators
    and invitation acceptance view.
    """

    def setUp(self):
        self.rf = RequestFactory()
        self.user = User.objects.create_user(
            email="perm.tester@aetherspace.dev",
            password="TestPassword123!",
            role="CONTRIBUTOR"
        )
        self.workspace = Workspace.objects.create(
            name="Perm Test WS",
            slug="perm-test-ws",
            owner=self.user
        )
        self.login_url = reverse('accounts:login')

    def test_workspace_member_required_unauthenticated_redirect(self):
        """Finding #6: workspaces/permissions.py:50"""
        @workspace_member_required
        def dummy_view(request, slug):
            return HttpResponse("OK")

        req = self.rf.get(f'/workspaces/{self.workspace.slug}/', HTTP_HOST='testserver')
        req.user = AnonymousUser()
        resp = dummy_view(req, slug=self.workspace.slug)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"{self.login_url}?next=/workspaces/{self.workspace.slug}/", resp.url)

    def test_workspace_admin_required_unauthenticated_redirect(self):
        """Finding #7: workspaces/permissions.py:76"""
        @workspace_admin_required
        def dummy_admin_view(request, slug):
            return HttpResponse("OK")

        req = self.rf.get(f'/workspaces/{self.workspace.slug}/admin/', HTTP_HOST='testserver')
        req.user = AnonymousUser()
        resp = dummy_admin_view(req, slug=self.workspace.slug)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"{self.login_url}?next=/workspaces/{self.workspace.slug}/admin/", resp.url)

    def test_workspace_manager_required_unauthenticated_redirect(self):
        """Finding #8: workspaces/permissions.py:100"""
        @workspace_manager_required
        def dummy_mgr_view(request, slug):
            return HttpResponse("OK")

        req = self.rf.get(f'/workspaces/{self.workspace.slug}/manager/', HTTP_HOST='testserver')
        req.user = AnonymousUser()
        resp = dummy_mgr_view(req, slug=self.workspace.slug)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"{self.login_url}?next=/workspaces/{self.workspace.slug}/manager/", resp.url)

    def test_platform_admin_required_unauthenticated_redirect(self):
        """Finding #5: admin_panel/permissions.py:29"""
        @platform_admin_required
        def dummy_platform_view(request):
            return HttpResponse("OK")

        req = self.rf.get('/admin-console/settings/', HTTP_HOST='testserver')
        req.user = AnonymousUser()
        resp = dummy_platform_view(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"{self.login_url}?next=/admin-console/settings/", resp.url)

    def test_accept_invite_unauthenticated_post_redirect(self):
        """Finding #16: workspaces/views.py:761"""
        invite = WorkspaceInvitation.objects.create(
            workspace=self.workspace,
            email="invited.person@aetherspace.dev",
            role=WorkspaceRole.CONTRIBUTOR,
            invited_by=self.user,
        )
        url = reverse('workspaces:accept_invitation', kwargs={'token': invite.token})

        # POST without authentication
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"{self.login_url}?next={url}", resp.url)


class Batch8ChatExceptionDisclosureTests(TestCase):
    """
    Findings #50, #51, #52, #4, #3: py/stack-trace-exposure in chat/views.py
    Validates that endpoints return generic, safe messages without leaking
    raw exception strings, tracebacks, database/SQL errors, or file paths.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="chat.sec.user@aetherspace.dev",
            password="TestPassword123!",
            role="CONTRIBUTOR"
        )
        self.workspace = Workspace.objects.create(
            name="Chat Sec WS",
            slug="chat-sec-ws",
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        self.channel = Channel.objects.create(
            workspace=self.workspace,
            name="sec-channel",
            slug="sec-channel",
            created_by=self.user
        )
        ChannelMembership.objects.create(
            channel=self.channel,
            user=self.user,
            role='OWNER'
        )
        self.message = Message.objects.create(
            workspace=self.workspace,
            channel=self.channel,
            sender=self.user,
            content="Sensitive security test message"
        )
        self.client.login(email=self.user.email, password="TestPassword123!")

    def test_channel_add_member_exception_disclosure_prevented(self):
        """Finding #50: chat/views.py:459"""
        sensitive_internal = "psycopg2.OperationalError: table users_channel corrupted at /app/chat/models.py"

        with patch('chat.views.add_channel_member', side_effect=ValidationError(sensitive_internal)):
            with self.assertLogs('chat.views', level='WARNING') as cm:
                url = reverse('chat:channel_add_members', kwargs={
                    'slug': self.workspace.slug,
                    'channel_slug': self.channel.slug
                })
                resp = self.client.post(
                    url,
                    data={'user_id': self.user.id},
                    HTTP_X_REQUESTED_WITH='XMLHttpRequest'
                )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        # Must NOT leak sensitive internal error string
        raw = resp.content.decode('utf-8')
        self.assertNotIn(sensitive_internal, raw)
        self.assertNotIn("psycopg2", raw)
        self.assertNotIn("/app/chat", raw)
        # Must contain generic safe error
        self.assertIn("Unable to add specified member to channel.", data['errors'])
        # Must log server-side
        self.assertTrue(any("Failed to add member" in log for log in cm.output))

    def test_channel_remove_member_exception_disclosure_prevented(self):
        """Finding #51: chat/views.py:484"""
        sensitive_internal = "PermissionDenied: User lacks RBAC matrix row 42 in /app/rbac/engine.py"

        with patch('chat.views.remove_channel_member', side_effect=PermissionDenied(sensitive_internal)):
            with self.assertLogs('chat.views', level='WARNING') as cm:
                url = reverse('chat:channel_remove_member', kwargs={
                    'slug': self.workspace.slug,
                    'channel_slug': self.channel.slug,
                    'user_id': self.user.id
                })
                resp = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], "Unable to remove member from channel.")
        # Must NOT leak exception internals
        raw = resp.content.decode('utf-8')
        self.assertNotIn(sensitive_internal, raw)
        self.assertNotIn("/app/rbac", raw)
        # Must log server-side
        self.assertTrue(any("Failed to remove member" in log for log in cm.output))

    def test_api_toggle_pin_exception_disclosure_prevented(self):
        """Finding #3: chat/views.py:625"""
        sensitive_internal = "PermissionDenied: SELECT * FROM secrets_tbl WHERE id=123;"

        with patch('chat.views.toggle_pin_message', side_effect=PermissionDenied(sensitive_internal)):
            with self.assertLogs('chat.views', level='WARNING') as cm:
                url = reverse('chat:api_toggle_pin', kwargs={
                    'slug': self.workspace.slug,
                    'message_id': self.message.id
                })
                resp = self.client.post(url)

        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], "You do not have permission to pin messages.")
        # Must NOT leak internal SQL or exception
        raw = resp.content.decode('utf-8')
        self.assertNotIn(sensitive_internal, raw)
        self.assertNotIn("SELECT *", raw)
        # Server-side logging occurred
        self.assertTrue(any("Permission denied toggling pin" in log for log in cm.output))

    def test_api_toggle_reaction_validation_exception_disclosure_prevented(self):
        """Finding #52: chat/views.py:667"""
        sensitive_internal = "ValidationError: Field regex failed at /app/chat/validation.py line 89"

        with patch('chat.views.toggle_reaction', side_effect=ValidationError(sensitive_internal)):
            with self.assertLogs('chat.views', level='WARNING') as cm:
                url = reverse('chat:api_toggle_reaction', kwargs={
                    'slug': self.workspace.slug,
                    'message_id': self.message.id
                })
                resp = self.client.post(url, {'emoji': '🚀'})

        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], "Invalid reaction emoji or request format.")
        # Must NOT leak exception internals
        raw = resp.content.decode('utf-8')
        self.assertNotIn(sensitive_internal, raw)
        self.assertNotIn("/app/chat/validation.py", raw)
        # Server-side logging occurred
        self.assertTrue(any("Validation error toggling reaction" in log for log in cm.output))

    def test_api_toggle_reaction_permission_exception_disclosure_prevented(self):
        """Finding #4: chat/views.py:669"""
        sensitive_internal = "PermissionDenied: User muted on channel internal_id_8899"

        with patch('chat.views.toggle_reaction', side_effect=PermissionDenied(sensitive_internal)):
            with self.assertLogs('chat.views', level='WARNING') as cm:
                url = reverse('chat:api_toggle_reaction', kwargs={
                    'slug': self.workspace.slug,
                    'message_id': self.message.id
                })
                resp = self.client.post(url, {'emoji': '👍'})

        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], "You do not have permission to react to this message.")
        # Must NOT leak exception details
        raw = resp.content.decode('utf-8')
        self.assertNotIn(sensitive_internal, raw)
        self.assertNotIn("internal_id_8899", raw)
        # Server-side logging occurred
        self.assertTrue(any("Permission denied toggling reaction" in log for log in cm.output))
