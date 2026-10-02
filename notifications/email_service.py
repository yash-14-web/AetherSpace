import html
import logging
import re
from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string, get_template
from django.utils.html import strip_tags
from django.utils import timezone

from .models import EmailDeliveryLog, EmailDeliveryStatus, EmailEventType

logger = logging.getLogger(__name__)

# Mandatory transactional events that cannot be suppressed by user preferences
MANDATORY_TRANSACTIONAL_EVENTS = {
    EmailEventType.PASSWORD_RESET,
    EmailEventType.EMAIL_VERIFICATION,
    'PASSWORD_RESET',
    'EMAIL_VERIFICATION',
}


def should_send_email_to_user(user, event_type):
    """
    Inspects user preferences to determine if email notifications are permitted.
    Mandatory transactional security/account emails (Password Reset, Email Verification)
    bypass normal notification frequency and suppression preferences.
    """
    if not user or not getattr(user, 'email', None):
        return False

    # Mandatory transactional security/account emails must never be suppressed by preferences
    if event_type in MANDATORY_TRANSACTIONAL_EVENTS:
        return True

    profile = getattr(user, 'profile', None)
    if not profile or not profile.preferences:
        return True

    prefs = profile.preferences.get('notifications', {})
    
    # 1. Global Frequency Check
    if prefs.get('email_frequency') == 'never':
        return False

    # 2. Specific Event Category Checks
    if event_type in ['TASK_ASSIGNED', 'TASK_STATUS_CHANGED'] and not prefs.get('task_alerts', True):
        return False
    if event_type in ['MEETING_SCHEDULED', 'MEETING_UPDATED', 'MEETING_CANCELLED'] and not prefs.get('meeting_reminders', True):
        return False
    if event_type in ['BUG_ASSIGNED', 'BUG_STATUS_CHANGED'] and not prefs.get('bug_alerts', True):
        return False
    if event_type in ['CHAT_MENTION', 'CHAT_DM', 'MENTION'] and not prefs.get('chat_mentions', True):
        return False

    return True


def is_duplicate_email(recipient_email, event_type, subject):
    """
    Prevents duplicate emails sent within a 60-second window.
    """
    recent_cutoff = timezone.now() - timedelta(seconds=60)
    return EmailDeliveryLog.objects.filter(
        recipient_email=recipient_email,
        event_type=event_type,
        subject=subject,
        status=EmailDeliveryStatus.SENT,
        sent_at__gte=recent_cutoff
    ).exists()


