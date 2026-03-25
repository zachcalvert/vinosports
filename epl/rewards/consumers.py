import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from channels.layers import get_channel_layer
from django.db import close_old_connections
from django.template.loader import render_to_string

from vinosports.betting.models import UserBadge, UserBalance
from vinosports.challenges.models import UserChallenge
from vinosports.rewards.models import RewardDistribution

logger = logging.getLogger(__name__)


class NotificationConsumer(WebsocketConsumer):
    """Per-user WebSocket consumer for real-time notifications."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_name = None

    def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            self.close()
            return

        self.group_name = f"user_notifications_{user.pk}"
        self.accept()
        self._join_group(self.group_name)

    def disconnect(self, close_code):
        if self.group_name:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_discard)(
                self.group_name, self.channel_name
            )
            self.group_name = None

    def _join_group(self, group_name):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_add)(group_name, self.channel_name)

    def badge_notification(self, event):
        close_old_connections()
        user_badge_id = event["user_badge_id"]
        try:
            user = self.scope.get("user")
            user_badge = (
                UserBadge.objects.filter(pk=user_badge_id, user=user)
                .select_related("badge")
                .first()
            )
            if not user_badge:
                return

            html = render_to_string(
                "epl_betting/partials/badge_toast_oob.html",
                {"user_badge": user_badge},
            )
            self.send(text_data=html)
        except Exception:
            logger.exception(
                "Error rendering badge_notification for user_badge %s",
                user_badge_id,
            )

    def challenge_notification(self, event):
        close_old_connections()
        user_challenge_id = event["user_challenge_id"]
        try:
            user = self.scope.get("user")
            user_challenge = (
                UserChallenge.objects.filter(pk=user_challenge_id, user=user)
                .select_related("challenge__template")
                .first()
            )
            if not user_challenge:
                return

            html = render_to_string(
                "epl_challenges/partials/challenge_toast_oob.html",
                {"user_challenge": user_challenge, "user": user},
            )
            try:
                current_balance = UserBalance.objects.get(user=user).balance
                html += render_to_string(
                    "epl_website/components/balance_oob.html",
                    {"balance": current_balance, "user": user},
                )
            except UserBalance.DoesNotExist:
                pass
            self.send(text_data=html)
        except Exception:
            logger.exception(
                "Error rendering challenge_notification for user_challenge %s",
                user_challenge_id,
            )

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
                "epl_rewards/partials/reward_toast_oob.html",
                {"distribution": distribution, "user": user},
            )
            try:
                current_balance = UserBalance.objects.get(user=user).balance
                html += render_to_string(
                    "epl_website/components/balance_oob.html",
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
