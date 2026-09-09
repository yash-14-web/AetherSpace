from django.urls import path
from . import views

app_name = 'meetings'

urlpatterns = [
    # Global entry router
    path('', views.meet_router, name='meet_router'),

    # Workspace scoped views
    path('w/<slug:slug>/', views.meet_hub_view, name='meet_hub'),
    path('w/<slug:slug>/start/', views.meeting_start_view, name='meeting_start'),
    path('w/<slug:slug>/chat-call/', views.meeting_chat_call_view, name='meeting_chat_call'),
    path('w/<slug:slug>/chat-call/<str:target_type>/<str:target_id>/<str:call_mode>/', views.meeting_chat_call_view, name='meeting_chat_call_routed'),
    path('w/<slug:slug>/join/', views.meeting_join_view, name='meeting_join'),
    path('w/<slug:slug>/schedule/', views.meeting_schedule_view, name='meeting_schedule'),
    path('w/<slug:slug>/history/', views.meeting_history_view, name='meeting_history'),
    path('w/<slug:slug>/room/<str:meeting_code>/', views.meeting_room_view, name='meeting_room'),
    path('w/<slug:slug>/<str:meeting_code>/', views.meeting_detail_view, name='meeting_detail'),
    path('w/<slug:slug>/<str:meeting_code>/edit/', views.meeting_edit_view, name='meeting_edit'),
    path('w/<slug:slug>/<str:meeting_code>/cancel/', views.meeting_cancel_view, name='meeting_cancel'),

    # Real-time room session APIs
    path('w/<slug:slug>/<str:meeting_code>/api/ping/', views.meeting_ping_api, name='meeting_ping_api'),
    path('w/<slug:slug>/<str:meeting_code>/api/end/', views.meeting_end_api, name='meeting_end_api'),
]
