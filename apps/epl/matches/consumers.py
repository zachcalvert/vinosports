from channels.generic.websocket import WebsocketConsumer


class LiveUpdatesConsumer(WebsocketConsumer):
    """WebSocket consumer for live match score updates.

    Clients connect via ws/live/<scope>/ where scope is either
    "dashboard" (all matches) or a match id_hash (single match).
    """

    def connect(self):
        self.scope_param = self.scope["url_route"]["kwargs"]["scope"]

        if self.scope_param == "dashboard":
            self.group_name = "live_scores"
        else:
            self.group_name = f"match_{self.scope_param}"

        from channels.layers import get_channel_layer
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

    def score_update(self, event):
        """Handle score_update events broadcast from Celery tasks."""
        self.send(text_data=event.get("html", ""))

    def match_score_update(self, event):
        """Handle match detail page score updates."""
        self.send(text_data=event.get("html", ""))
