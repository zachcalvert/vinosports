import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from activity.routing import websocket_urlpatterns as activity_ws
from matches.routing import websocket_urlpatterns as matches_ws

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(matches_ws + activity_ws)
        ),
    }
)
