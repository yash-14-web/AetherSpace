import re
import bleach
import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = [
    'p', 'strong', 'b', 'em', 'i', 'u', 's', 'strike', 'del', 'code', 'pre',
    'blockquote', 'ul', 'ol', 'li', 'a', 'br', 'span', 'input', 'div',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td'
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'target', 'rel'],
    'span': ['class', 'data-contributor-id', 'data-user-id', 'data-user-hover', 'data-user-name', 'data-workspace-slug'],
    'input': ['type', 'checked', 'disabled', 'class'],
    'li': ['class'],
    'ul': ['class'],
    'ol': ['class'],
    'div': ['class'],
    'blockquote': ['class'],
    'h1': ['class'],
    'h2': ['class'],
    'h3': ['class'],
    'h4': ['class'],
    'h5': ['class'],
    'h6': ['class'],
    'p': ['class'],
    'hr': ['class'],
    'del': ['class'],
    'th': ['align', 'class'],
    'td': ['align', 'class'],
    'table': ['class'],
    'code': ['class'],
    'pre': ['class'],
}

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


MENTION_PATTERN = re.compile(
    r'(?<![a-zA-Z0-9_])(?:@\[([^\]]+)\]\(([a-zA-Z0-9_-]+)\)|@(\d{5}[A-Za-z])\b|@([A-Z][a-zA-Z0-9_]*(?:\s+[A-Z][a-zA-Z0-9_]*)*|[a-zA-Z0-9_.-]+)\b)'
)


def _mention_replacer(match):
    # 1. Complex mentions: @[Full Name](ID)
    if match.group(1) and match.group(2):
        name = match.group(1)
        user_id = match.group(2)
        return (
            f'<span class="aether-mention inline-flex items-center space-x-1 px-2 py-0.5 rounded-full '
            f'text-xs font-semibold bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/25 '
            f'hover:bg-blue-500/25 cursor-pointer transition" data-user-hover="" data-user-id="{user_id}" '
            f'data-user-name="{name}">@{name}</span>'
        )

    # 2. Simple mentions by Contributor ID: @76044C
    if match.group(3):
        cid = match.group(3)
        return (
            f'<span class="aether-mention inline-flex items-center space-x-1 px-1.5 py-0.5 rounded-full '
            f'text-xs font-mono font-bold bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/25 '
            f'hover:bg-blue-500/25 cursor-pointer transition" data-user-hover="" data-contributor-id="{cid}" '
            f'data-user-name="{cid}">@{cid}</span>'
        )

    # 3. Text mentions by name or username: @Lead Developer or @username
    if match.group(4):
        raw_name = match.group(4).strip()
        return (
            f'<span class="aether-mention inline-flex items-center space-x-1 px-2 py-0.5 rounded-full '
            f'text-xs font-medium bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/25 '
            f'hover:bg-blue-500/25 cursor-pointer transition" data-user-hover="" data-user-name="{raw_name}">@{raw_name}</span>'
        )

    return match.group(0)


def transform_mentions(text):
    """
    Transforms @[Full Name](CONTRIBUTOR_ID or USER_ID), @CONTRIBUTOR_ID,
    and @Full Name into interactive styled mention pills with hover card triggers.
    Protects <code> and <pre> blocks from accidental mention conversion (e.g. @login_required).
    Uses single-pass replacement to prevent double-wrapping and regex collision.
    """
    if not text:
        return ""

    # Protect code blocks and inline code from mention replacement
    code_blocks = []

    def _preserve_code(m):
        code_blocks.append(m.group(0))
        return f"__AETHER_CODE_BLOCK_{len(code_blocks)-1}__"

    protected_text = re.sub(r'<(code|pre)\b[^>]*>[\s\S]*?</\1>', _preserve_code, text)

    # Transform strikethrough ~~text~~ into <del>text</del> (code blocks protected)
    protected_text = re.sub(r'~~(.*?)~~', r'<del>\1</del>', protected_text)

    # Transform mentions in prose
    text_with_mentions = MENTION_PATTERN.sub(_mention_replacer, protected_text)

    # Restore preserved code blocks
    if code_blocks:
        text_with_mentions = re.sub(
            r'__AETHER_CODE_BLOCK_(\d+)__',
            lambda m: code_blocks[int(m.group(1))],
            text_with_mentions
        )

    return text_with_mentions


def normalize_markdown_delimiters(text):
    """
    Normalizes markdown delimiters such as bold (**text **) and strikethrough (~~text ~~)
    where human authors accidentally include trailing/leading spaces inside the delimiter run.
    Ensures standard CommonMark parsers recognize them as valid formatting runs while strictly
    preserving code blocks and inline code.
    """
    if not text:
        return ""
    code_blocks = []

    def _preserve(m):
        code_blocks.append(m.group(0))
        return f"__AETHER_MD_CODE_{len(code_blocks)-1}__"

    # Match fenced code blocks and inline code
    protected = re.sub(r'(```[\s\S]*?```|`[^`\n]+`)', _preserve, str(text))

    # Normalize bold with trailing/leading inner spaces: ** word ** -> **word**
    protected = re.sub(
        r'\*\*([^\*\n]+?)\*\*',
        lambda m: f"**{m.group(1).strip()}**" if m.group(1).strip() else m.group(0),
        protected
    )
    # Normalize strikethrough: ~~ word ~~ -> ~~word~~
    protected = re.sub(
        r'~~([^~\n]+?)~~',
        lambda m: f"~~{m.group(1).strip()}~~" if m.group(1).strip() else m.group(0),
        protected
    )

    # Restore preserved code blocks
    if code_blocks:
        protected = re.sub(
            r'__AETHER_MD_CODE_(\d+)__',
            lambda m: code_blocks[int(m.group(1))],
            protected
        )

    return protected


