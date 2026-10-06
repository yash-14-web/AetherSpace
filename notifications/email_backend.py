import sys
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.html import strip_tags
import re


class CleanConsoleEmailBackend(BaseEmailBackend):
    """
    Clean, human-readable console email backend for development.
    Avoids raw MIME dumps, base64 data, boundary markers, and raw HTML tags
    in the terminal stdout while keeping developers informed of outgoing emails.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stream = kwargs.pop('stream', sys.stdout)

    def write_message(self, message):
        recipients = ', '.join(message.to)
        subject = message.subject
        from_email = message.from_email

        # Prefer plain-text body; if body has HTML or styles, clean it up
        body = message.body or ''
        if not body and hasattr(message, 'alternatives'):
            for alt_content, alt_mimetype in message.alternatives:
                if alt_mimetype == 'text/plain':
                    body = alt_content
                    break
                elif alt_mimetype == 'text/html':
                    body = alt_content

        # Safely convert to clean plain text without regex tag filters
        from .email_service import html_to_plain_text
        clean_body = html_to_plain_text(body)

        banner = (
            "\n"
            + "=" * 80 + "\n"
            + f"[AETHERSPACE EMAIL OUTBOX]\n"
            + f"To:      {recipients}\n"
            + f"From:    {from_email}\n"
            + f"Subject: {subject}\n"
            + "-" * 80 + "\n"
            + f"{clean_body}\n"
            + "=" * 80 + "\n"
        )
        self.stream.write(banner)
        self.stream.flush()

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        count = 0
        for message in email_messages:
            self.write_message(message)
            count += 1
        return count
