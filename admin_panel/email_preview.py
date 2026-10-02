"""
AetherSpace Phase B — Email Design System Preview & QA Service
Provides safe, isolated sample datasets for testing and previewing all AetherSpace email templates.
"""
from django.utils import timezone
from django.conf import settings
from django.template.loader import render_to_string
import html


class MockUser:
    def __init__(self, full_name, email, contributor_id='CR-102948'):
        self.full_name = full_name
        self.email = email
        self.contributor_id = contributor_id
        self.id = 9999
        self.first_name = full_name.split()[0] if full_name else 'User'

    def __str__(self):
        return self.full_name or self.email


class MockWorkspace:
    def __init__(self, name, slug):
        self.name = name
        self.slug = slug

    def __str__(self):
        return self.name


class MockTask:
    def __init__(self, task_code, title, priority, status, due_date, description, workspace):
        self.task_code = task_code
        self.title = title
        self.priority = priority
        self.status = status
        self.due_date = due_date
        self.description = description
        self.workspace = workspace

    def get_priority_display(self):
        return str(self.priority).title() if self.priority else "Medium"

    def get_status_display(self):
        return str(self.status).replace('_', ' ').title() if self.status else "To Do"


class MockBug:
    def __init__(self, bug_code, title, severity, priority, module, description, workspace):
        self.bug_code = bug_code
        self.title = title
        self.severity = severity
        self.priority = priority
        self.module = module
        self.description = description
        self.workspace = workspace

    def get_severity_display(self):
        return str(self.severity).title() if self.severity else "Medium"

    def get_priority_display(self):
        return str(self.priority).title() if self.priority else "Medium"


class MockMeeting:
    def __init__(self, title, meeting_code, scheduled_start, duration_minutes, room_code, workspace, host):
        self.title = title
        self.meeting_code = meeting_code
        self.scheduled_start = scheduled_start
        self.duration_minutes = duration_minutes
        self.room_code = room_code
        self.workspace = workspace
        self.host = host


