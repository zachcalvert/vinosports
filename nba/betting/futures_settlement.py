"""
Futures market settlement for NBA.

settle_futures_market(market_pk, winner_team_pk) settles all bets in a market.
void_futures_market(market_pk) cancels a market and refunds all pending bets.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from nba.betting.balance import log_transaction
from nba.betting.models import FuturesBet, FuturesMarket, FuturesOutcome
from nba.betting.stats import record_bet_result
from vinosports.betting.models import (
    BetStatus,
    FuturesMarketStatus,
)

logger = logging.getLogger(__name__)


def _calculate_payout_american(stake: Decimal, odds: int) -> Decimal:
    """Calculate payout from American odds."""
    if odds > 0:
        return (stake * Decimal(odds) / 100 + stake).quantize(Decimal("0.01"))
    else:
        return (stake * Decimal(100) / Decimal(abs(odds)) + stake).quantize(
            Decimal("0.01")
        )


def settle_futures_market(market_pk: int, winner_team_pk: int) -> dict:
    """
    Settle a futures market by declaring a winning team.

    Returns dict with settlement stats.
    """
    with transaction.atomic():
        market = FuturesMarket.objects.select_for_update().get(pk=market_pk)
        if market.status != FuturesMarketStatus.OPEN:
            raise ValueError(f"Market {market.name} is {market.status}, not OPEN")

        # Mark the winning outcome
        winning_outcome = FuturesOutcome.objects.get(
            market=market, team_id=winner_team_pk
        )
        winning_outcome.is_winner = True
        winning_outcome.save(update_fields=["is_winner"])

        # Update market status
        market.status = FuturesMarketStatus.SETTLED
        market.settled_at = timezone.now()
        market.save(update_fields=["status", "settled_at"])

    # Settle bets outside the market lock
    pending_bets = FuturesBet.objects.filter(
        outcome__market=market, status=BetStatus.PENDING
    ).select_related("outcome", "user")

    won_count = 0
    lost_count = 0

    for bet in pending_bets:
        with transaction.atomic():
            if bet.outcome_id == winning_outcome.pk:
                payout = _calculate_payout_american(bet.stake, bet.odds_at_placement)
                bet.status = BetStatus.WON
                bet.payout = payout
                bet.save(update_fields=["status", "payout"])

                log_transaction(
                    bet.user,
                    payout,
                    "FUTURES_WIN",
                    f"Futures bet won: {market.name}",
                )
                won_count += 1
            else:
                bet.status = BetStatus.LOST
                bet.payout = Decimal("0")
                bet.save(update_fields=["status", "payout"])
                lost_count += 1

        record_bet_result(
            bet.user,
            won=(bet.status == BetStatus.WON),
            stake=bet.stake,
            payout=bet.payout or Decimal("0"),
            odds=bet.odds_at_placement,
        )

    logger.info(
        "settle_futures_market: %s settled — %d won, %d lost",
        market.name,
        won_count,
        lost_count,
    )
    return {"market": market.name, "won": won_count, "lost": lost_count}


def void_futures_market(market_pk: int) -> dict:
    """Cancel a futures market and refund all pending bets."""
    with transaction.atomic():
        market = FuturesMarket.objects.select_for_update().get(pk=market_pk)
        if market.status not in (
            FuturesMarketStatus.OPEN,
            FuturesMarketStatus.SUSPENDED,
        ):
            raise ValueError(f"Market {market.name} is {market.status}, cannot void")

        market.status = FuturesMarketStatus.CANCELLED
        market.save(update_fields=["status"])

    pending_bets = FuturesBet.objects.filter(
        outcome__market=market, status=BetStatus.PENDING
    ).select_related("user")

    refunded = 0
    for bet in pending_bets:
        with transaction.atomic():
            bet.status = BetStatus.VOID
            bet.payout = bet.stake
            bet.save(update_fields=["status", "payout"])

            log_transaction(
                bet.user,
                bet.stake,
                "FUTURES_VOID",
                f"Futures bet voided: {market.name}",
            )
            refunded += 1

    logger.info(
        "void_futures_market: %s cancelled — %d refunded", market.name, refunded
    )
    return {"market": market.name, "refunded": refunded}
