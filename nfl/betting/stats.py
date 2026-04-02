"""
Stats recording for NFL bet results.

Updates UserStats atomically after each bet or parlay settles,
then checks and awards badges.
"""

import logging
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from nfl.betting.badges import BetContext, check_and_award_badges
from vinosports.betting.models import UserStats

logger = logging.getLogger(__name__)

MAX_SINGLE_STAKE = Decimal("100000.00")


def record_bet_result(
    user,
    *,
    won: bool,
    stake: Decimal,
    payout: Decimal,
    odds=None,
    is_parlay=False,
    leg_count=0,
):
    newly_earned = []

    with transaction.atomic():
        stats, _ = UserStats.objects.get_or_create(user=user)
        stats = UserStats.objects.select_for_update().get(pk=stats.pk)

        stats.total_bets += 1
        stats.total_staked += stake
        stats.total_payout += payout

        if won:
            stats.total_wins += 1
            stats.current_streak = max(stats.current_streak, 0) + 1
            stats.best_streak = max(stats.best_streak, stats.current_streak)
        else:
            stats.total_losses += 1
            stats.current_streak = min(stats.current_streak, 0) - 1

        stats.net_profit = stats.total_payout - stats.total_staked

        stats.save(
            update_fields=[
                "total_bets",
                "total_wins",
                "total_losses",
                "total_staked",
                "total_payout",
                "net_profit",
                "current_streak",
                "best_streak",
            ]
        )

        ctx = BetContext(
            won=won,
            odds=odds if odds is not None else Decimal("0"),
            is_parlay=is_parlay,
            leg_count=leg_count,
            stake=stake,
            max_stake=MAX_SINGLE_STAKE,
        )
        newly_earned = check_and_award_badges(user, stats, ctx)

    logger.info(
        "record_bet_result: user=%s won=%s streak=%d best=%d profit=%s badges=%s",
        user.pk,
        won,
        stats.current_streak,
        stats.best_streak,
        stats.net_profit,
        [ub.badge.slug for ub in newly_earned],
    )

    if newly_earned:
        transaction.on_commit(lambda: _broadcast_badges(user, newly_earned))


def _broadcast_badges(user, user_badges):
    channel_layer = get_channel_layer()
    send = async_to_sync(channel_layer.group_send)
    group = f"user_notifications_{user.pk}"

    for ub in user_badges:
        try:
            send(
                group,
                {
                    "type": "badge_notification",
                    "user_badge_id": ub.pk,
                },
            )
        except Exception:
            logger.exception(
                "Failed to broadcast badge notification for user_badge %s", ub.pk
            )
