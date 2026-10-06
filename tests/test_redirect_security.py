"""
Batch 4: Open Redirect / Untrusted URL Redirection Hardening Tests.
Validates centralized URL safety helper and protects all application redirect flows.
"""

from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.utils import safe_redirect_target, safe_redirect
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from tasks.models import Task, TaskStatus, TaskPriority
from chat.models import Channel, ChannelMembership, ChannelRole
from files.models import StoredFile, Folder
from notifications.models import Notification, NotificationCategory, NotificationType

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver', 'app.aetherspace.dev', 'localhost', '127.0.0.1'])
class Batch4SafeRedirectHelperUnitTests(TestCase):
    """
    Unit tests for core.utils.safe_redirect_target against the complete security matrix.
    """
    def setUp(self):
        self.rf = RequestFactory()
        self.req_http = self.rf.get('/test/', HTTP_HOST='testserver')
        self.req_custom_host = self.rf.get('/test/', HTTP_HOST='app.aetherspace.dev')

    def test_safe_internal_paths(self):
        safe_paths = [
            '/',
            '/dashboard/',
            '/workspaces/',
            '/chat/',
            '/tasks/',
            '/bugs/',
            '/notifications/',
        ]
        for path in safe_paths:
            self.assertEqual(
                safe_redirect_target(self.req_http, path, fallback='/fallback/'),
                path,
                f"Failed to allow safe internal path: {path}"
            )

    def test_safe_relative_query_strings(self):
        paths = [
            '/dashboard/?tab=active',
            '/tasks/w/alpha/619347/?tab=comments&filter=all',
            '/files/w/beta/?sort=desc#preview',
        ]
        for path in paths:
            self.assertEqual(
                safe_redirect_target(self.req_http, path, fallback='/fallback/'),
                path
            )

    def test_safe_absolute_url_matching_request_host(self):
        self.assertEqual(
            safe_redirect_target(self.req_http, 'http://testserver/dashboard/', fallback='/fallback/'),
            'http://testserver/dashboard/'
        )
        self.assertEqual(
            safe_redirect_target(self.req_custom_host, 'http://app.aetherspace.dev/tasks/', fallback='/fallback/'),
            'http://app.aetherspace.dev/tasks/'
        )

    def test_malicious_external_hosts_rejected(self):
        malicious = [
            'https://evil.example',
            'https://evil.example/login',
            'http://evil.example',
            'http://evil.example/aetherspace',
            'https://attacker.com/steal-creds?next=/dashboard/',
        ]
        for target in malicious:
            self.assertEqual(
                safe_redirect_target(self.req_http, target, fallback='/fallback/'),
                '/fallback/',
                f"Failed to reject external destination: {target}"
            )

    def test_protocol_relative_urls_rejected(self):
        protocol_relative = [
            '//evil.example',
            '//evil.example/login',
            '//attacker.com',
            '///evil.example',
        ]
        for target in protocol_relative:
            self.assertEqual(
                safe_redirect_target(self.req_http, target, fallback='/fallback/'),
                '/fallback/',
                f"Failed to reject protocol-relative target: {target}"
            )

    def test_backslash_variations_rejected(self):
        backslash_targets = [
            r'https:\evil.example',
            r'https:\\evil.example',
            r'//evil.example\foo',
            r'/\evil.example',
            r'\\evil.example',
            r'/\\evil.example',
            r'\\evil.example\login',
            '/dashboard/\\evil.example',
        ]
        for target in backslash_targets:
            self.assertEqual(
                safe_redirect_target(self.req_http, target, fallback='/fallback/'),
                '/fallback/',
                f"Failed to reject backslash target: {target}"
            )

    def test_malformed_schemes_rejected(self):
        malformed = [
            'https:/evil.example',
            'https:///evil.example',
            'http:/evil.example/test',
            'htp://evil.example',
        ]
        for target in malformed:
            self.assertEqual(
                safe_redirect_target(self.req_http, target, fallback='/fallback/'),
                '/fallback/',
                f"Failed to reject malformed scheme target: {target}"
            )

    def test_dangerous_schemes_rejected(self):
        dangerous = [
            'javascript:alert(1)',
            'javascript:alert(document.cookie)',
            'data:text/html,<script>alert(1)</script>',
            'data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==',
            'vbscript:msgbox(1)',
            'file:///etc/passwd',
            'file:///c:/windows/system32/cmd.exe',
        ]
        for target in dangerous:
            self.assertEqual(
                safe_redirect_target(self.req_http, target, fallback='/fallback/'),
                '/fallback/',
                f"Failed to reject dangerous scheme target: {target}"
            )

    def test_empty_whitespace_and_none(self):
        self.assertEqual(safe_redirect_target(self.req_http, '', fallback='/fallback/'), '/fallback/')
        self.assertEqual(safe_redirect_target(self.req_http, '   ', fallback='/fallback/'), '/fallback/')
        self.assertEqual(safe_redirect_target(self.req_http, None, fallback='/fallback/'), '/fallback/')
        # Valid path with leading/trailing whitespace should be trimmed and accepted
        self.assertEqual(safe_redirect_target(self.req_http, '  /dashboard/  ', fallback='/fallback/'), '/dashboard/')
        # Malicious external with leading whitespace must be rejected
        self.assertEqual(safe_redirect_target(self.req_http, '  https://evil.example  ', fallback='/fallback/'), '/fallback/')

    def test_obfuscated_and_encoded_variants_rejected(self):
        obfuscated = [
            '%2f%2fevil.example',
            '/%5cevil.example',
            '%5c%5cevil.example',
            '%2f%255cevil.example',
        ]
        for target in obfuscated:
            self.assertEqual(
                safe_redirect_target(self.req_http, target, fallback='/fallback/'),
                '/fallback/',
                f"Failed to reject obfuscated target: {target}"
            )

    def test_crlf_header_injection_rejected(self):
        crlf = '/dashboard/\r\nLocation: https://evil.example'
        self.assertEqual(
            safe_redirect_target(self.req_http, crlf, fallback='/fallback/'),
            '/fallback/'
        )

    def test_dynamic_host_authority_validation(self):
        # http://evil.example should be rejected regardless of current host
        self.assertEqual(
            safe_redirect_target(self.req_http, 'http://evil.example/dashboard/', fallback='/fallback/'),
            '/fallback/'
        )
        # Target matching a different host than request should be rejected
        self.assertEqual(
            safe_redirect_target(self.req_http, 'http://app.aetherspace.dev/dashboard/', fallback='/fallback/'),
            '/fallback/'
        )
        # Target matching the specific request host must succeed
        self.assertEqual(
            safe_redirect_target(self.req_custom_host, 'http://app.aetherspace.dev/dashboard/', fallback='/fallback/'),
            'http://app.aetherspace.dev/dashboard/'
        )


