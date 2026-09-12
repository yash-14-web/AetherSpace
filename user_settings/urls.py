from django.urls import path
from . import views

app_name = 'user_settings'

urlpatterns = [
    path('', views.index, name='index'),
    path('account/', views.account_settings, name='account'),
    path('profile/', views.profile_settings, name='profile'),
    path('appearance/', views.appearance_settings, name='appearance'),
    path('notifications/', views.notification_settings, name='notifications'),
    path('security/', views.security_settings, name='security'),
    path('workspaces/', views.workspaces_settings, name='workspaces'),
    path('workspaces/<slug:slug>/', views.workspace_detail_settings, name='workspace_detail'),
    path('integrations/', views.integrations_settings, name='integrations'),
    path('api/theme/', views.api_update_theme, name='api_update_theme'),
]