def get_preview_catalog():
    """Returns metadata for all previewable AetherSpace emails."""
    site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
    now = timezone.now()

    return {
        'verification': {
            'title': 'Account Verification',
            'category': 'Authentication & Security',
            'html_template': 'emails/verification.html',
            'txt_template': 'emails/verification.txt',
            'description': 'Sent during new user registration with a secure 24-hour verification token.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com', 'CR-482019'),
                'verify_url': f'{site_url}/auth/verify/sample-verification-token-2026/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'password_reset': {
            'title': 'Password Reset Request',
            'category': 'Authentication & Security',
            'html_template': 'emails/password_reset.html',
            'txt_template': 'emails/password_reset.txt',
            'description': 'Sent when a user initiates a password reset. Token is never exposed in text.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com', 'CR-482019'),
                'reset_url': f'{site_url}/auth/password-reset/confirm/MQ/sample-secure-token-99/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'workspace_invite': {
            'title': 'Workspace Invitation',
            'category': 'Workspaces & Access',
            'html_template': 'emails/workspace_invite.html',
            'txt_template': 'emails/workspace_invite.txt',
            'description': 'Sent to invite new or existing contributors to a specific workspace.',
            'context': {
                'workspace': MockWorkspace('AetherSpace Core', 'aetherspace-core'),
                'role_name': 'Contributor',
                'actor': MockUser('Sarah Connor', 'sarah.connor@example.com'),
                'action_url': f'{site_url}/workspaces/join/sample-invite-token-aether/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'account_approved': {
            'title': 'Account Status: Approved',
            'category': 'Accounts & Governance',
            'html_template': 'emails/account_status.html',
            'txt_template': 'emails/account_status.txt',
            'description': 'Sent when a root administrator approves a newly registered contributor profile.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com', 'CR-482019'),
                'status': 'APPROVED',
                'approved_by': MockUser('Sarah Connor', 'sarah.connor@example.com'),
                'action_url': f'{site_url}/auth/login/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'account_rejected': {
            'title': 'Account Status: Rejected / Suspended',
            'category': 'Accounts & Governance',
            'html_template': 'emails/account_status.html',
            'txt_template': 'emails/account_status.txt',
            'description': 'Sent when an account is rejected or suspended with administrative reasoning.',
            'context': {
                'user': MockUser('Jordan Lee', 'jordan.lee@example.com', 'CR-992102'),
                'status': 'REJECTED',
                'reason': 'Corporate identity verification could not be matched with verified registry.',
                'action_url': f'{site_url}/auth/login/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'task_assigned': {
            'title': 'Task Assignment',
            'category': 'Agile Project Management',
            'html_template': 'emails/task_assigned.html',
            'txt_template': 'emails/task_assigned.txt',
            'description': 'Sent when an agile task (#619347) is assigned to a workspace member.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com', 'CR-482019'),
                'task': MockTask(
                    task_code='619347',
                    title='Implement dashboard filtering & date range selectors',
                    priority='HIGH',
                    status='IN_PROGRESS',
                    due_date=now.date(),
                    description='Add multi-select status filtering, search term debouncing, and custom date range picker to the team dashboard.',
                    workspace=MockWorkspace('AetherSpace Core', 'aetherspace-core')
                ),
                'actor': MockUser('Sarah Connor', 'sarah.connor@example.com'),
                'action_url': f'{site_url}/tasks/w/aetherspace-core/t/619347/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'bug_assigned': {
            'title': 'Bug / Defect Assignment',
            'category': 'Defect Tracking',
            'html_template': 'emails/bug_assigned.html',
            'txt_template': 'emails/bug_assigned.txt',
            'description': 'Sent when an engineering defect (B-882316) is assigned to a contributor.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com', 'CR-482019'),
                'bug': MockBug(
                    bug_code='B-882316',
                    title='Calendar invite rendering issue on Safari mobile',
                    severity='HIGH',
                    priority='CRITICAL',
                    module='calendar',
                    description='Dates with UTC offsets greater than +05:30 wrap into two lines and break table alignment.',
                    workspace=MockWorkspace('AetherSpace Core', 'aetherspace-core')
                ),
                'actor': MockUser('Marcus Wright', 'marcus.wright@example.com'),
                'action_url': f'{site_url}/bugs/w/aetherspace-core/b/B-882316/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'meeting_event': {
            'title': 'Meeting / Event Notification',
            'category': 'Collaboration & Meets',
            'html_template': 'emails/meeting_event.html',
            'txt_template': 'emails/meeting_event.txt',
            'description': 'Sent when a video call or conference session is scheduled or updated.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com', 'CR-482019'),
                'meeting': MockMeeting(
                    title='Sprint Planning & Architecture Sync',
                    meeting_code='MEET-74921',
                    scheduled_start=now,
                    duration_minutes=45,
                    room_code='ROOM-SYNC-99',
                    workspace=MockWorkspace('AetherSpace Core', 'aetherspace-core'),
                    host=MockUser('Sarah Connor', 'sarah.connor@example.com')
                ),
                'status_str': 'Scheduled',
                'actor': MockUser('Sarah Connor', 'sarah.connor@example.com'),
                'action_url': f'{site_url}/meetings/w/aetherspace-core/room/MEET-74921/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'mention_notification': {
            'title': 'Mention Notification',
            'category': 'Team Communication',
            'html_template': 'emails/mention_notification.html',
            'txt_template': 'emails/mention_notification.txt',
            'description': 'Sent when a contributor is @mentioned in comments or chat threads.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com'),
                'actor': MockUser('Elena Rostova', 'elena.rostova@example.com'),
                'context_type': 'Task',
                'context_title': 'Task #619347 — Implement dashboard filtering',
                'snippet': '@Alex Rivera Can you please verify the responsive breakpoint table styles before we merge to main?',
                'action_url': f'{site_url}/tasks/w/aetherspace-core/t/619347/#comment-14',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'access_approved': {
            'title': 'Access Request Approved',
            'category': 'Security & RBAC',
            'html_template': 'emails/general_notification.html',
            'txt_template': 'emails/general_notification.txt',
            'description': 'Sent when an administrator approves a temporary or elevated workspace access request.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com', 'CR-482019'),
                'title': 'Access Request Approved: Create Task',
                'body': "Your access request for 'Create Task' in AetherSpace Core has been approved. Temporary elevation active for 2 hours.",
                'workspace': MockWorkspace('AetherSpace Core', 'aetherspace-core'),
                'action_url': f'{site_url}/workspaces/w/aetherspace-core/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'access_rejected': {
            'title': 'Access Request Rejected',
            'category': 'Security & RBAC',
            'html_template': 'emails/general_notification.html',
            'txt_template': 'emails/general_notification.txt',
            'description': 'Sent when an access request is rejected with administrative reasoning.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com', 'CR-482019'),
                'title': 'Access Request Rejected: Delete Workspace',
                'body': "Your request for 'Delete Workspace' in AetherSpace Core was reviewed and rejected. Reason: Only Platform Administrators may decommission core workspaces.",
                'reason': 'Only Platform Administrators may decommission core workspaces.',
                'workspace': MockWorkspace('AetherSpace Core', 'aetherspace-core'),
                'action_url': f'{site_url}/workspaces/w/aetherspace-core/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
        'general_notification': {
            'title': 'General Notification',
            'category': 'Platform Broadcast',
            'html_template': 'emails/general_notification.html',
            'txt_template': 'emails/general_notification.txt',
            'description': 'Sent for system announcements, status updates, or custom broadcasts.',
            'context': {
                'user': MockUser('Alex Rivera', 'alex.rivera@example.com', 'CR-482019'),
                'title': 'Scheduled Platform Maintenance Window',
                'body': 'AetherSpace will undergo brief database index maintenance on Sunday between 02:00 and 02:30 UTC. Read-only mode will be active during this period.',
                'action_url': f'{site_url}/dashboard/',
                'site_url': site_url,
                'app_name': 'AetherSpace',
                'year': now.year,
            }
        },
    }


def render_preview(template_key, as_text=False):
    """Renders the HTML or Text representation of an email preview item."""
    catalog = get_preview_catalog()
    if template_key not in catalog:
        return None

    item = catalog[template_key]
    template_path = item['txt_template'] if as_text else item['html_template']
    raw_content = render_to_string(template_path, item['context'])
    if as_text:
        return html.unescape(raw_content).strip()
    return raw_content
