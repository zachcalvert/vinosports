from channels.generic.websocket import WebsocketConsumer


class LiveUpdatesConsumer(WebsocketConsumer):
    """WebSocket consumer for live game score updates."""

    def connect(self):
        self.scope_param = self.scope["url_route"]["kwargs"]["scope"]

        if self.scope_param == "dashboard":
            self.group_name = "live_scores"
        else:
            self.group_name = f"game_{self.scope_param}"

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
        self.send(text_data=event.get("html", ""))

    def game_score_update(self, event):
        self.send(text_data=event.get("html", ""))
