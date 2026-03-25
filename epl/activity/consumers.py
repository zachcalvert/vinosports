import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class ActivityConsumer(WebsocketConsumer):
    """WebSocket consumer for the site-wide activity feed."""

    def connect(self):
        self.group_name = "site_activity"
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )

    def activity_event(self, event):
        try:
            html = render_to_string(
                "epl_activity/partials/activity_toast_oob.html",
                {
                    "message": event.get("message", ""),
                    "url": event.get("url", ""),
                    "icon": event.get("icon", "info"),
                    "event_type": event.get("event_type", ""),
                },
            )
            self.send(text_data=html)
        except Exception:
            logger.exception("Error rendering activity_event")
