from django.urls import re_path

from .consumers import ActivityConsumer, NotificationsConsumer

websocket_urlpatterns = [
    re_path(r"ws/activity/$", ActivityConsumer.as_asgi()),
    re_path(r"ws/notifications/$", NotificationsConsumer.as_asgi()),
]
