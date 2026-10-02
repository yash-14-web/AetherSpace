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

    # Sprint Planning endpoints
    path('w/<slug:slug>/sprints/', views.sprint_planning_view, name='sprint_planning'),
    path('w/<slug:slug>/sprints/create/', views.sprint_create_view, name='sprint_create'),
    path('w/<slug:slug>/sprints/<uuid:sprint_id>/edit/', views.sprint_edit_view, name='sprint_edit'),
    path('w/<slug:slug>/sprints/<uuid:sprint_id>/action/', views.sprint_action_view, name='sprint_action'),
    path('w/<slug:slug>/sprints/move-task/', views.sprint_move_task_view, name='sprint_move_task'),
    path('w/<slug:slug>/sprints/quick-create-task/', views.sprint_quick_create_task_view, name='sprint_quick_create_task'),

    path('w/<slug:slug>/<str:task_code>/', views.task_detail_view, name='task_detail'),
    path('w/<slug:slug>/<str:task_code>/edit/', views.task_edit_view, name='task_edit'),
    path('w/<slug:slug>/<str:task_code>/status/', views.task_status_update_view, name='task_status_update'),
    path('w/<slug:slug>/<str:task_code>/activity/', views.task_activity_view, name='task_activity'),
    path('w/<slug:slug>/<str:task_code>/delete/', views.task_delete_view, name='task_delete'),
    path('w/<slug:slug>/<str:task_code>/comment/', views.task_comment_add_view, name='task_comment_add'),
    path('w/<slug:slug>/<str:task_code>/comment/<uuid:comment_id>/edit/', views.task_comment_edit_view, name='task_comment_edit'),
    path('w/<slug:slug>/<str:task_code>/comment/<uuid:comment_id>/delete/', views.task_comment_delete_view, name='task_comment_delete'),

    # Bug Linking endpoints
    path('w/<slug:slug>/<str:task_code>/bugs/attach/', views.task_bug_attach_view, name='task_bug_attach'),
    path('w/<slug:slug>/<str:task_code>/bugs/<str:bug_code>/detach/', views.task_bug_detach_view, name='task_bug_detach'),

    # Subtask endpoints
    path('w/<slug:slug>/<str:task_code>/subtasks/create/', views.subtask_create_view, name='subtask_create'),
    path('w/<slug:slug>/<str:task_code>/subtasks/<uuid:subtask_id>/toggle/', views.subtask_toggle_view, name='subtask_toggle'),
    path('w/<slug:slug>/<str:task_code>/subtasks/<uuid:subtask_id>/delete/', views.subtask_delete_view, name='subtask_delete'),

    # Attachment endpoints
    path('w/<slug:slug>/<str:task_code>/attachment/upload/', views.task_attachment_upload_view, name='task_attachment_upload'),
    path('w/<slug:slug>/<str:task_code>/attachment/<uuid:attachment_id>/delete/', views.task_attachment_delete_view, name='task_attachment_delete'),

    # Code Review endpoints
    path('w/<slug:slug>/<str:task_code>/code-review/create/', views.code_review_create_view, name='code_review_create'),
    path('w/<slug:slug>/code-review/<uuid:review_id>/status/', views.code_review_status_update_view, name='code_review_status_update'),

    # Markdown preview endpoint
    path('w/<slug:slug>/api/markdown-preview/', views.markdown_preview_view, name='markdown_preview'),
]

