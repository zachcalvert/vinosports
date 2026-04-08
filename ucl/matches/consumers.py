from channels.generic.websocket import AsyncWebsocketConsumer


class LiveUpdatesConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for live UCL score updates."""

    async def connect(self):
        self.scope_key = self.scope["url_route"]["kwargs"]["scope"]
        if self.scope_key == "dashboard":
            self.group_name = "ucl_live_scores"
        else:
            self.group_name = f"ucl_match_{self.scope_key}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def score_update(self, event):
        await self.send(text_data=event["html"])

    async def match_score_update(self, event):
        await self.send(text_data=event["html"])
