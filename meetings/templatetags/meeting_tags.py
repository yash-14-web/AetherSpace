from django import template

register = template.Library()


@register.filter(name='is_call_invite')
def is_call_invite(content):
    """Check if a chat message represents a Google Chat style call invite."""
    return isinstance(content, str) and content.startswith('CALL_INVITE:')


@register.filter(name='parse_call_invite')
def parse_call_invite(content):
    """
    Parses 'CALL_INVITE:meet-xxxx-xxxx|VIDEO|Title' into a dictionary.
    """
    if not isinstance(content, str) or not content.startswith('CALL_INVITE:'):
        return None
    raw = content.replace('CALL_INVITE:', '', 1)
    parts = raw.split('|')
    code = parts[0] if len(parts) > 0 else ''
    mode = parts[1] if len(parts) > 1 else 'VIDEO'
    title = parts[2] if len(parts) > 2 else 'Live Standup'
    return {
        'code': code,
        'mode': mode,
        'title': title,
        'is_video': mode.upper() == 'VIDEO',
    }
