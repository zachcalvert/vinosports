import json
import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

ADMIN_DASHBOARD_GROUP = "admin_dashboard"


class AdminDashboardConsumer(WebsocketConsumer):
    """Push real-time update notifications to the admin dashboard."""

    def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not user.is_superuser:
            self.close()
            return

        self.accept()
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_add)(ADMIN_DASHBOARD_GROUP, self.channel_name)

    def disconnect(self, close_code):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_discard)(
            ADMIN_DASHBOARD_GROUP, self.channel_name
        )

    def dashboard_update(self, event):
        """Forward dashboard update events to the WebSocket client."""
        self.send(
            text_data=json.dumps(
                {
                    "type": event["update_type"],
                }
            )
        )


def notify_admin_dashboard(update_type):
    """Send a lightweight notification to the admin dashboard group.

    Call after creating a bet, comment, or user signup.
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            ADMIN_DASHBOARD_GROUP,
            {
                "type": "dashboard_update",
                "update_type": update_type,
            },
        )
    except Exception:
        logger.warning("Failed to notify admin dashboard", exc_info=True)
