from django.urls import path
from . import views

app_name = 'admin_panel'

urlpatterns = [
    # 1. Dashboard / System Overview (Screens 04, 67)
    path('', views.admin_dashboard, name='dashboard'),
    path('system/', views.system_overview, name='system_overview'),

    # 2. User Management & Details (Screens 59, 60)
    path('users/', views.user_list, name='user_list'),
    path('users/<uuid:user_id>/', views.user_details, name='user_details'),
    path('users/<uuid:user_id>/status/', views.toggle_user_status, name='toggle_user_status'),
    path('users/<uuid:user_id>/role/', views.update_user_role, name='update_user_role'),

    # 3. Roles & Permissions (Screen 61)
    path('roles/', views.roles_permissions, name='roles_permissions'),

    # 4. Invitations (Screen 62)
    path('invitations/', views.invitations_list, name='invitations_list'),
    path('invitations/<uuid:invite_id>/resend/', views.resend_invitation, name='resend_invitation'),
    path('invitations/<uuid:invite_id>/revoke/', views.revoke_invitation, name='revoke_invitation'),

    # 5. Workspace Management (Screen 63)
    path('workspaces/', views.workspace_list, name='workspace_list'),
    path('workspaces/<slug:slug>/', views.workspace_details, name='workspace_details'),
    path('workspaces/<slug:slug>/status/', views.toggle_workspace_status, name='toggle_workspace_status'),
    path('workspaces/<slug:slug>/quota/', views.update_workspace_quota, name='update_workspace_quota'),

    # 6. Workspace Requests (Screen 64)
    path('requests/', views.workspace_requests, name='workspace_requests'),
    path('requests/<uuid:request_id>/decision/', views.decide_workspace_request, name='decide_workspace_request'),

    # 7. Member Management (Screen 65)
    path('members/', views.member_management, name='member_management'),

    # 8. Audit Logs (Screen 66)
    path('audit-logs/', views.audit_logs, name='audit_logs'),

    # 9. Integrations (Screen 68)
    path('integrations/', views.integrations, name='integrations'),

    # 10. Storage & Files — Real Sync (Screen 69)
    path('storage/', views.storage_files, name='storage_files'),
    path('storage/sync/', views.storage_sync_audit, name='storage_sync_audit'),
    path('storage/purge/<uuid:file_id>/', views.purge_file, name='purge_file'),

    # 11. Security (Screen 70)
    path('security/', views.security_overview, name='security_overview'),

    # 12. Backup & Restore (Screen 71)
    path('backup/', views.backup_restore, name='backup_restore'),
    path('backup/export/', views.export_data, name='export_data'),

    # 13. Activity Monitor (Screen 72)
    path('activity/', views.activity_monitor, name='activity_monitor'),

    # 14. Performance (Screen 73)
    path('performance/', views.performance_overview, name='performance_overview'),

    # 15. Alerts (Screen 74)
    path('alerts/', views.alerts_list, name='alerts_list'),
    path('alerts/<uuid:alert_id>/resolve/', views.resolve_alert, name='resolve_alert'),

    # Search-First People Search API
    path('api/people-search/', views.api_people_search, name='api_people_search'),
]
