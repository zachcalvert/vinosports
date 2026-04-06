from channels.generic.websocket import AsyncWebsocketConsumer


class ActivityConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for World Cup activity feed."""

    async def connect(self):
        self.group_name = "wc_site_activity"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def activity_event(self, event):
        await self.send(text_data=event["html"])
