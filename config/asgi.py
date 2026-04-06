import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path

from epl.activity.routing import websocket_urlpatterns as epl_activity_ws
from epl.matches.routing import websocket_urlpatterns as epl_matches_ws
from epl.rewards.routing import websocket_urlpatterns as epl_rewards_ws
from hub.consumers import AdminDashboardConsumer
from nba.activity.routing import websocket_urlpatterns as nba_activity_ws
from nba.games.routing import websocket_urlpatterns as nba_games_ws
from nfl.activity.routing import websocket_urlpatterns as nfl_activity_ws
from nfl.games.routing import websocket_urlpatterns as nfl_games_ws
from worldcup.activity.routing import (
    websocket_urlpatterns as wc_activity_ws,
)
from worldcup.matches.routing import (
    websocket_urlpatterns as wc_matches_ws,
)
from worldcup.rewards.routing import (
    websocket_urlpatterns as wc_rewards_ws,
)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(
                [
                    path(
                        "epl/",
                        URLRouter(epl_matches_ws + epl_activity_ws + epl_rewards_ws),
                    ),
                    path("nba/", URLRouter(nba_games_ws + nba_activity_ws)),
                    path("nfl/", URLRouter(nfl_games_ws + nfl_activity_ws)),
                    path(
                        "worldcup/",
                        URLRouter(wc_matches_ws + wc_activity_ws + wc_rewards_ws),
                    ),
                    path("ws/admin/", AdminDashboardConsumer.as_asgi()),
                ]
            )
        ),
    }
)
