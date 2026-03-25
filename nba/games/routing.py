from django.urls import re_path

from nba.games.consumers import LiveUpdatesConsumer

websocket_urlpatterns = [
    re_path(r"ws/live/(?P<scope>\w+)/$", LiveUpdatesConsumer.as_asgi()),
]
