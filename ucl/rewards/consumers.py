import json

from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):
    """Per-user notification consumer for UCL rewards/badges."""

    async def connect(self):
        user = self.scope.get("user")
        if not user or user.is_anonymous:
            await self.close()
            return
        self.group_name = f"user_notifications_{user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def inbox_notification(self, event):
        await self.send(text_data=json.dumps({"unread_count": event["unread_count"]}))

    async def badge_notification(self, event):
        await self.send(text_data=event["html"])

    async def challenge_notification(self, event):
        await self.send(text_data=event["html"])

    async def reward_notification(self, event):
        await self.send(text_data=event["html"])
