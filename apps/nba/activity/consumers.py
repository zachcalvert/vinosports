import json

from channels.generic.websocket import WebsocketConsumer


class ActivityConsumer(WebsocketConsumer):
    """WebSocket consumer for the site-wide activity feed."""

    def connect(self):
        self.group_name = "site_activity"

        from asgiref.sync import async_to_sync

        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        from asgiref.sync import async_to_sync

        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )

    def activity_event(self, event):
        """Handle activity events from Celery tasks.

        Accepts either pre-rendered HTML or structured data.
        """
        html = event.get("html")
        if html:
            self.send(text_data=html)
            return

        # Build a simple toast from structured data
        message = event.get("message", "")
        icon = event.get("icon", "lightning")

        toast_html = (
            f'<div id="activity-toasts" hx-swap-oob="afterbegin">'
            f'<div class="activity-toast animate-slide-in-left" role="status">'
            f'<i class="ph-duotone ph-{icon} text-accent text-lg flex-shrink-0"></i>'
            f'<p class="activity-toast-message">{message}</p>'
            f"</div></div>"
        )
        self.send(text_data=toast_html)


class NotificationsConsumer(WebsocketConsumer):
    """Per-user WebSocket for bet settlement notifications, badges, etc."""

    def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            self.close()
            return

        self.group_name = f"user_notifications_{user.pk}"

        from asgiref.sync import async_to_sync

        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            from asgiref.sync import async_to_sync

            async_to_sync(self.channel_layer.group_discard)(
                self.group_name, self.channel_name
            )

    def notification(self, event):
        self.send(text_data=event.get("html", ""))

    def balance_update(self, event):
        self.send(text_data=event.get("html", ""))

    def badge_notification(self, event):
        self.send(text_data=json.dumps({"type": "badge", "data": event}))
