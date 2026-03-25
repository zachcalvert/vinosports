"""
Stats recording for bet results.

Updates UserStats atomically after each bet or parlay settles.
"""

import logging
from decimal import Decimal

from django.db import transaction

from vinosports.betting.models import UserStats

logger = logging.getLogger(__name__)


def record_bet_result(user, *, won: bool, stake: Decimal, payout: Decimal):
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

    logger.info(
        "record_bet_result: user=%s won=%s streak=%d profit=%s",
        user.pk,
        won,
        stats.current_streak,
        stats.net_profit,
    )
