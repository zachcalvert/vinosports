import logging
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from vinosports.betting.balance import log_transaction
from vinosports.betting.models import BalanceTransaction, UserBalance
from vinosports.core.models import BaseModel

logger = logging.getLogger(__name__)


class Reward(BaseModel):
    name = models.CharField(_("name"), max_length=200)
    amount = models.DecimalField(_("amount"), max_digits=10, decimal_places=2)
    description = models.TextField(_("description"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_rewards",
        verbose_name=_("created by"),
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.amount} credits)"

    def distribute_to_users(self, users):
        """Credit this reward to the given users atomically.

        Creates RewardDistribution records and increments each user's balance.
        Skips users who have already received this reward.
        Returns the list of newly created distributions.
        """
        new_distributions = []

        with transaction.atomic():
            existing = set(
                self.distributions.filter(user__in=users).values_list(
                    "user_id", flat=True
                )
            )
            for user in users:
                if user.pk in existing:
                    continue

                dist = RewardDistribution.objects.create(reward=self, user=user)
                new_distributions.append(dist)

                balance, _ = UserBalance.objects.select_for_update().get_or_create(
                    user=user, defaults={"balance": Decimal("100000.00")}
                )
                log_transaction(
                    balance,
                    self.amount,
                    BalanceTransaction.Type.REWARD,
                    f"Reward: {self.name}",
                )

        if new_distributions:
            transaction.on_commit(lambda: _broadcast_rewards(new_distributions))

        return new_distributions


class RewardDistribution(BaseModel):
    reward = models.ForeignKey(
        Reward,
        on_delete=models.CASCADE,
        related_name="distributions",
        verbose_name=_("reward"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reward_distributions",
        verbose_name=_("user"),
    )
    seen = models.BooleanField(_("seen"), default=False)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("reward", "user")]

    def __str__(self):
        return f"{self.reward.name} → {self.user}"


class RewardRule(BaseModel):
    class RuleType(models.TextChoices):
        BET_COUNT = "BET_COUNT", _("Bet count milestone")
        STAKE_AMOUNT = "STAKE_AMOUNT", _("Stake amount threshold")

    reward = models.OneToOneField(
        Reward,
        on_delete=models.CASCADE,
        related_name="rule",
        verbose_name=_("reward"),
    )
    rule_type = models.CharField(
        _("rule type"),
        max_length=20,
        choices=RuleType.choices,
    )
    threshold = models.DecimalField(
        _("threshold"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Bet count (e.g. 10) or stake amount (e.g. 100.00)"),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["rule_type", "threshold"]
        unique_together = [("rule_type", "threshold")]

    def clean(self):
        if self.rule_type == self.RuleType.BET_COUNT and self.threshold is not None:
            threshold = Decimal(str(self.threshold))
            if threshold != threshold.to_integral_value():
                raise ValidationError(
                    {"threshold": _("Bet count milestones must be whole numbers.")}
                )

    def __str__(self):
        if self.rule_type == self.RuleType.BET_COUNT:
            return f"Bet #{int(self.threshold)} → {self.reward.name}"
        return f"Stake ≥ {self.threshold} → {self.reward.name}"


def _broadcast_rewards(distributions):
    """Send a WebSocket notification to each reward recipient."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    send = async_to_sync(channel_layer.group_send)

    for dist in distributions:
        group = f"user_notifications_{dist.user_id}"
        try:
            send(
                group,
                {
                    "type": "reward_notification",
                    "distribution_id": dist.pk,
                },
            )
        except Exception:
            logger.exception(
                "Failed to broadcast reward notification for distribution %s",
                dist.pk,
            )
