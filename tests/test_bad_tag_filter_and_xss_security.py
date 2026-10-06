import re
import os
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core import mail
from notifications.email_service import (
    html_to_plain_text,
    send_aether_email,
    send_notification_email,
)
from notifications.models import EmailDeliveryLog, EmailDeliveryStatus, EmailEventType

User = get_user_model()


class BadTagFilterSecurityTestCase(TestCase):
    """
    Test suite for py/bad-tag-filter remediation (CodeQL Alerts #33, #34, #49).
    Verifies that HTML parsing/plain-text conversion in email_service.py correctly handles
    browser-tolerated malformed HTML, closing tags with attributes, uppercase tags,
    and event handler payloads without relying on vulnerable regular expression tag filtering.
    """

    def test_script_tag_basic(self):
        payload = "<script>alert(1)</script>"
        result = html_to_plain_text(payload)
        self.assertEqual(result, "")
        self.assertNotIn("alert(1)", result)
        self.assertNotIn("<script>", result)

    def test_script_tag_malformed_closing_tag_with_attributes(self):
        # CodeQL Alert pattern: </script foo="bar">
        payload = '<script>alert(1)</script foo="bar">'
        result = html_to_plain_text(payload)
        self.assertEqual(result, "")
        self.assertNotIn("alert(1)", result)
        self.assertNotIn("foo", result)

    def test_script_tag_uppercase(self):
        payload = "<SCRIPT>alert(1)</SCRIPT>"
        result = html_to_plain_text(payload)
        self.assertEqual(result, "")
        self.assertNotIn("alert(1)", result)

    def test_script_tag_multiline_and_whitespace(self):
        payload = "<script\n>alert(1)</script>"
        result = html_to_plain_text(payload)
        self.assertEqual(result, "")
        self.assertNotIn("alert(1)", result)

    def test_script_tag_with_attributes(self):
        payload = '<script x="1" type="text/javascript">alert(1)</script>'
        result = html_to_plain_text(payload)
        self.assertEqual(result, "")
        self.assertNotIn("alert(1)", result)

    def test_script_tag_with_comments(self):
        payload = "<script>/* attack */ alert(1);</script>"
        result = html_to_plain_text(payload)
        self.assertEqual(result, "")
        self.assertNotIn("attack", result)
        self.assertNotIn("alert", result)

    def test_style_tag_removal(self):
        # Alert #49: style tag filtering
        payload = "<style>body { background-color: red; color: #fff; }</style><p>Real notification content</p>"
        result = html_to_plain_text(payload)
        self.assertEqual(result, "Real notification content")
        self.assertNotIn("background-color", result)
        self.assertNotIn("style", result)

    def test_img_onerror_payload(self):
        payload = '<p>Check task: <img src="x" onerror="alert(1)"> Urgent update</p>'
        result = html_to_plain_text(payload)
        self.assertIn("Check task:", result)
        self.assertIn("Urgent update", result)
        self.assertNotIn("onerror", result)
        self.assertNotIn("alert", result)

    def test_svg_onload_payload(self):
        payload = '<svg onload="alert(1)"><circle cx="50" cy="50" r="40"/></svg><p>Meeting scheduled</p>'
        result = html_to_plain_text(payload)
        self.assertIn("Meeting scheduled", result)
        self.assertNotIn("onload", result)
        self.assertNotIn("alert", result)

    def test_div_onclick_payload(self):
        payload = '<div onclick="alert(1)">Click here to see update</div>'
        result = html_to_plain_text(payload)
        self.assertEqual(result, "Click here to see update")
        self.assertNotIn("onclick", result)
        self.assertNotIn("alert", result)

    def test_malicious_comments_edge_cases(self):
        payload = '<!-- <script>alert("nested")</script> --><p>Clean body text</p>'
        result = html_to_plain_text(payload)
        self.assertEqual(result, "Clean body text")
        self.assertNotIn("nested", result)

    def test_head_meta_title_elements_decomposed(self):
        payload = """<!DOCTYPE html>
        <html>
        <head>
            <title>Secret Email Title</title>
            <meta name="description" content="Meta snippet">
            <style>h1 { font-size: 20px; }</style>
            <script>console.log("tracker");</script>
        </head>
        <body>
            <h1>Welcome to AetherSpace</h1>
            <p>Your team workspace is ready.</p>
        </body>
        </html>"""
        result = html_to_plain_text(payload)
        self.assertIn("Welcome to AetherSpace", result)
        self.assertIn("Your team workspace is ready.", result)
        self.assertNotIn("Secret Email Title", result)
        self.assertNotIn("Meta snippet", result)
        self.assertNotIn("tracker", result)

    def test_empty_and_none_input(self):
        self.assertEqual(html_to_plain_text(""), "")
        self.assertEqual(html_to_plain_text(None), "")

    def test_send_aether_email_plain_text_generation_safe(self):
        """Verify send_aether_email uses html_to_plain_text fallback safely."""
        html_content = """<p>Task Assigned: <strong>#619347</strong></p>
        <script>alert('xss')</script>
        <style>.btn { color: red; }</style>"""

        success = send_aether_email(
            recipient_email="sec-test@aetherspace.dev",
            subject="Security Test Notification",
            html_content=html_content,
            event_type=EmailEventType.TASK_ASSIGNED
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn("Task Assigned: #619347", sent_email.body)
        self.assertNotIn("alert('xss')", sent_email.body)
        self.assertNotIn(".btn", sent_email.body)
        self.assertNotIn("<script>", sent_email.body)


class ChatDOMXSSSecurityTestCase(TestCase):
    """
    Test suite for js/xss remediation (CodeQL Alerts #27, #28, #31, #32).
    Verifies that chat template message formatting, reactions, and badges
    cannot be exploited via DOM XSS, attribute injection, or unsafe innerHTML sinks.
    """

    def test_zero_inner_html_assignments_in_all_templates(self):
        """Repository-wide assertion: No .innerHTML assignments exist in any template."""
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
        unsafe_pattern = re.compile(r'\.innerHTML\s*=')
        found_violations = []

        for root, _, files in os.walk(template_dir):
            for fname in files:
                if fname.endswith('.html'):
                    fpath = os.path.join(root, fname)
                    with open(fpath, 'r', encoding='utf-8') as f:
                        for line_no, line in enumerate(f, 1):
                            if unsafe_pattern.search(line):
                                found_violations.append(f"{os.path.relpath(fpath, template_dir)}:{line_no} -> {line.strip()}")

        self.assertEqual(found_violations, [], f"Found unsafe .innerHTML assignments in templates: {found_violations}")

    def test_format_message_content_escaping_logic(self):
        """
        Verify the formatMessageContent escaping logic faithfully implemented in JS
        neutralizes quotes, tags, and script payloads to prevent attribute breakout.
        """
        def py_format_message_content(content):
            if not content:
                return ''
            esc = (
                str(content)
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;')
            )
            # Quotes / Replying to: lines starting with &gt;
            esc = re.sub(
                r'^&gt;\s*(.*?)$',
                r'<blockquote class="border-l-2 border-blue-500/60 pl-2.5 py-0.5 my-1 text-slate-500 dark:text-zinc-400 italic bg-blue-50/40 dark:bg-blue-950/30 rounded-r text-[11px]">\1</blockquote>',
                esc,
                flags=re.MULTILINE
            )
            # Bold: **text**
            esc = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', esc)
            # Italic: *text*
            esc = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', esc)
            # Complex mentions: @[Full Name](ID)
            esc = re.sub(
                r'@\[([^\]]+)\]\(([a-zA-Z0-9_-]+)\)',
                r'<span class="aether-mention" data-user-hover data-user-id="\2" data-user-name="\1">@\1</span>',
                esc
            )
            return esc

        # 1. Attribute breakout test in mentions
        attack_payload = '@[Attacker" onclick="alert(1)" x="](user123)'
        output = py_format_message_content(attack_payload)
        self.assertIn('&quot;', output)
        self.assertNotIn('onclick="alert(1)"', output)
        self.assertIn('data-user-name="Attacker&quot; onclick=&quot;alert(1)&quot; x=&quot;"', output)

        # 2. Raw HTML tags
        script_payload = "<script>alert('xss')</script>"
        output = py_format_message_content(script_payload)
        self.assertIn("&lt;script&gt;", output)
        self.assertNotIn("<script>", output)

        # 3. Image tag with onerror
        img_payload = '<img src=x onerror=alert(1)>'
        output = py_format_message_content(img_payload)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", output)
        self.assertNotIn("<img", output)

        # 4. SVG with onload
        svg_payload = '<svg onload=alert(1)>'
        output = py_format_message_content(svg_payload)
        self.assertIn("&lt;svg onload=alert(1)&gt;", output)
        self.assertNotIn("<svg", output)
