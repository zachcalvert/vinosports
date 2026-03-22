from channels.generic.websocket import WebsocketConsumer


class ActivityConsumer(WebsocketConsumer):
    """WebSocket consumer for the site-wide activity feed."""

    def connect(self):
        self.group_name = "site_activity"

        from asgiref.sync import async_to_sync

        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        from asgiref.sync import async_to_sync

        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )

    def activity_event(self, event):
        self.send(text_data=event.get("html", ""))
