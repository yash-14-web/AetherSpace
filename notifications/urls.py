from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notifications_router, name='notifications_router'),
    path('w/<slug:slug>/', views.workspace_notifications, name='workspace_notifications'),
    path('mark-read/<uuid:notification_id>/', views.mark_notification_read_view, name='mark_read'),
    path('mark-unread/<uuid:notification_id>/', views.mark_notification_unread_view, name='mark_unread'),
    path('mark-all-read/', views.mark_all_notifications_read_view, name='mark_all_read'),
    path('delete/<uuid:notification_id>/', views.delete_notification_view, name='delete'),
    path('api/unread/', views.api_unread_notifications, name='api_unread'),
]
