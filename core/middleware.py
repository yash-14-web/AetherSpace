import logging
import secrets
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, Http404
from django.shortcuts import render

logger = logging.getLogger('aetherspace.errors')


class RateLimitExceeded(Exception):
    """Raised when an operation or IP exceeds configured rate limit threshold."""
    def __init__(self, message="Too Many Requests", retry_after=60):
        super().__init__(message)
        self.retry_after = retry_after


class RequestTimeoutException(Exception):
    """Raised when an external service or long-running query exceeds client timeout."""
    def __init__(self, message="Request Timed Out"):
        super().__init__(message)


class ServiceUnavailableException(Exception):
    """Raised when an essential external provider or service dependency is offline."""
    def __init__(self, message="Service Unavailable"):
        super().__init__(message)


class AetherSpaceGlobalErrorMiddleware:
    """
    Global error handling middleware for AetherSpace.
    - Standardizes AJAX / API error responses into structured JSON.
    - Handles custom application exceptions (RateLimitExceeded, RequestTimeoutException, ServiceUnavailableException).
    - Generates production-safe correlation Error IDs (ERR-500-XXXXXXXX) without leaking internals.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Ensure AJAX / API requests always receive JSON on error codes (>= 400)
        # instead of unstyled raw HTML snippets injected into client components.
        if response.status_code >= 400 and self.is_ajax_or_api(request):
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' in content_type or not content_type or 'text/plain' in content_type:
                error_messages = {
                    400: 'Invalid Request — The request could not be processed due to invalid parameters.',
                    401: 'Authentication Required — Please sign in to continue.',
                    403: 'Access Restricted — You do not have the required permissions for this resource.',
                    404: 'Page Not Found — The requested resource does not exist or has been moved.',
                    408: 'Request Timed Out — The request took too long to complete. Please try again.',
                    429: "Too Many Requests — You've made too many requests in a short period.",
                    500: 'Internal Server Error — Something went wrong on our end.',
                    503: 'Service Unavailable — AetherSpace is temporarily unable to process your request.',
                }
                msg = error_messages.get(response.status_code, 'An error occurred while processing the request.')
                
                # Check if view provided custom error string in response body
                if response.content:
                    try:
                        raw_body = response.content.decode('utf-8').strip()
                        if raw_body and len(raw_body) < 300 and '<html' not in raw_body.lower():
                            msg = raw_body
                    except Exception:
                        pass

                json_data = {
                    'error': msg,
                    'status_code': response.status_code,
                    'path': request.path,
                }
                if response.status_code == 429 and hasattr(response, 'retry_after'):
                    json_data['retry_after'] = response.retry_after
                
                json_resp = JsonResponse(json_data, status=response.status_code)
                if response.status_code == 429:
                    json_resp['Retry-After'] = str(getattr(response, 'retry_after', 60))
                return json_resp

        # Intercept plain-text / default HttpResponseForbidden on browser requests
        # and render the designed AetherSpace 403 page while preserving the permission reason.
        if response.status_code == 403 and not self.is_ajax_or_api(request):
            content_type = response.headers.get('Content-Type', '')
            # If not already an AetherSpace rendered HTML page
            if 'text/plain' in content_type or (response.content and b'<!DOCTYPE html>' not in response.content and b'<html' not in response.content.lower()):
                plain_msg = None
                try:
                    raw_text = response.content.decode('utf-8', errors='ignore').strip()
                    if raw_text:
                        plain_msg = raw_text
                except Exception:
                    pass
                from core.views import error_403
                return error_403(request, message=plain_msg)

        return response

    def process_exception(self, request, exception):
        """Handle custom and unexpected exceptions gracefully."""
        if isinstance(exception, RateLimitExceeded):
            if self.is_ajax_or_api(request):
                resp = JsonResponse({
                    'error': str(exception),
                    'status_code': 429,
                    'retry_after': exception.retry_after,
                }, status=429)
                resp['Retry-After'] = str(exception.retry_after)
                return resp
            from core.views import error_429
            return error_429(request, exception=exception)

        if isinstance(exception, RequestTimeoutException):
            if self.is_ajax_or_api(request):
                return JsonResponse({
                    'error': str(exception),
                    'status_code': 408,
                }, status=408)
            from core.views import error_408
            return error_408(request, exception=exception)

        if isinstance(exception, ServiceUnavailableException):
            if self.is_ajax_or_api(request):
                return JsonResponse({
                    'error': str(exception),
                    'status_code': 503,
                }, status=503)
            from core.views import error_503
            return error_503(request, exception=exception)

        if isinstance(exception, PermissionDenied):
            ex_msg = str(exception).strip()
            if self.is_ajax_or_api(request):
                return JsonResponse({
                    'error': ex_msg or 'Access Restricted — You do not have the required permissions.',
                    'status_code': 403,
                }, status=403)
            from core.views import error_403
            return error_403(request, exception=exception, message=ex_msg if ex_msg else None)

        if isinstance(exception, Http404):
            if self.is_ajax_or_api(request):
                return JsonResponse({
                    'error': 'Page Not Found — The requested resource does not exist.',
                    'status_code': 404,
                }, status=404)
            from core.views import error_404
            return error_404(request, exception=exception)

        # Unhandled server exceptions
        logger.exception("Unhandled server exception on %s %s: %s",
                         request.method, request.path, str(exception))

        if self.is_ajax_or_api(request):
            err_msg = str(exception) if settings.DEBUG else 'Internal Server Error — Something went wrong on our end.'
            error_id = secrets.token_hex(4).upper()
            return JsonResponse({
                'status': 'error',
                'error': err_msg,
                'message': err_msg,
                'status_code': 500,
                'error_id': f'ERR-500-{error_id}',
            }, status=500)

        if not settings.DEBUG:
            error_id = secrets.token_hex(4).upper()
            from core.views import error_500
            return error_500(request, error_id=error_id)

        return None

    @staticmethod
    def is_ajax_or_api(request):
        """Determines whether a request expects a JSON response."""
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return True
        if request.path.startswith('/api/') or '/api/' in request.path:
            return True
        accept = request.headers.get('accept', '')
        if 'application/json' in accept and 'text/html' not in accept:
            return True
        return False


class ModuleMaintenanceMiddleware:
    """
    Global Server-Side Module Maintenance Enforcement Middleware.
    Inspects requests to operational modules and blocks unauthorized access, direct URL bypasses,
    and action invocations when a module is marked UNDER MAINTENANCE or COMING SOON.
    """

    # Modules and their specific action paths that are blocked during maintenance
    MAINTENANCE_BLOCKED_SUBPATHS = {
        'meetings': [
            '/start/',
            '/join/',
            '/room/',
            '/chat-call/',
            '/api/',
        ],
    }

    # Modules where the entire URL prefix is restricted during maintenance
    STRICT_PREFIX_MODULES = {
        # Can be expanded for other modules when total blackout is required
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Always bypass static assets, media, favicon, and cloud healthchecks
        path = request.path
        if (path.startswith('/static/') or path.startswith('/media/') or 
            path == '/favicon.ico' or path.startswith('/healthz')):
            return self.get_response(request)

        # 2. Always bypass admin panel and core auth/management views
        if path.startswith('/admin/') or path.startswith('/admin-panel/') or path.startswith('/accounts/'):
            return self.get_response(request)

        # 3. Check module maintenance rules
        from core.models import ModuleStatus
        module_statuses = ModuleStatus.get_all_statuses()

        # Check Meetings Module
        meetings_status = module_statuses.get('meetings')
        if meetings_status and not meetings_status.is_available:
            if path.startswith('/meetings/'):
                # Block real-time action paths: starting, joining room, calls, APIs
                is_blocked_action = any(sub in path for sub in self.MAINTENANCE_BLOCKED_SUBPATHS['meetings'])
                # If meeting room direct URL: /meetings/w/<slug>/<code/
                # Note: overview is /meetings/w/<slug>/ and history is /meetings/w/<slug>/history/
                is_room_url = '/room/' in path
                
                if is_blocked_action or is_room_url:
                    return self.render_maintenance_response(request, meetings_status)

        return self.get_response(request)

    def render_maintenance_response(self, request, module_status):
        """Render standard 503 response in JSON or HTML matching AetherSpace design."""
        is_ajax = AetherSpaceGlobalErrorMiddleware.is_ajax_or_api(request)
        if is_ajax:
            return JsonResponse({
                'error': module_status.effective_message,
                'module': module_status.name,
                'status': module_status.status,
                'status_code': 503,
            }, status=503)

        workspace_slug = None
        parts = [p for p in request.path.strip('/').split('/') if p]
        if len(parts) >= 3 and parts[1] == 'w':
            workspace_slug = parts[2]

        return render(request, 'core/module_maintenance.html', {
            'module_status': module_status,
            'workspace_slug': workspace_slug,
        }, status=503)


class UserActivityMiddleware:
    """
    Middleware that records user activity heartbeat in cache.
    Keeps user availability status active ('available' / 'away' / etc.)
    and marks users 'offline' when no requests are received for > 5 minutes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                from django.core.cache import cache
                from django.utils import timezone
                cache.set(f'user_last_seen_{request.user.id}', timezone.now().timestamp(), timeout=300)
            except Exception:
                pass
        return self.get_response(request)


