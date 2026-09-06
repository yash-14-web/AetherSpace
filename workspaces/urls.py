from django.urls import path
from . import views

app_name = 'workspaces'

urlpatterns = [
    path('', views.dashboard_router, name='dashboard_router'),
    path('dashboard/', views.dashboard_router, name='dashboard'),
    path('master/', views.master_dashboard, name='master_dashboard'),
    path('create/', views.create_workspace, name='create'),
    path('join/<str:token>/', views.accept_invitation, name='accept_invitation'),
    path('w/<slug:slug>/', views.workspace_dashboard, name='workspace_dashboard'),
    path('w/<slug:slug>/team/', views.workspace_team, name='team'),
    path('w/<slug:slug>/team/invite/', views.invite_member, name='invite_member'),
    path('w/<slug:slug>/team/members/<uuid:member_id>/role/', views.update_member_role, name='update_member_role'),
    path('w/<slug:slug>/team/members/<uuid:member_id>/remove/', views.remove_member, name='remove_member'),
    path('w/<slug:slug>/settings/', views.workspace_settings, name='settings'),
    path('w/<slug:slug>/project/', views.workspace_project_details, name='project_details'),
    path('w/<slug:slug>/chat/', views.workspace_chat, name='workspace_chat'),
    path('w/<slug:slug>/request-access/', views.request_access, name='request_access'),
]
