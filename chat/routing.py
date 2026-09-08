from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/chat/c/<uuid:channel_id>/', consumers.ChatConsumer.as_asgi()),
    path('ws/chat/dm/<uuid:conversation_id>/', consumers.ChatConsumer.as_asgi()),
]
