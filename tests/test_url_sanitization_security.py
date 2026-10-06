"""
Batch 5: Incomplete URL Substring Sanitization Hardening Tests.
Validates authoritative URL and hostname validation across files, accounts, and workspaces.
Eliminates py/incomplete-url-substring-sanitization (CWE-20) vulnerabilities.
"""

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from core.utils import (
    is_domain_match,
    validate_external_url,
    is_safe_external_url,
    validate_image_url,
)
from files.services import detect_external_provider
from files.forms import FileUploadForm
from files.models import StoredFile, FileCategory
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from accounts.services import process_and_save_avatar, process_and_save_banner
from workspaces.services import process_and_save_workspace_logo

User = get_user_model()


class Batch5UrlSanitizationUnitTests(TestCase):
    """
    Unit tests for core URL validation and provider detection against the complete security matrix.
    """

    def test_valid_http_and_https_urls(self):
        valid_urls = [
            'https://example.com',
            'http://example.com',
            'https://www.example.com/path?query=1#frag',
            'https://sub.domain.example.org:8080/resource',
        ]
        for u in valid_urls:
            is_valid, cleaned, err = validate_external_url(u)
            self.assertTrue(is_valid, f"Expected valid for: {u}, error: {err}")
            self.assertEqual(cleaned, u)
            self.assertIsNone(err)
            self.assertTrue(is_safe_external_url(u))

    def test_invalid_schemes_rejected(self):
        dangerous_schemes = [
            'javascript:alert(1)',
            'JaVaScRiPt:alert(1)',
            'data:text/html,<script>alert(1)</script>',
            'DATA:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==',
            'vbscript:alert(1)',
            'file:///etc/passwd',
            'file:///c:/windows/win.ini',
            'about:blank',
            'blob:https://example.com/uuid',
        ]
        for u in dangerous_schemes:
            is_valid, cleaned, err = validate_external_url(u)
            self.assertFalse(is_valid, f"Dangerous scheme should be rejected: {u}")
            self.assertFalse(is_safe_external_url(u))
            self.assertIsNotNone(err)
            self.assertEqual(detect_external_provider(u), 'Web Resource')

    def test_protocol_relative_urls_rejected(self):
        protocol_relative = [
            '//evil.example',
            '//evil.example/login',
            '///evil.example',
        ]
        for u in protocol_relative:
            is_valid, cleaned, err = validate_external_url(u)
            self.assertFalse(is_valid, f"Protocol-relative should be rejected: {u}")
            self.assertFalse(is_safe_external_url(u))
            self.assertEqual(detect_external_provider(u), 'Web Resource')

    def test_backslash_variations_rejected(self):
        backslash_urls = [
            r'https:\evil.example',
            r'https:/\evil.example',
            r'\\evil.example',
            r'https://evil.example\path',
            r'https://example.com/\evil.example',
        ]
        for u in backslash_urls:
            is_valid, cleaned, err = validate_external_url(u)
            self.assertFalse(is_valid, f"Backslash URL should be rejected: {u}")
            self.assertFalse(is_safe_external_url(u))
            self.assertEqual(detect_external_provider(u), 'Web Resource')

    def test_userinfo_host_confusion_not_spoofed(self):
        # Even with deceptive userinfo, the actual hostname is evil.example
        deceptive = 'https://figma.com@evil.example/'
        is_valid, cleaned, err = validate_external_url(deceptive)
        self.assertTrue(is_valid)  # Valid HTTP URL, but provider MUST NOT be fooled!
        self.assertEqual(detect_external_provider(deceptive), 'Web Resource')

        deceptive_github = 'https://github.com@attacker.com/'
        self.assertEqual(detect_external_provider(deceptive_github), 'Web Resource')

        deceptive_drive = 'https://drive.google.com@phishing.site/'
        self.assertEqual(detect_external_provider(deceptive_drive), 'Web Resource')

    def test_deceptive_subdomain_and_suffix_spoofing(self):
        spoofs = [
            ('https://figma.com.evil.example/', 'Web Resource'),
            ('https://evil.example/figma.com', 'Web Resource'),
            ('https://myfigma.com/', 'Web Resource'),
            ('https://fakebox.com/', 'Web Resource'),
            ('https://box.com.attacker.com/', 'Web Resource'),
            ('https://myloom.com/', 'Web Resource'),
            ('https://evil-youtube.com/', 'Web Resource'),
            ('https://youtube.com.attacker.com/', 'Web Resource'),
            ('https://notion.so.malicious.net/', 'Web Resource'),
            ('https://dropbox.com.phish.cc/', 'Web Resource'),
            ('https://github.com.attacker.com/', 'Web Resource'),
            ('https://google.com.drive.google.com.evil.com/', 'Web Resource'),
        ]
        for url_str, expected in spoofs:
            self.assertEqual(
                detect_external_provider(url_str),
                expected,
                f"URL '{url_str}' was incorrectly classified as a trusted provider instead of '{expected}'"
            )

    def test_all_eight_providers_authoritative_recognition(self):
        # 1. Figma Design (figma.com)
        self.assertEqual(detect_external_provider('https://figma.com/file/123/design'), 'Figma Design')
        self.assertEqual(detect_external_provider('https://www.figma.com/file/123/design'), 'Figma Design')

        # 2. Google Drive (drive.google.com, docs.google.com)
        self.assertEqual(detect_external_provider('https://drive.google.com/drive/folders/123'), 'Google Drive')
        self.assertEqual(detect_external_provider('https://docs.google.com/document/d/123/edit'), 'Google Drive')

        # 3. GitHub (github.com)
        self.assertEqual(detect_external_provider('https://github.com/aetherspace/core'), 'GitHub')
        self.assertEqual(detect_external_provider('https://gist.github.com/user/xyz'), 'GitHub')

        # 4. Notion (notion.so, notion.site)
        self.assertEqual(detect_external_provider('https://notion.so/workspace/123'), 'Notion')
        self.assertEqual(detect_external_provider('https://team.notion.site/docs'), 'Notion')

        # 5. Dropbox (dropbox.com)
        self.assertEqual(detect_external_provider('https://dropbox.com/s/123/doc'), 'Dropbox')
        self.assertEqual(detect_external_provider('https://www.dropbox.com/s/123/doc'), 'Dropbox')

        # 6. Box (box.com)
        self.assertEqual(detect_external_provider('https://box.com/s/123'), 'Box')
        self.assertEqual(detect_external_provider('https://app.box.com/s/123'), 'Box')

        # 7. Loom Video (loom.com)
        self.assertEqual(detect_external_provider('https://loom.com/share/123'), 'Loom Video')
        self.assertEqual(detect_external_provider('https://www.loom.com/share/123'), 'Loom Video')

        # 8. YouTube (youtube.com, youtu.be)
        self.assertEqual(detect_external_provider('https://youtube.com/watch?v=123'), 'YouTube')
        self.assertEqual(detect_external_provider('https://www.youtube.com/watch?v=123'), 'YouTube')
        self.assertEqual(detect_external_provider('https://youtu.be/123'), 'YouTube')

        # Fallback Web Resource
        self.assertEqual(detect_external_provider('https://developer.mozilla.org/'), 'Web Resource')
        self.assertEqual(detect_external_provider('https://example.com/'), 'Web Resource')

    def test_encoded_and_obfuscated_variants_rejected(self):
        obfuscated = [
            '%6aavascript:alert(1)',
            '%4a%41%56%41script:alert(1)',
            '%2f%2fevil.example',
            '%5c%5cevil.example',
        ]
        for u in obfuscated:
            is_valid, _, _ = validate_external_url(u)
            self.assertFalse(is_valid, f"Obfuscated target should be rejected: {u}")
            self.assertEqual(detect_external_provider(u), 'Web Resource')

    def test_whitespace_and_case_normalization(self):
        # Case normalization for scheme
        is_valid, cleaned, _ = validate_external_url('HTTP://EXAMPLE.COM/PATH')
        self.assertTrue(is_valid)

        is_valid_https, cleaned_https, _ = validate_external_url('HTTPS://EXAMPLE.COM/PATH')
        self.assertTrue(is_valid_https)

        # Whitespace trimming
        is_valid_ws, cleaned_ws, _ = validate_external_url('   https://example.com/trimmed   ')
        self.assertTrue(is_valid_ws)
        self.assertEqual(cleaned_ws, 'https://example.com/trimmed')

        # Dangerous scheme with whitespace
        is_valid_bad, _, _ = validate_external_url('   javascript:alert(1)   ')
        self.assertFalse(is_valid_bad)

    def test_empty_and_none_values(self):
        for val in (None, '', '   '):
            is_valid, _, _ = validate_external_url(val)
            self.assertFalse(is_valid)
            self.assertEqual(detect_external_provider(val), 'Web Resource')

    def test_malformed_urls_rejected(self):
        malformed = [
            'https:',
            'https:example.com',
            'http:///example.com',
            'https://example.com:999999/',  # Invalid port
            'https://example.com:0/',       # Invalid port
        ]
        for u in malformed:
            is_valid, _, _ = validate_external_url(u)
            self.assertFalse(is_valid, f"Expected malformed URL to fail: {u}")
            self.assertEqual(detect_external_provider(u), 'Web Resource')


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class Batch5FilesLifecycleSecurityTests(TestCase):
    """
    Integration tests verifying external link lifecycle:
    Create -> Validate -> Store -> Display -> Preview -> Download.
    """

    def setUp(self):
        self.client = Client()
        self.password = "SecurePass123!"
        self.user = User.objects.create_user(
            email="batch5.tester@aetherspace.dev",
            password=self.password,
            full_name="Batch5 Tester",
            contributor_id="55555B",
            is_active=True
        )
        if hasattr(self.user, 'approval_status'):
            from accounts.models import ApprovalStatus
            self.user.approval_status = ApprovalStatus.APPROVED
            self.user.save(update_fields=['approval_status'])

        self.workspace = Workspace.objects.create(
            name="Batch 5 Workspace",
            slug="batch5-ws",
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    def test_form_validation_rejects_malicious_link(self):
        # 1. Reject javascript:
        form_js = FileUploadForm(data={
            'upload_type': 'link',
            'external_url': 'javascript:alert(document.cookie)',
            'name': 'Malicious Link',
        }, workspace=self.workspace)
        self.assertFalse(form_js.is_valid())
        self.assertIn('external_url', form_js.errors)

        # 2. Reject data:
        form_data = FileUploadForm(data={
            'upload_type': 'link',
            'external_url': 'data:text/html,<script>alert(1)</script>',
            'name': 'Data Link',
        }, workspace=self.workspace)
        self.assertFalse(form_data.is_valid())
        self.assertIn('external_url', form_data.errors)

        # 3. Reject backslashes
        form_slash = FileUploadForm(data={
            'upload_type': 'link',
            'external_url': r'https:\evil.example',
            'name': 'Backslash Link',
        }, workspace=self.workspace)
        self.assertFalse(form_slash.is_valid())
        self.assertIn('external_url', form_slash.errors)

        # 4. Accept legitimate link
        form_valid = FileUploadForm(data={
            'upload_type': 'link',
            'external_url': 'https://www.figma.com/file/123/Project',
            'name': 'Figma Mockup',
        }, workspace=self.workspace)
        self.assertTrue(form_valid.is_valid())
        self.assertEqual(form_valid.cleaned_data['external_url'], 'https://www.figma.com/file/123/Project')

    def test_model_safe_external_url_defense_in_depth(self):
        # Valid external link
        valid_file = StoredFile.objects.create(
            workspace=self.workspace,
            name="Valid Link",
            original_name="Valid Link",
            uploaded_by=self.user,
            is_external_link=True,
            external_url="https://github.com/aetherspace/core",
            category=FileCategory.URL_LINK
        )
        self.assertEqual(valid_file.safe_external_url, "https://github.com/aetherspace/core")
        self.assertEqual(valid_file.file_url, "https://github.com/aetherspace/core")

        # Injected or legacy malicious link in database
        malicious_file = StoredFile.objects.create(
            workspace=self.workspace,
            name="Legacy Malicious",
            original_name="Legacy Malicious",
            uploaded_by=self.user,
            is_external_link=True,
            external_url="javascript:alert(1)",
            category=FileCategory.URL_LINK
        )
        # Must neutralize to '#' to prevent DOM XSS in templates
        self.assertEqual(malicious_file.safe_external_url, "#")
        self.assertEqual(malicious_file.file_url, "#")

    def test_template_rendering_uses_safe_external_url(self):
        self.client.force_login(self.user)
        # Store a file with an unsafe URL directly
        unsafe_file = StoredFile.objects.create(
            workspace=self.workspace,
            name="Unsafe File",
            original_name="Unsafe File",
            uploaded_by=self.user,
            is_external_link=True,
            external_url="javascript:alert(document.cookie)",
            category=FileCategory.URL_LINK
        )
        url = reverse('files:file_detail', kwargs={'slug': self.workspace.slug, 'file_id': unsafe_file.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Assert that the href attribute does NOT contain executable javascript:
        content = response.content.decode('utf-8')
        self.assertNotIn('href="javascript:', content)
        self.assertNotIn("href='javascript:", content)

    def test_file_version_upload_validates_new_external_url(self):
        self.client.force_login(self.user)
        stored_file = StoredFile.objects.create(
            workspace=self.workspace,
            name="Cloud Doc",
            original_name="Cloud Doc",
            uploaded_by=self.user,
            is_external_link=True,
            external_url="https://notion.so/original-page",
            category=FileCategory.URL_LINK
        )
        url = reverse('files:file_version_upload', kwargs={'slug': self.workspace.slug, 'file_id': stored_file.id})

        # 1. Attempt updating to malicious URL
        resp_bad = self.client.post(url, {'external_url': 'javascript:alert(1)'})
        self.assertEqual(resp_bad.status_code, 302)
        stored_file.refresh_from_db()
        self.assertEqual(stored_file.external_url, "https://notion.so/original-page")

        # 2. Update to legitimate new URL
        resp_good = self.client.post(url, {'external_url': 'https://notion.so/updated-page'})
        self.assertEqual(resp_good.status_code, 302)
        stored_file.refresh_from_db()
        self.assertEqual(stored_file.external_url, "https://notion.so/updated-page")

    def test_file_preview_and_download_block_unsafe_redirect(self):
        self.client.force_login(self.user)
        unsafe_file = StoredFile.objects.create(
            workspace=self.workspace,
            name="Unsafe Target",
            original_name="Unsafe Target",
            uploaded_by=self.user,
            is_external_link=True,
            external_url="javascript:alert(1)",
            category=FileCategory.URL_LINK
        )
        # Preview
        preview_url = reverse('files:file_preview', kwargs={'slug': self.workspace.slug, 'file_id': unsafe_file.id})
        resp_prev = self.client.get(preview_url)
        self.assertEqual(resp_prev.status_code, 302)
        self.assertNotIn("javascript:", resp_prev.url)
        self.assertIn(f"/files/w/{self.workspace.slug}/{unsafe_file.id}/", resp_prev.url)

        # Download
        dl_url = reverse('files:file_download', kwargs={'slug': self.workspace.slug, 'file_id': unsafe_file.id})
        resp_dl = self.client.get(dl_url)
        self.assertEqual(resp_dl.status_code, 302)
        self.assertNotIn("javascript:", resp_dl.url)
        self.assertIn(f"/files/w/{self.workspace.slug}/{unsafe_file.id}/", resp_dl.url)


class Batch5ImageAndLogoValidationTests(TestCase):
    """
    Unit and integration tests for avatar, banner, and workspace logo URL sanitization.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="batch5.image@aetherspace.dev",
            password="SecurePass123!",
            full_name="Image Tester",
            contributor_id="77777I",
            is_active=True
        )
        self.workspace = Workspace.objects.create(
            name="Image Workspace",
            slug="image-ws",
            owner=self.user
        )

    def test_avatar_url_validation(self):
        # 1. Dangerous scheme rejected
        ok, msg = process_and_save_avatar(self.user, avatar_url='javascript:alert(1)')
        self.assertFalse(ok)
        self.assertNotEqual(self.user.avatar, 'javascript:alert(1)')

        # 2. Preset accepted
        ok_preset, _ = process_and_save_avatar(self.user, avatar_url='preset:teal')
        self.assertTrue(ok_preset)
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, 'preset:teal')

        # 3. Legitimate external URL accepted
        ok_url, _ = process_and_save_avatar(self.user, avatar_url='https://images.example.com/avatar.jpg')
        self.assertTrue(ok_url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, 'https://images.example.com/avatar.jpg')

        # 4. Domain-only string auto-prefixes https://
        ok_norm, _ = process_and_save_avatar(self.user, avatar_url='cdn.example.com/avatar.png')
        self.assertTrue(ok_norm)
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar, 'https://cdn.example.com/avatar.png')

    def test_banner_url_validation(self):
        # Dangerous scheme rejected
        ok_bad, _ = process_and_save_banner(self.user, banner_url='data:text/html,bad')
        self.assertFalse(ok_bad)

        # Legitimate URL accepted
        ok_good, _ = process_and_save_banner(self.user, banner_url='https://images.example.com/banner.jpg')
        self.assertTrue(ok_good)

    def test_workspace_logo_url_validation(self):
        # Dangerous scheme rejected
        ok_bad, _ = process_and_save_workspace_logo(self.workspace, logo_url='javascript:alert(1)')
        self.assertFalse(ok_bad)
        self.workspace.refresh_from_db()
        self.assertNotEqual(self.workspace.logo, 'javascript:alert(1)')

        # Legitimate URL accepted
        ok_good, _ = process_and_save_workspace_logo(self.workspace, logo_url='https://cdn.example.com/logo.svg')
        self.assertTrue(ok_good)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.logo, 'https://cdn.example.com/logo.svg')