def send_notification_email(recipient_user, event_type, subject, template_name, context):
    """
    Primary multi-part HTML & text email delivery pipeline.
    Respects preferences, prevents duplicates, and logs results safely.
    """
    recipient_email = getattr(recipient_user, 'email', None)
    if not recipient_email:
        return False

    # Check recipient preferences
    if not should_send_email_to_user(recipient_user, event_type):
        EmailDeliveryLog.objects.create(
            recipient_email=recipient_email,
            event_type=event_type,
            subject=subject,
            status=EmailDeliveryStatus.SUPPRESSED,
            error_message="Suppressed by user notification preferences (frequency=never or alert disabled)."
        )
        return False

    # Check duplicate prevention
    if is_duplicate_email(recipient_email, event_type, subject):
        EmailDeliveryLog.objects.create(
            recipient_email=recipient_email,
            event_type=event_type,
            subject=subject,
            status=EmailDeliveryStatus.SUPPRESSED,
            error_message="Suppressed duplicate email within 60s deduplication window."
        )
        return False

    # Build context with centralized SITE_URL configuration
    site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
    ctx = {
        'user': recipient_user,
        'app_name': 'AetherSpace',
        'site_url': site_url,
        'year': timezone.now().year,
        **context
    }

    try:
        html_content = render_to_string(template_name, ctx)

        # Check if matching dedicated plain-text template exists
        text_template = template_name.replace('.html', '.txt')
        try:
            get_template(text_template)
            raw_text = render_to_string(text_template, ctx)
            text_content = html.unescape(raw_text).strip()
        except Exception:
            clean_html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html_content, flags=re.IGNORECASE)
            clean_html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', clean_html, flags=re.IGNORECASE)
            text_content = html.unescape(strip_tags(clean_html)).strip()
            text_content = re.sub(r'\n{3,}', '\n\n', text_content)

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'AetherSpace <no-reply@aetherspace.dev>')
        msg = EmailMultiAlternatives(subject, text_content, from_email, [recipient_email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        EmailDeliveryLog.objects.create(
            recipient_email=recipient_email,
            event_type=event_type,
            subject=subject,
            status=EmailDeliveryStatus.SENT
        )
        return True

    except Exception as e:
        logger.error(f"Email delivery failure for {recipient_email} ({subject}): {e}", exc_info=True)
        EmailDeliveryLog.objects.create(
            recipient_email=recipient_email,
            event_type=event_type,
            subject=subject,
            status=EmailDeliveryStatus.FAILED,
            error_message=str(e)
        )
        return False


def send_aether_email(recipient_email, subject, html_content, text_content=None, event_type='GENERAL', recipient_user=None):
    """
    Direct HTML/text email dispatch with preference and duplicate checking.
    """
    if not recipient_email:
        return False

    if recipient_user and not should_send_email_to_user(recipient_user, event_type):
        EmailDeliveryLog.objects.create(
            recipient_email=recipient_email,
            event_type=event_type,
            subject=subject,
            status=EmailDeliveryStatus.SUPPRESSED,
            error_message="Skipped by user notification preferences."
        )
        return False

    if is_duplicate_email(recipient_email, event_type, subject):
        EmailDeliveryLog.objects.create(
            recipient_email=recipient_email,
            event_type=event_type,
            subject=subject,
            status=EmailDeliveryStatus.SUPPRESSED,
            error_message="Suppressed duplicate within 60s."
        )
        return False

    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'AetherSpace <no-reply@aetherspace.dev>')
        if text_content:
            text = text_content
        else:
            clean_html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html_content, flags=re.IGNORECASE)
            clean_html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', clean_html, flags=re.IGNORECASE)
            text = html.unescape(strip_tags(clean_html)).strip()
            text = re.sub(r'\n{3,}', '\n\n', text)
        msg = EmailMultiAlternatives(subject, text, from_email, [recipient_email])
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)


        EmailDeliveryLog.objects.create(
            recipient_email=recipient_email,
            event_type=event_type,
            subject=subject,
            status=EmailDeliveryStatus.SENT
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send direct email to {recipient_email}: {e}")
        EmailDeliveryLog.objects.create(
            recipient_email=recipient_email,
            event_type=event_type,
            subject=subject,
            status=EmailDeliveryStatus.FAILED,
            error_message=str(e)
        )
        return False


# Specific Event Dispatchers

def send_task_assigned_email(task, assignee, actor=None):
    """Notify contributor that a task (#619347) was assigned to them."""
    if not assignee or (actor and actor.id == assignee.id):
        return False

    subject = f"[AetherSpace] Task Assigned: #{task.task_code} — {task.title}"
    context = {
        'task': task,
        'actor': actor,
        'action_url': f"/tasks/w/{task.workspace.slug}/t/{task.task_code}/",
    }
    return send_notification_email(
        recipient_user=assignee,
        event_type=EmailEventType.TASK_ASSIGNED,
        subject=subject,
        template_name='emails/task_assigned.html',
        context=context
    )


def send_meeting_scheduled_email(meeting, participant_user=None, recipient=None, actor=None):
    """Notify participant of a scheduled meeting."""
    target = participant_user or recipient
    if not target or (actor and actor.id == target.id):
        return False

    subject = f"[AetherSpace] Meeting Scheduled: {meeting.title}"
    context = {
        'meeting': meeting,
        'actor': actor,
        'action_url': f"/meetings/w/{meeting.workspace.slug}/room/{meeting.meeting_code}/",
    }
    return send_notification_email(
        recipient_user=target,
        event_type=EmailEventType.MEETING_SCHEDULED,
        subject=subject,
        template_name='emails/meeting_event.html',
        context=context
    )


def send_meeting_status_email(meeting, participant_user=None, recipient=None, status_change='UPDATED', actor=None):
    """Notify participant of a meeting update or cancellation."""
    target = participant_user or recipient
    if not target:
        return False

    status_str = "Cancelled" if str(status_change).upper() in ['CANCELLED', 'CANCEL'] else "Updated"
    subject = f"[AetherSpace] Meeting {status_str}: {meeting.title}"
    context = {
        'meeting': meeting,
        'status_str': status_str,
        'actor': actor,
        'action_url': f"/meetings/w/{meeting.workspace.slug}/",
    }
    event_type = EmailEventType.MEETING_CANCELLED if status_str == 'Cancelled' else EmailEventType.MEETING_UPDATED
    return send_notification_email(
        recipient_user=target,
        event_type=event_type,
        subject=subject,
        template_name='emails/meeting_event.html',
        context=context
    )


def send_account_approved_email(user, approved_by=None):
    """Notify contributor that their account was approved and can now sign in."""
    subject = f"[AetherSpace] Your Account has been Approved! (Contributor ID: {user.contributor_id})"
    context = {
        'user': user,
        'approved_by': approved_by,
        'action_url': "/auth/login/",
    }
    return send_notification_email(
        recipient_user=user,
        event_type=EmailEventType.ACCOUNT_APPROVED,
        subject=subject,
        template_name='emails/account_status.html',
        context=context
    )


def send_account_status_email(user, status=None, status_name=None, actor=None, reason=''):
    """Notify contributor of account status change (e.g. REJECTED or SUSPENDED)."""
    stat = status or status_name or 'UPDATED'
    subject = f"[AetherSpace] Account Status Update: {stat.title()}"
    context = {
        'user': user,
        'status': stat,
        'actor': actor,
        'reason': reason,
        'action_url': "/auth/login/",
    }
    return send_notification_email(
        recipient_user=user,
        event_type=f'ACCOUNT_{str(stat).upper()}',
        subject=subject,
        template_name='emails/account_status.html',
        context=context
    )


def send_workspace_invitation_email(invitation=None, recipient_email=None, workspace=None, invitation_url=None, role_name=None, actor=None):
    """Notify user of a workspace invitation."""
    email = recipient_email or (invitation.email if invitation else None)
    ws = workspace or (invitation.workspace if invitation else None)
    
    # Normalize url: if absolute URL is passed, extract relative path so site_url applies cleanly
    if invitation_url:
        url = invitation_url
        if url.startswith('http://') or url.startswith('https://'):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            url = parsed.path
            if parsed.query:
                url += f"?{parsed.query}"
    elif invitation:
        url = f"/workspaces/join/{invitation.token}/"
    else:
        url = "#"

    role = role_name or (invitation.get_role_display() if invitation else "Contributor")
    inviter = actor or (invitation.invited_by if invitation else None)

    if not email or not ws:
        return False

    subject = f"[AetherSpace] You have been invited to join '{ws.name}'"
    context = {
        'workspace': ws,
        'role_name': role,
        'actor': inviter,
        'action_url': url,
        'invitation': invitation or {
            'workspace': ws,
            'get_role_display': role,
            'role': role,
            'invited_by': inviter,
            'email': email,
        },
    }
    # For invitations, recipient is an email address; wrap in an object with email
    class TempRecipient:
        def __init__(self, email):
            self.email = email
            self.profile = None

    return send_notification_email(
        recipient_user=TempRecipient(email),
        event_type=EmailEventType.WORKSPACE_INVITE,
        subject=subject,
        template_name='emails/workspace_invite.html',
        context=context
    )


def send_bug_assigned_email(bug, assignee, actor=None):
    """Notify contributor that a defect (B-######) was assigned to them."""
    if not assignee or (actor and actor.id == assignee.id):
        return False

    subject = f"[AetherSpace] Defect Assigned: {bug.bug_code} — {bug.title}"
    context = {
        'bug': bug,
        'actor': actor,
        'action_url': f"/bugs/w/{bug.workspace.slug}/b/{bug.bug_code}/",
    }
    return send_notification_email(
        recipient_user=assignee,
        event_type=EmailEventType.BUG_ASSIGNED,
        subject=subject,
        template_name='emails/bug_assigned.html',
        context=context
    )


def send_password_reset_email(user, reset_url):
    """Send secure password reset link to user."""
    if not user or not user.email:
        return False

    subject = "[AetherSpace] Reset Your Account Password"
    context = {
        'user': user,
        'reset_url': reset_url,
    }
    return send_notification_email(
        recipient_user=user,
        event_type=EmailEventType.PASSWORD_RESET,
        subject=subject,
        template_name='emails/password_reset.html',
        context=context
    )


def send_email_verification_email(user, verify_url):
    """Send email verification link to newly registered user."""
    if not user or not user.email:
        return False

    subject = "[AetherSpace] Verify Your Email Address"
    context = {
        'user': user,
        'verify_url': verify_url,
    }
    return send_notification_email(
        recipient_user=user,
        event_type=EmailEventType.EMAIL_VERIFICATION,
        subject=subject,
        template_name='emails/verification.html',
        context=context
    )


def send_mention_email(user, actor, context_type, context_title, snippet, action_url):
    """Notify user that they were mentioned in a task or bug comment."""
    if not user or not user.email or (actor and actor.id == user.id):
        return False

    actor_name = actor.full_name or actor.email if actor else "A teammate"
    subject = f"[AetherSpace] {actor_name} mentioned you in {context_type}: {context_title}"
    context = {
        'user': user,
        'actor': actor,
        'context_type': context_type,
        'context_title': context_title,
        'snippet': snippet,
        'action_url': action_url,
    }
    return send_notification_email(
        recipient_user=user,
        event_type=EmailEventType.MENTION,
        subject=subject,
        template_name='emails/mention_notification.html',
        context=context
    )

