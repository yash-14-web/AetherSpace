from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotFound, HttpResponseServerError


def landing(request):
    """Public landing page introducing AetherSpace."""
    return render(request, 'core/landing.html', {
        'title': 'AetherSpace — Next-Gen Agile Collaboration Platform',
    })


@login_required
def calendar_view(request):
    """Calendar & Agenda navigation destination - redirects to active workspace calendar."""
    return redirect('calendars:calendar_router')



@login_required
def files_view(request):
    """Files & Workspace Storage navigation destination - redirects to active workspace files."""
    return redirect('files:files_router')


@login_required
def meetings_view(request):
    """Meet Hub navigation destination - redirects to workspace meet hub."""
    return redirect('meetings:meet_router')


@login_required
def chat_view(request):
    """Team Chat navigation destination."""
    return render(request, 'components/placeholder.html', {
        'module_title': 'Team Chat & Channels',
        'phase_badge': 'Phase 5 — Collaboration',
        'module_icon': 'chat',
        'module_description': 'Real-time team messaging, topic channels, direct messages, and code snippet sharing.',
        'empty_heading': 'Collaboration & Channels',
        'empty_text': 'Channel threads, direct messages, asset pins, and WebSocket real-time messaging arrive in Phase 5.',
        'features': [
            'Topic channels (e.g. #general, #frontend, #bugs)',
            '1-to-1 encrypted direct messaging',
            'Markdown formatting & code block syntax highlighting',
            'Pinned workspace assets & shared file drawer',
        ],
    })


@login_required
def time_tracking_view(request):
    """Time Tracking navigation destination."""
    return render(request, 'components/placeholder.html', {
        'module_title': 'Time Tracking & Logs',
        'phase_badge': 'Phase 4 — Shell Rail',
        'module_icon': 'time',
        'module_description': 'Track sprint hours, task durations, and team workload efficiency across active workspaces.',
        'empty_heading': 'Workload & Sprint Hours',
        'empty_text': 'Live stopwatch timers, manual hour logs, and billable time export will accompany the task execution phase.',
        'features': [
            'Real-time task stopwatch timer',
            'Daily and weekly timesheet summaries',
            'Sprint hour burn-down analytics',
            'Exportable CSV timesheets for team leads',
        ],
    })


@login_required
def notifications_view(request):
    """Notification Center navigation destination."""
    return render(request, 'components/placeholder.html', {
        'module_title': 'Notifications Center',
        'phase_badge': 'Phase 9 — Notifications',
        'module_icon': 'notifications',
        'module_description': 'Centralized inbox for task assignments, bug updates, workspace invitations, and system alerts.',
        'empty_heading': 'All Notifications Caught Up',
        'empty_text': 'You have zero unread notifications. Real-time notification dispatch will arrive with Phase 9.',
        'features': [
            'Task & bug assignment mentions (@username)',
            'Workspace role update notifications',
            'Meeting reminder pings before start time',
            'Digest preferences & email alerts',
        ],
    })


@login_required
def profile_view(request):
    """User Profile & Account settings."""
    return render(request, 'components/placeholder.html', {
        'module_title': 'User Profile & Preferences',
        'phase_badge': 'Phase 9 — Accounts',
        'module_icon': 'profile',
        'module_description': 'Manage your personal profile, credentials, active workspace memberships, and display preferences.',
        'empty_heading': f"{request.user.full_name or request.user.email}",
        'empty_text': f"Account: {request.user.email} • Role: {request.user.get_role_display() if hasattr(request.user, 'get_role_display') else 'Member'}. Full profile editing and avatar customization will arrive in Phase 9.",
        'features': [
            'Profile name, title, and avatar editor',
            'Password change & multi-factor verification',
            'Active workspace memberships manager',
            'Theme & accessibility display preferences',
        ],
    })


def error_400(request, exception=None):
    """400 Bad Request error page."""
    return render(request, 'errors/400.html', {
        'status_code': 400,
        'title': 'Bad Request',
        'message': 'Invalid Request — The request could not be processed due to invalid parameters.',
    }, status=400)


def error_403(request, exception=None):
    """403 Forbidden / Access Restricted error page with Request Access workflow."""
    return render(request, 'errors/403.html', {
        'status_code': 403,
        'title': 'Permission Denied',
        'message': 'Access Restricted — You do not have the required permissions to view this workspace or resource.',
        'show_request_access': True,
    }, status=403)


def error_404(request, exception=None):
    """404 Not Found error page."""
    return render(request, 'errors/404.html', {
        'status_code': 404,
        'title': 'Page Not Found',
        'message': 'Page Not Found — The task, bug, or workspace you are looking for does not exist or has been moved.',
    }, status=404)


def error_500(request):
    """500 Internal Server Error page."""
    return render(request, 'errors/500.html', {
        'status_code': 500,
        'title': 'Internal Server Error',
        'message': 'Internal Server Error — Something went wrong on our end. Our engineering team has been notified.',
    }, status=500)
