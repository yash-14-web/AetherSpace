from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    # Global entry points
    path('', views.tasks_redirect_router, name='tasks_router'),
    path('my/', views.my_tasks_view, name='my_tasks'),

    # Workspace-scoped task management
    path('w/<slug:slug>/', views.task_list_view, name='task_list'),
    path('w/<slug:slug>/board/', views.task_board_view, name='task_board'),
    path('w/<slug:slug>/create/', views.task_create_view, name='task_create'),
    path('w/<slug:slug>/<str:task_code>/', views.task_detail_view, name='task_detail'),
    path('w/<slug:slug>/<str:task_code>/edit/', views.task_edit_view, name='task_edit'),
    path('w/<slug:slug>/<str:task_code>/status/', views.task_status_update_view, name='task_status_update'),
    path('w/<slug:slug>/<str:task_code>/activity/', views.task_activity_view, name='task_activity'),
    path('w/<slug:slug>/<str:task_code>/delete/', views.task_delete_view, name='task_delete'),
]