class Batch4ViewRedirectHardeningIntegrationTests(TestCase):
    """
    Integration tests verifying hardened redirects across accounts, tasks, chat, files,
    notifications, and workspaces views.
    """
    def setUp(self):
        self.client = Client()
        self.password = "SecurePass123!"
        self.user = User.objects.create_user(
            email="redirect.tester@aetherspace.dev",
            password=self.password,
            full_name="Redirect Tester",
            contributor_id="11111A",
            is_active=True
        )
        # Ensure user is approved
        if hasattr(self.user, 'approval_status'):
            from accounts.models import ApprovalStatus
            self.user.approval_status = ApprovalStatus.APPROVED
            self.user.save(update_fields=['approval_status'])

        self.workspace = Workspace.objects.create(
            name="Sec Workspace",
            slug="sec-ws",
            owner=self.user
        )
        self.membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    # 1. Accounts Login Redirect
    def test_login_redirect_safe_internal(self):
        url = reverse('accounts:login') + '?next=/workspaces/'
        resp = self.client.post(url, {
            'contributor_id': self.user.contributor_id,
            'password': self.password,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/workspaces/')

    def test_login_redirect_malicious_external_falls_back_to_dashboard(self):
        malicious_urls = [
            'https://evil.example',
            '//evil.example/login',
            r'https:\evil.example',
            'javascript:alert(1)',
        ]
        for m in malicious_urls:
            url = reverse('accounts:login') + f'?next={m}'
            resp = self.client.post(url, {
                'contributor_id': self.user.contributor_id,
                'password': self.password,
            })
            self.assertEqual(resp.status_code, 302)
            self.assertNotEqual(resp.url, m)
            self.assertIn('/workspaces/dashboard/', resp.url)

    # 2. Tasks Status Update Redirect
    def test_task_status_update_safe_next(self):
        self.client.force_login(self.user)
        task = Task.objects.create(
            workspace=self.workspace,
            task_code="777777",
            title="Redirect Test Task",
            reporter=self.user,
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM
        )
        url = reverse('tasks:task_status_update', kwargs={'slug': self.workspace.slug, 'task_code': task.task_code})
        safe_dest = f"/tasks/w/{self.workspace.slug}/board/"
        resp = self.client.post(url, {
            'status': TaskStatus.IN_PROGRESS,
            'next': safe_dest
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, safe_dest)

    def test_task_status_update_malicious_next_falls_back_to_detail(self):
        self.client.force_login(self.user)
        task = Task.objects.create(
            workspace=self.workspace,
            task_code="777778",
            title="Redirect Test Task 2",
            reporter=self.user,
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM
        )
        url = reverse('tasks:task_status_update', kwargs={'slug': self.workspace.slug, 'task_code': task.task_code})
        resp = self.client.post(url, {
            'status': TaskStatus.DONE,
            'next': 'https://evil.example/phish'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.example', resp.url)
        self.assertIn(f"/tasks/w/{self.workspace.slug}/{task.task_code}/", resp.url)

    # 3. Chat Referer Redirect
    def test_chat_member_add_safe_referer(self):
        self.client.force_login(self.user)
        channel = Channel.objects.create(
            workspace=self.workspace,
            name="sec-channel",
            slug="sec-channel",
            created_by=self.user
        )
        ChannelMembership.objects.create(
            channel=channel,
            user=self.user,
            role=ChannelRole.ADMIN
        )
        url = reverse('chat:channel_add_members', kwargs={'slug': self.workspace.slug, 'channel_slug': channel.slug})
        safe_ref = f"/chat/w/{self.workspace.slug}/c/{channel.slug}/"
        resp = self.client.post(url, {}, HTTP_REFERER=f"http://testserver{safe_ref}")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(safe_ref, resp.url)

    def test_chat_member_add_malicious_referer_rejected(self):
        self.client.force_login(self.user)
        channel = Channel.objects.create(
            workspace=self.workspace,
            name="sec-channel-2",
            slug="sec-channel-2",
            created_by=self.user
        )
        ChannelMembership.objects.create(
            channel=channel,
            user=self.user,
            role=ChannelRole.ADMIN
        )
        url = reverse('chat:channel_add_members', kwargs={'slug': self.workspace.slug, 'channel_slug': channel.slug})
        resp = self.client.post(url, {}, HTTP_REFERER="https://evil.example/attack")
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.example', resp.url)
        self.assertIn(f"/chat/w/{self.workspace.slug}/c/{channel.slug}/details/", resp.url)

    # 4. Files Star Toggle & Move Referer Redirect
    def test_files_star_toggle_safe_referer_vs_malicious(self):
        self.client.force_login(self.user)
        stored_file = StoredFile.objects.create(
            workspace=self.workspace,
            name="test_file.txt",
            original_name="test_file.txt",
            uploaded_by=self.user,
            size_bytes=100,
            storage_path="test/path.txt"
        )
        url = reverse('files:file_star_toggle', kwargs={'slug': self.workspace.slug, 'file_id': stored_file.id})

        # Safe referer
        safe_ref = f"/files/w/{self.workspace.slug}/"
        resp = self.client.get(url, HTTP_REFERER=f"http://testserver{safe_ref}")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(safe_ref, resp.url)

        # Malicious referer
        resp_mal = self.client.get(url, HTTP_REFERER="https://evil.example/steal")
        self.assertEqual(resp_mal.status_code, 302)
        self.assertNotIn('evil.example', resp_mal.url)
        self.assertIn(f"/files/w/{self.workspace.slug}/", resp_mal.url)

    # 5. Files External Link Redirection Safety
    def test_file_preview_external_link_safe_vs_javascript(self):
        self.client.force_login(self.user)
        # Safe external link
        figma_file = StoredFile.objects.create(
            workspace=self.workspace,
            name="Figma Mockup",
            original_name="Figma Mockup",
            uploaded_by=self.user,
            size_bytes=0,
            is_external_link=True,
            external_url="https://www.figma.com/file/12345/design"
        )
        url = reverse('files:file_preview', kwargs={'slug': self.workspace.slug, 'file_id': figma_file.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "https://www.figma.com/file/12345/design")

        # Dangerous javascript external link
        js_file = StoredFile.objects.create(
            workspace=self.workspace,
            name="Malicious Link",
            original_name="Malicious Link",
            uploaded_by=self.user,
            size_bytes=0,
            is_external_link=True,
            external_url="javascript:alert(document.cookie)"
        )
        url_js = reverse('files:file_preview', kwargs={'slug': self.workspace.slug, 'file_id': js_file.id})
        resp_js = self.client.get(url_js)
        self.assertEqual(resp_js.status_code, 302)
        self.assertNotIn("javascript:", resp_js.url)
        self.assertIn(f"/files/w/{self.workspace.slug}/{js_file.id}/", resp_js.url)

    # 6. Notifications Referer Redirect
    def test_notification_mark_read_safe_vs_malicious_referer(self):
        self.client.force_login(self.user)
        notif = Notification.objects.create(
            recipient=self.user,
            actor=self.user,
            workspace=self.workspace,
            category=NotificationCategory.SYSTEM,
            notification_type=NotificationType.GENERAL,
            title="Security Alert",
            body="Batch 4 remediation in progress"
        )
        url = reverse('notifications:mark_read', kwargs={'notification_id': notif.id})

        # Safe referer
        resp_safe = self.client.post(url, HTTP_REFERER="http://testserver/notifications/")
        self.assertEqual(resp_safe.status_code, 302)
        self.assertIn("/notifications/", resp_safe.url)

        # Malicious referer
        resp_evil = self.client.post(url, HTTP_REFERER="https://evil.example/redirect")
        self.assertEqual(resp_evil.status_code, 302)
        self.assertNotIn("evil.example", resp_evil.url)
        self.assertIn("/notifications/", resp_evil.url)

    # 7. Workspaces Global Access Request Referer Redirect
    def test_workspace_access_request_safe_vs_malicious_referer(self):
        self.client.force_login(self.user)
        url = reverse('workspaces:submit_access_request')

        # Safe referer
        resp_safe = self.client.post(url, {'reason': 'Need permissions'}, HTTP_REFERER="http://testserver/workspaces/dashboard/")
        self.assertEqual(resp_safe.status_code, 302)
        self.assertIn("/workspaces/dashboard/", resp_safe.url)

        # Malicious referer
        resp_evil = self.client.post(url, {'reason': 'Need permissions'}, HTTP_REFERER="https://evil.example/hack")
        self.assertEqual(resp_evil.status_code, 302)
        self.assertNotIn("evil.example", resp_evil.url)
        self.assertIn("/workspaces/dashboard/", resp_evil.url)
