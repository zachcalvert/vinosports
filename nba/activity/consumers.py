import json
import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.db import close_old_connections
from django.template.loader import render_to_string

from vinosports.betting.models import UserBalance
from vinosports.rewards.models import RewardDistribution

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
                "nba_activity/partials/activity_toast_oob.html",
                {
                    "message": event.get("message", ""),
                    "url": event.get("url", ""),
                    "icon": event.get("icon", "lightning"),
                    "event_type": event.get("event_type", ""),
                },
            )
            self.send(text_data=html)
        except Exception:
            logger.exception("Error rendering activity_event")


class NotificationsConsumer(WebsocketConsumer):
    """Per-user WebSocket for bet settlement notifications, badges, etc."""

    def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            self.close()
            return

        self.group_name = f"user_notifications_{user.pk}"
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            async_to_sync(self.channel_layer.group_discard)(
                self.group_name, self.channel_name
            )

    def notification(self, event):
        self.send(text_data=event.get("html", ""))

    def balance_update(self, event):
        self.send(text_data=event.get("html", ""))

    def badge_notification(self, event):
        self.send(text_data=json.dumps({"type": "badge", "data": event}))

    def reward_notification(self, event):
        close_old_connections()
        distribution_id = event["distribution_id"]
        try:
            user = self.scope.get("user")
            distribution = (
                RewardDistribution.objects.filter(pk=distribution_id, user=user)
                .select_related("reward")
                .first()
            )
            if not distribution:
                return

            html = render_to_string(
                "nba_rewards/partials/reward_toast_oob.html",
                {"distribution": distribution, "user": user},
            )
            try:
                current_balance = UserBalance.objects.get(user=user).balance
                html += render_to_string(
                    "nba_website/components/balance_oob.html",
                    {"balance": current_balance, "user": user},
                )
            except UserBalance.DoesNotExist:
                pass
            self.send(text_data=html)
        except Exception:
            logger.exception(
                "Error rendering reward_notification for distribution %s",
                distribution_id,
            )
