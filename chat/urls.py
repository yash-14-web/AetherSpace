from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    # Top-level entry
    path('', views.chat_router, name='chat_router'),

    # Workspace Chat Dashboard & Views
    path('w/<slug:slug>/', views.chat_home_view, name='chat_home'),
    path('w/<slug:slug>/c/create/', views.channel_create_view, name='channel_create'),
    path('w/<slug:slug>/c/<slug:channel_slug>/', views.channel_view, name='channel_view'),
    path('w/<slug:slug>/c/<slug:channel_slug>/details/', views.channel_details_view, name='channel_details'),
    path('w/<slug:slug>/dm/<uuid:user_id>/', views.direct_message_view, name='direct_message'),
    path('w/<slug:slug>/pinned/', views.pinned_assets_view, name='pinned_assets'),
    path('w/<slug:slug>/files/', views.shared_files_view, name='shared_files'),

    # API / AJAX Endpoints
    path('w/<slug:slug>/api/pin/<uuid:message_id>/', views.api_toggle_pin, name='api_toggle_pin'),
    path('w/<slug:slug>/api/react/<uuid:message_id>/', views.api_toggle_reaction, name='api_toggle_reaction'),
    path('w/<slug:slug>/api/messages/c/<slug:channel_slug>/', views.api_channel_messages, name='api_channel_messages'),
    path('w/<slug:slug>/api/messages/dm/<uuid:user_id>/', views.api_direct_messages, name='api_direct_messages'),
    path('w/<slug:slug>/api/users/search/', views.api_search_users, name='api_search_users'),
]
