import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from epl.activity.routing import websocket_urlpatterns as epl_activity_ws  # noqa: E402
from epl.matches.routing import websocket_urlpatterns as epl_matches_ws  # noqa: E402
from epl.rewards.routing import websocket_urlpatterns as epl_rewards_ws  # noqa: E402
from nba.activity.routing import websocket_urlpatterns as nba_activity_ws  # noqa: E402
from nba.games.routing import websocket_urlpatterns as nba_games_ws  # noqa: E402
from nfl.activity.routing import websocket_urlpatterns as nfl_activity_ws  # noqa: E402
from nfl.games.routing import websocket_urlpatterns as nfl_games_ws  # noqa: E402

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
                ]
            )
        ),
    }
)
