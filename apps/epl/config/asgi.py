import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf import settings
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from activity.routing import websocket_urlpatterns as activity_ws  # noqa: E402
from matches.routing import websocket_urlpatterns as matches_ws  # noqa: E402
from rewards.routing import websocket_urlpatterns as rewards_ws  # noqa: E402


class ScriptNameStripMiddleware:
    """Normalize WebSocket paths for Channels URL routing.

    FORCE_SCRIPT_NAME causes Daphne to set root_path on the ASGI scope,
    which can result in the prefix being prepended to the path. Nginx
    already strips the /epl/ or /nba/ prefix, so we strip it again here
    if present. We also strip the leading slash so that paths like
    '/ws/live/dashboard/' become 'ws/live/dashboard/' — matching the
    route patterns which don't include a leading slash.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            prefix = getattr(settings, "FORCE_SCRIPT_NAME", "") or ""
            path = scope.get("path", "")
            if prefix and path.startswith(prefix):
                path = path[len(prefix) :]
            path = path.lstrip("/")
            scope = dict(scope, path=path)
        return await self.inner(scope, receive, send)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": ScriptNameStripMiddleware(
            AuthMiddlewareStack(URLRouter(matches_ws + activity_ws + rewards_ws))
        ),
    }
)
