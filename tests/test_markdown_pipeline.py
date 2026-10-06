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


class Batch3ReDoSSecurityTests(TestCase):
    """
    Security regression tests for Batch 3: Polynomial ReDoS remediation.
    Validates deterministic linear mention extraction, bounded rich_text mention pattern,
    and resilience against catastrophic backtracking on adversarial input strings.
    """
    def test_extract_mention_cids_formats(self):
        from core.templatetags.rich_text import extract_mention_cids
        # Format 1: @[Display Name](CID)
        self.assertEqual(extract_mention_cids("Hello @[Ramu M](26457C)"), {"26457C"})
        self.assertEqual(extract_mention_cids("@[José García](26457C) please review"), {"26457C"})
        # Format 2: @CID
        self.assertEqual(extract_mention_cids("Hello @26457C"), {"26457C"})
        self.assertEqual(extract_mention_cids("(@26457C)"), {"26457C"})
        self.assertEqual(extract_mention_cids("@26457C,"), {"26457C"})
        self.assertEqual(extract_mention_cids("@26457C."), {"26457C"})
        self.assertEqual(extract_mention_cids("@26457C!"), {"26457C"})
        # Multiple mentions
        self.assertEqual(
            extract_mention_cids("@26457C please sync with @12345C and @[Alex](99999Z)"),
            {"26457C", "12345C", "99999Z"}
        )
        # Repeated mentions
        self.assertEqual(extract_mention_cids("@26457C pinging @26457C again"), {"26457C"})

    def test_extract_mention_cids_malformed_rejected(self):
        from core.templatetags.rich_text import extract_mention_cids
        malformed = [
            "@[broken]",
            "@[name]()",
            "@[name](not-an-id)",
            "@123",
            "@abcdef",
            "email@26457C",
            "@26457Cextra",
            "@[name\nwith\nnewline](26457C)",
        ]
        for m in malformed:
            self.assertEqual(extract_mention_cids(m), set(), f"Failed to reject: {m}")

    def test_rich_text_transform_mentions_formats(self):
        # Format 1
        rendered = render_rich_text("Hello @[Ramu M](26457C)")
        self.assertIn("aether-mention", rendered)
        self.assertIn("@Ramu M", rendered)
        self.assertIn('data-user-id="26457C"', rendered)

        # Format 2
        rendered_cid = render_rich_text("Hello @26457C")
        self.assertIn("aether-mention", rendered_cid)
        self.assertIn("@26457C", rendered_cid)
        self.assertIn('data-contributor-id="26457C"', rendered_cid)

    def test_adversarial_redos_inputs_complete_in_bounded_linear_time(self):
        import time
        from core.templatetags.rich_text import extract_mention_cids

        adversarial_inputs = [
            ("repeating_brackets", "@[" * 25000),
            ("repeating_at", "@" * 50000),
            ("long_bracketed", "@[" + "a" * 25000 + "](26457C)"),
            ("long_parenthesized", "@[test](" + "a" * 25000 + ")"),
            ("many_open_parens", "(" * 50000),
            ("many_open_brackets", "[" * 50000),
            ("malformed_mentions", "@[broken](" * 10000),
            ("surrounding_text", "x" * 25000 + "@" + "y" * 25000),
        ]

        for name, payload in adversarial_inputs:
            start = time.perf_counter()
            cids = extract_mention_cids(payload)
            elapsed = time.perf_counter() - start
            # Must complete well under 500ms (linear execution)
            self.assertLess(elapsed, 0.5, f"Adversarial input {name} took too long: {elapsed:.3f}s")
            self.assertEqual(len(cids), 0)

    def test_linear_scaling_n_2n_4n_8n(self):
        import time
        from core.templatetags.rich_text import extract_mention_cids

        # Verify linear growth (not polynomial quadratic O(N^2))
        base_n = 5000
        timings = []
        for multiplier in [1, 2, 4, 8]:
            n = base_n * multiplier
            payload = "@[" * n
            t0 = time.perf_counter()
            extract_mention_cids(payload)
            timings.append(time.perf_counter() - t0)

        # In quadratic O(N^2), 8N would be 64x slower than 1N.
        # In linear O(N), 8N is at most ~16x slower (accounting for GC / CPU frequency scaling).
        ratio = timings[3] / max(timings[0], 0.0001)
        self.assertLess(ratio, 25.0, f"Polynomial scaling detected! 8N/1N ratio was {ratio:.2f}x")
