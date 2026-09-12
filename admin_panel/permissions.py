from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse


def get_client_ip(request):
    """Extract client IP address from request headers safely."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip or '127.0.0.1'


def platform_admin_required(view_func):
    """
    Decorator for views that require Platform Administrator authority.
    - If user is not authenticated: redirects to login.
    - If user is authenticated but not a platform administrator (Managers / Contributors):
      raises PermissionDenied (HTTP 403 Forbidden).
    - Never relies solely on UI element visibility.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = reverse('accounts:login')
            return redirect(f"{login_url}?next={request.path}")

        # Check platform admin authority: role == ADMIN or superuser
        is_platform_admin = (
            getattr(request.user, 'is_admin_role', False) or
            getattr(request.user, 'role', '') == 'ADMIN' or
            request.user.is_superuser
        )

        if not is_platform_admin:
            raise PermissionDenied(
                "Access Restricted — Platform Administrator privileges are required to access the Admin Panel."
            )

        return view_func(request, *args, **kwargs)

    return _wrapped_view
