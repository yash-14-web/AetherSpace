from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing, name='landing'),
    
    # Global Navigation Shell destinations
    path('calendar/', views.calendar_view, name='calendar'),
    path('files/', views.files_view, name='files'),
    path('meetings/', views.meetings_view, name='meetings'),
    path('chat/', views.chat_view, name='chat'),
    path('time-tracking/', views.time_tracking_view, name='time_tracking'),
    path('notifications/', views.notifications_view, name='notifications'),
    path('profile/', views.profile_view, name='profile'),

    # Test error endpoints
    path('test/400/', views.error_400, name='test_400'),
    path('test/403/', views.error_403, name='test_403'),
    path('test/404/', views.error_404, name='test_404'),
    path('test/500/', views.error_500, name='test_500'),
]
