from django.urls import path, re_path
from . import consumers

websocket_urlpatterns = [
    # Global call signaling & ringtone across all authenticated pages
    path('ws/calls/global/', consumers.GlobalCallConsumer.as_asgi()),
    # Match workspace slug and meeting code (e.g. ws/meetings/alpha-project/meet-k7xp-2m9q/)
    re_path(r'^ws/meetings/(?P<slug>[-\w]+)/(?P<meeting_code>[-\w]+)/$', consumers.MeetingSignalingConsumer.as_asgi()),
]

