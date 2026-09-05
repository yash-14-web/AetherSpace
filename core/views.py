from django.shortcuts import render
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotFound, HttpResponseServerError


def landing(request):
    """Public landing page introducing AetherSpace."""
    return render(request, 'core/landing.html', {
        'title': 'AetherSpace — Next-Gen Agile Collaboration Platform',
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