def normalize_markdown_blocks(text):
    """
    Ensures block-level markdown structures (lists, blockquotes) preceded or followed
    by paragraph text are recognized by Markdown parsers by inserting a blank line boundary.
    """
    if not text:
        return ""
    lines = text.split("\n")
    normalized_lines = []
    list_marker = re.compile(r'^\s*([-*+]|\d+\.)\s+')
    quote_marker = re.compile(r'^\s*>\s*')
    for i, line in enumerate(lines):
        prev = lines[i - 1] if i > 0 else ""
        if list_marker.match(line):
            if i > 0 and prev.strip() and not list_marker.match(prev):
                normalized_lines.append("")
        elif quote_marker.match(line):
            if i > 0 and prev.strip() and not quote_marker.match(prev):
                normalized_lines.append("")
        elif i > 0 and quote_marker.match(prev) and line.strip() and not quote_marker.match(line):
            normalized_lines.append("")
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


@register.filter(name='render_rich_text')
def render_rich_text(value):
    """
    Converts markdown and formatted text to sanitized safe HTML.
    Supports bold, italic, lists, code, quotes, links, and @mentions.
    Protects against XSS while allowing rich formatting.
    """
    if not value:
        return ""

    # Normalize delimiter spacing (e.g. **bold **) before parsing
    normalized_value = normalize_markdown_delimiters(value)

    # Normalize block boundaries (lists, quotes) without preceding blank lines
    normalized_value = normalize_markdown_blocks(normalized_value)

    # Normalize standalone task brackets: [ ] Task or [x] Task -> - [ ] Task / - [x] Task
    normalized_value = re.sub(r'^(?:\s*)(\[[ xX]\]\s+.*)$', r'- \1', normalized_value, flags=re.MULTILINE)

    # Parse markdown into HTML
    raw_html = markdown.markdown(
        normalized_value,
        extensions=['nl2br', 'extra', 'tables', 'fenced_code']
    )

    # Convert task checkboxes in lists (both standard <li> and paragraph-wrapped <li><p>)
    raw_html = re.sub(
        r'<li>(?:\s*<p>)?\s*\[ \]\s*',
        r'<li class="task-list-item flex items-center space-x-2 my-1 list-none"><input type="checkbox" disabled class="rounded border-slate-300 dark:border-zinc-700 text-aether-blue pointer-events-none mr-1.5" /> ',
        raw_html
    )
    raw_html = re.sub(
        r'<li>(?:\s*<p>)?\s*\[[xX]\]\s*',
        r'<li class="task-list-item flex items-center space-x-2 my-1 list-none"><input type="checkbox" checked disabled class="rounded border-slate-300 dark:border-zinc-700 text-aether-blue pointer-events-none mr-1.5" /> ',
        raw_html
    )

    # Convert task checkboxes in paragraph / newline contexts if any remain
    raw_html = re.sub(
        r'(?:<p>|<br\s*/?>|^)\s*-\s*\[ \]\s*([^<\n]+)',
        r'<div class="task-list-item flex items-center space-x-2 my-1"><input type="checkbox" disabled class="rounded border-slate-300 dark:border-zinc-700 text-aether-blue pointer-events-none mr-1.5" /> <span>\1</span></div>',
        raw_html
    )
    raw_html = re.sub(
        r'(?:<p>|<br\s*/?>|^)\s*-\s*\[[xX]\]\s*([^<\n]+)',
        r'<div class="task-list-item flex items-center space-x-2 my-1"><input type="checkbox" checked disabled class="rounded border-slate-300 dark:border-zinc-700 text-aether-blue pointer-events-none mr-1.5" /> <span class="line-through text-slate-400 dark:text-zinc-500">\1</span></div>',
        raw_html
    )

    # Transform @mentions into pills (code blocks protected)
    html_with_mentions = transform_mentions(raw_html)

    # Sanitize HTML using bleach
    cleaned_html = bleach.clean(
        html_with_mentions,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True
    )

    # Ensure external links open securely in a new tab
    cleaned_html = re.sub(
        r'<a (?!.*target=)([^>]+)>',
        r'<a target="_blank" rel="noopener noreferrer" \1>',
        cleaned_html
    ).strip()

    # Unwrap single paragraph <p>...</p> tags so inline messages don't inherit browser block margins
    if cleaned_html.startswith('<p>') and cleaned_html.endswith('</p>') and cleaned_html.count('<p>') == 1:
        cleaned_html = cleaned_html[3:-4].strip()

    return mark_safe(cleaned_html)
