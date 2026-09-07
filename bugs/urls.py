from django.urls import path
from . import views

app_name = 'bugs'

urlpatterns = [
    # Global entry points
    path('', views.bugs_redirect_router, name='bugs_router'),
    path('my/', views.my_bugs_view, name='my_bugs'),

    # Workspace-scoped bug tracking
    path('w/<slug:slug>/', views.bug_list_view, name='bug_list'),
    path('w/<slug:slug>/dashboard/', views.bug_dashboard_view, name='bug_dashboard'),
    path('w/<slug:slug>/create/', views.bug_create_view, name='bug_create'),
    path('w/<slug:slug>/<str:bug_code>/', views.bug_detail_view, name='bug_detail'),
    path('w/<slug:slug>/<str:bug_code>/edit/', views.bug_edit_view, name='bug_edit'),
    path('w/<slug:slug>/<str:bug_code>/status/', views.bug_status_update_view, name='bug_status_update'),
    path('w/<slug:slug>/<str:bug_code>/activity/', views.bug_activity_view, name='bug_activity'),
    path('w/<slug:slug>/<str:bug_code>/delete/', views.bug_delete_view, name='bug_delete'),
    path('w/<slug:slug>/<str:bug_code>/comment/', views.bug_comment_add_view, name='bug_comment_add'),
    path('w/<slug:slug>/<str:bug_code>/comment/<uuid:comment_id>/delete/', views.bug_comment_delete_view, name='bug_comment_delete'),
]
