from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('about/', views.about_view, name='about'),
    
    # Global Navigation Shell destinations
    path('calendar/', views.calendar_view, name='calendar'),
    path('files/', views.files_view, name='files'),
    path('meetings/', views.meetings_view, name='meetings'),
    path('chat/', views.chat_view, name='chat'),
    path('time-tracking/', views.time_tracking_view, name='time_tracking'),
    path('notifications/', views.notifications_view, name='notifications'),
    path('profile/', views.profile_view, name='profile'),
    path('api/search/', views.global_search_api, name='global_search_api'),
    path('api/markdown-preview/', views.api_markdown_preview, name='markdown_preview'),

    # Test error endpoints
    path('test/400/', views.error_400, name='test_400'),
    path('test/401/', views.error_401, name='test_401'),
    path('test/403/', views.error_403, name='test_403'),
    path('test/404/', views.error_404, name='test_404'),
    path('test/408/', views.error_408, name='test_408'),
    path('test/429/', views.error_429, name='test_429'),
    path('test/500/', views.error_500, name='test_500'),
    path('test/503/', views.error_503, name='test_503'),
    path('test/network/', views.error_network, name='test_network'),
    path('test/errors-showcase/', views.errors_showcase_view, name='errors_showcase'),
]
