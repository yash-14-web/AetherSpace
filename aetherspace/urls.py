"""
AetherSpace URL Configuration
"""
from django.contrib import admin
from django.urls import path, include

from django.views.generic import RedirectView
from admin_panel import views as admin_panel_views

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('admin-panel/', include('admin_panel.urls')),
    path('admin/requests/<uuid:request_id>/decision/', admin_panel_views.decide_workspace_request),
    path('admin/', RedirectView.as_view(url='/admin-panel/', permanent=False)),
    path('admin/<path:subpath>', RedirectView.as_view(url='/admin-panel/%(subpath)s', permanent=False)),
    path('auth/', include('accounts.urls')),
    path('accounts/<path:subpath>', RedirectView.as_view(url='/auth/%(subpath)s', permanent=False)),
    path('workspaces/', include('workspaces.urls')),
    path('tasks/', include('tasks.urls')),
    path('bugs/', include('bugs.urls')),
    path('chat/', include('chat.urls')),
    path('meetings/', include('meetings.urls')),
    path('calendar/', include('calendars.urls')),
    path('calendars/<path:subpath>', RedirectView.as_view(url='/calendar/%(subpath)s', permanent=False)),
    path('calendars/', RedirectView.as_view(url='/calendar/', permanent=False)),
    path('files/', include('files.urls')),
    path('notifications/', include('notifications.urls')),
    path('settings/', include('user_settings.urls')),
    path('timetracking/', include('timetracking.urls')),
    path('dashboard/', RedirectView.as_view(url='/workspaces/dashboard/', permanent=False)),
    path('', include('core.urls')),
]

from django.conf import settings
from django.views.static import serve
from django.urls import re_path

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

# Custom Error Handlers per docs/08_ERROR_HANDLERS.md
handler400 = 'core.views.error_400'
handler403 = 'core.views.error_403'
handler404 = 'core.views.error_404'
handler500 = 'core.views.error_500'

