import logging
from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from betting.models import BetSlip, Parlay
from vinosports.rewards.models import RewardRule

logger = logging.getLogger(__name__)


def _evaluate_rules_for_user(user, stake):
    """Shared reward rule evaluation used by both single bet and parlay signals."""
    active_rules = RewardRule.objects.filter(is_active=True).select_related("reward")

    bet_count_rules = []
    stake_rules = []
    for rule in active_rules:
        if rule.rule_type == RewardRule.RuleType.BET_COUNT:
            bet_count_rules.append(rule)
        elif rule.rule_type == RewardRule.RuleType.STAKE_AMOUNT:
            stake_rules.append(rule)

    if bet_count_rules:
        # Count both single bets and parlays as "bets" for milestone rules
        total_bet_count = (
            BetSlip.objects.filter(user=user).count()
            + Parlay.objects.filter(user=user).count()
        )
        for rule in bet_count_rules:
            if total_bet_count == int(rule.threshold):
                rule.reward.distribute_to_users([user])

    stake_decimal = Decimal(str(stake))
    for rule in stake_rules:
        if stake_decimal >= rule.threshold:
            rule.reward.distribute_to_users([user])


@receiver(post_save, sender=BetSlip)
def check_reward_rules(sender, instance, created, **kwargs):
    """Evaluate active reward rules whenever a new single bet is placed."""
    if not created:
        return
    _evaluate_rules_for_user(instance.user, instance.stake)


@receiver(post_save, sender=Parlay)
def check_reward_rules_for_parlay(sender, instance, created, **kwargs):
    """Evaluate active reward rules whenever a new parlay is placed."""
    if not created:
        return
    _evaluate_rules_for_user(instance.user, instance.stake)
