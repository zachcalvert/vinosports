# ruff: noqa
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialize Django ASGI application early so the app registry is populated
# before any routing modules import models.
from django.core.asgi import get_asgi_application  # ruff: disable

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # ruff: disable
from channels.routing import ProtocolTypeRouter, URLRouter  # ruff: disable
from django.urls import path  # ruff: disable

from epl.activity.routing import (
    websocket_urlpatterns as epl_activity_ws,  # ruff: disable
)
from epl.matches.routing import websocket_urlpatterns as epl_matches_ws  # ruff: disable
from epl.rewards.routing import websocket_urlpatterns as epl_rewards_ws  # ruff: disable
from hub.consumers import AdminDashboardConsumer  # ruff: disable
from nba.activity.routing import (
    websocket_urlpatterns as nba_activity_ws,  # ruff: disable
)
from nba.games.routing import websocket_urlpatterns as nba_games_ws  # ruff: disable
from nfl.activity.routing import (
    websocket_urlpatterns as nfl_activity_ws,  # ruff: disable
)
from nfl.games.routing import websocket_urlpatterns as nfl_games_ws  # ruff: disable
from worldcup.activity.routing import (
    websocket_urlpatterns as wc_activity_ws,  # ruff: disable
)
from worldcup.matches.routing import (
    websocket_urlpatterns as wc_matches_ws,  # ruff: disable
)
from worldcup.rewards.routing import (
    websocket_urlpatterns as wc_rewards_ws,  # ruff: disable
)

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
