from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # WebSocket URL for real-time tracking and chat for a specific service request
    # The UUID format is assumed based on the models.py provided.
    re_path(
        r'ws/service/(?P<request_id>[0-9a-f-]+)/$', 
        consumers.ServiceRequestConsumer.as_asgi()
    ),
]
