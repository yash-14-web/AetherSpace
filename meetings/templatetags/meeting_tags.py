import re
from django import template

register = template.Library()


@register.filter(name='is_call_invite')
def is_call_invite(content):
    """Check if a chat message represents a Google Chat style call invite."""
    return isinstance(content, str) and content.startswith('CALL_INVITE:')


@register.filter(name='parse_call_invite')
def parse_call_invite(content):
    """
    Parses 'CALL_INVITE:meet-xxxx-xxxx:VIDEO:Title' or pipe-separated into a dictionary
    with database-verified meeting status.
    """
    if not isinstance(content, str) or not content.startswith('CALL_INVITE:'):
        return None

    raw = content.replace('CALL_INVITE:', '', 1).strip()

    # Safely extract meeting code matching standard meet-xxxx-xxxx
    code_match = re.search(r'meet-[a-z0-9]{4}-[a-z0-9]{4}', raw, re.IGNORECASE)
    if code_match:
        code = code_match.group(0).lower()
    else:
        code = re.split(r'[:|]', raw)[0].strip().lower()

    # Determine mode and title from raw string
    if '|' in raw:
        parts = raw.split('|')
        mode = parts[1].strip() if len(parts) > 1 else 'VIDEO'
        title = parts[2].strip() if len(parts) > 2 else 'Quick Meeting'
    else:
        parts = raw.split(':')
        mode = parts[1].strip() if len(parts) > 1 else 'VIDEO'
        title = ':'.join(parts[2:]).strip() if len(parts) > 2 else 'Quick Meeting'

    # Check meeting status in database
    from meetings.models import Meeting, MeetingStatus
    meeting = Meeting.objects.filter(meeting_code__iexact=code).select_related('host').first()

    if meeting:
        is_live = (meeting.status == MeetingStatus.LIVE)
        is_ended = (meeting.status in [MeetingStatus.ENDED, MeetingStatus.CANCELLED])
        status = meeting.status
        title = meeting.title or title
    else:
        is_live = False
        is_ended = True
        status = 'ended'

    return {
        'code': code,
        'mode': mode,
        'title': title,
        'is_video': mode.upper() == 'VIDEO',
        'is_live': is_live,
        'is_ended': is_ended,
        'status': status,
        'meeting': meeting,
    }

