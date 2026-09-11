"""
AetherSpace URL Configuration
"""
from django.contrib import admin
from django.urls import path, include

from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
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
    path('dashboard/', RedirectView.as_view(url='/workspaces/dashboard/', permanent=False)),
    path('', include('core.urls')),
]

# Custom Error Handlers per docs/08_ERROR_HANDLERS.md
handler400 = 'core.views.error_400'
handler403 = 'core.views.error_403'
handler404 = 'core.views.error_404'
handler500 = 'core.views.error_500'
