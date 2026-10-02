import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from workspaces.models import Workspace, WorkspaceMembership
from core.templatetags.rich_text import render_rich_text, transform_mentions

User = get_user_model()

class MarkdownPipelineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='marcus_aether',
            email='marcus@aether.test',
            password='Password123!',
            first_name='Marcus',
            last_name='Aurelius'
        )
        self.workspace = Workspace.objects.create(
            name='Aether Workspace',
            slug='aether-workspace',
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role='admin'
        )
        self.client = Client()

    def test_code_block_decorator_is_not_treated_as_mention(self):
        markdown_source = "```python\n@login_required\n@property\ndef get_status():\n    return 'active'\n```"
        rendered = render_rich_text(markdown_source)
        self.assertIn("@login_required", rendered)
        self.assertIn("@property", rendered)
        self.assertNotIn("aether-mention", rendered)
        self.assertIn("<pre>", rendered)
        self.assertIn("<code", rendered)

    def test_inline_code_symbol_is_not_treated_as_mention(self):
        markdown_source = "Check the `@classmethod` decorator in `core/views.py`."
        rendered = render_rich_text(markdown_source)
        self.assertIn("<code>@classmethod</code>", rendered)
        self.assertNotIn("aether-mention", rendered)

    def test_normal_mention_in_text(self):
        markdown_source = "Please review this PR @marcus_aether"
        rendered = render_rich_text(markdown_source)
        self.assertIn("aether-mention", rendered)
        self.assertIn("@marcus_aether", rendered)

    def test_strikethrough_and_table_support(self):
        markdown_source = "~~old requirement~~\n\n| Column 1 | Column 2 |\n| --- | --- |\n| Cell A | Cell B |"
        rendered = render_rich_text(markdown_source)
        self.assertIn("<del>old requirement</del>", rendered)
        self.assertIn("<table>", rendered)
        self.assertIn("<th>Column 1</th>", rendered)
        self.assertIn("<td>Cell A</td>", rendered)

    def test_markdown_preview_api_auth_required(self):
        url = reverse('core:markdown_preview')
        response = self.client.post(url, json.dumps({'content': 'test'}), content_type='application/json')
        # Anonymous user should be redirected to login
        self.assertEqual(response.status_code, 302)

    def test_markdown_preview_api_exact_parity_with_render_rich_text(self):
        self.client.force_login(self.user)
        url = reverse('core:markdown_preview')
        source = (
            "## Sprint Review\n\n"
            "- Item 1: **Completed**\n"
            "- Item 2: ~~Postponed~~\n\n"
            "```python\n"
            "@login_required\n"
            "def test_view(): pass\n"
            "```\n\n"
            "Pinging @marcus_aether for feedback."
        )

        response = self.client.post(url, json.dumps({'content': source}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')

        expected_html = str(render_rich_text(source))
        self.assertEqual(data.get('html'), expected_html)

    def test_tasks_markdown_preview_endpoint_parity(self):
        self.client.force_login(self.user)
        url = reverse('tasks:markdown_preview', kwargs={'slug': self.workspace.slug})
        source = "### Task Details\n\nFix authentication in `auth_service.py`."
        response = self.client.post(url, json.dumps({'content': source}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('html'), str(render_rich_text(source)))

    def test_loose_markdown_delimiter_normalization(self):
        source = "**I Saw the Issues I will soon fixed as soon as possible **"
        rendered = render_rich_text(source)
        self.assertIn("<strong>I Saw the Issues I will soon fixed as soon as possible</strong>", rendered)
        self.assertNotIn("**", rendered)

        # Code blocks with **kwargs should remain untouched
        code_source = "```python\ndef test(**kwargs):\n    return kwargs\n```"
        rendered_code = render_rich_text(code_source)
        self.assertIn("**kwargs", rendered_code)
        self.assertNotIn("<strong>", rendered_code)
