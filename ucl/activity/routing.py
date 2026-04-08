from django.urls import re_path

from .consumers import ActivityConsumer

websocket_urlpatterns = [
    re_path(r"ws/activity/$", ActivityConsumer.as_asgi()),
]
