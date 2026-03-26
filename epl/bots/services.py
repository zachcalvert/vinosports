"""Bot services — bet placement, odds helpers, and balance top-ups.

These mirror the atomic patterns in betting/views.py but without the HTTP layer.
"""

import logging
import random
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Min

from epl.betting.models import BetSlip, Parlay, ParlayLeg
from epl.matches.models import Match, Odds
from vinosports.betting.balance import log_transaction
from vinosports.betting.models import (
    Bailout,
    BalanceTransaction,
    Bankruptcy,
    BetStatus,
    UserBalance,
)

logger = logging.getLogger(__name__)

SELECTION_TO_ODDS_FIELD = {
    "HOME_WIN": "home_win",
    "DRAW": "draw",
    "AWAY_WIN": "away_win",
}


def get_available_matches_for_bot(bot_user):
    """Return bettable matches the bot hasn't already placed a pending bet on."""
    already_bet = BetSlip.objects.filter(user=bot_user, status="PENDING").values_list(
        "match_id", flat=True
    )

    already_in_parlay = ParlayLeg.objects.filter(
        parlay__user=bot_user, parlay__status="PENDING"
    ).values_list("match_id", flat=True)

    excluded = set(already_bet) | set(already_in_parlay)

    qs = Match.objects.filter(
        status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
    ).select_related("home_team", "away_team")

    if excluded:
        qs = qs.exclude(pk__in=excluded)

    return qs


def get_best_odds_map(match_ids):
    """Return {match_id: {"home_win": D, "draw": D, "away_win": D}}.

    Uses the same Min() aggregate pattern as the odds board views.
    """
    rows = (
        Odds.objects.filter(match_id__in=match_ids)
        .values("match_id")
        .annotate(
            home_win=Min("home_win"),
            draw=Min("draw"),
            away_win=Min("away_win"),
        )
    )
    return {
        row["match_id"]: {
            "home_win": row["home_win"],
            "draw": row["draw"],
            "away_win": row["away_win"],
        }
        for row in rows
    }


def get_full_odds_map(match_ids):
    """Return {match_id: [{"bookmaker": str, "home_win": D, ...}, ...]}.

    Used by ValueHunter to compute per-bookmaker spreads.
    """
    result = {}
    for odds in Odds.objects.filter(match_id__in=match_ids).values(
        "match_id", "bookmaker", "home_win", "draw", "away_win"
    ):
        result.setdefault(odds["match_id"], []).append(odds)
    return result


def place_bot_bet(user, match_id, selection, stake):
    """Place a single bet for a bot user. Returns BetSlip or None."""
    odds_field = SELECTION_TO_ODDS_FIELD.get(selection)
    if not odds_field:
        logger.warning("Invalid selection %s for bot %s", selection, user.email)
        return None

    try:
        with transaction.atomic():
            match = Match.objects.get(pk=match_id)
            if match.status not in (Match.Status.SCHEDULED, Match.Status.TIMED):
                return None

            best_odds = (
                Odds.objects.filter(match=match)
                .aggregate(best=Min(odds_field))
                .get("best")
            )
            if not best_odds:
                return None

            balance = UserBalance.objects.select_for_update().get(user=user)
            if balance.balance < stake:
                return None

            match_label = (
                f"{match.home_team.short_name or match.home_team.name}"
                f" vs {match.away_team.short_name or match.away_team.name}"
            )
            log_transaction(
                balance,
                -stake,
                BalanceTransaction.Type.BET_PLACEMENT,
                f"Bet on {match_label}",
            )

            bet = BetSlip.objects.create(
                user=user,
                match=match,
                selection=selection,
                odds_at_placement=best_odds,
                stake=stake,
            )
            logger.info(
                "Bot %s placed bet: %s on %s @ %s, stake=%s",
                user.display_name,
                selection,
                match,
                best_odds,
                stake,
            )
            return bet

    except (Match.DoesNotExist, UserBalance.DoesNotExist):
        return None


def place_bot_parlay(user, legs_data, stake):
    """Place a parlay for a bot user. Returns Parlay or None.

    legs_data: [{"match_id": int, "selection": str}, ...]
    """
    if len(legs_data) < 2 or len(legs_data) > 10:
        return None

    try:
        with transaction.atomic():
            match_ids = [lg["match_id"] for lg in legs_data]
            matches_by_id = {
                m.pk: m
                for m in Match.objects.filter(pk__in=match_ids).select_related(
                    "home_team", "away_team"
                )
            }

            leg_info = []
            combined_odds = Decimal("1.00")

            for entry in legs_data:
                match = matches_by_id.get(entry["match_id"])
                if not match or match.status not in (
                    Match.Status.SCHEDULED,
                    Match.Status.TIMED,
                ):
                    return None

                odds_field = SELECTION_TO_ODDS_FIELD.get(entry["selection"])
                if not odds_field:
                    logger.warning(
                        "Bot parlay leg has invalid selection %r", entry["selection"]
                    )
                    return None
                best = (
                    Odds.objects.filter(match=match)
                    .aggregate(best=Min(odds_field))
                    .get("best")
                )
                if not best:
                    return None

                combined_odds *= best
                leg_info.append(
                    {
                        "match": match,
                        "selection": entry["selection"],
                        "odds": best,
                    }
                )

            combined_odds = combined_odds.quantize(Decimal("0.01"))

            balance = UserBalance.objects.select_for_update().get(user=user)
            if balance.balance < stake:
                return None

            log_transaction(
                balance,
                -stake,
                BalanceTransaction.Type.PARLAY_PLACEMENT,
                f"Parlay with {len(leg_info)} legs",
            )

            parlay = Parlay.objects.create(
                user=user,
                stake=stake,
                combined_odds=combined_odds,
            )
            ParlayLeg.objects.bulk_create(
                [
                    ParlayLeg(
                        parlay=parlay,
                        match=li["match"],
                        selection=li["selection"],
                        odds_at_placement=li["odds"],
                    )
                    for li in leg_info
                ]
            )

            logger.info(
                "Bot %s placed parlay: %d legs @ %sx, stake=%s",
                user.display_name,
                len(leg_info),
                combined_odds,
                stake,
            )
            return parlay

    except (UserBalance.DoesNotExist, IntegrityError):
        return None


def maybe_topup_bot(bot_user, min_balance=Decimal("50.00")):
    """Give the bot a bailout if balance is low and no pending bets."""
    try:
        balance = UserBalance.objects.get(user=bot_user)
    except UserBalance.DoesNotExist:
        return

    if balance.balance >= min_balance:
        return

    pending_bets = BetSlip.objects.filter(
        user=bot_user, status=BetStatus.PENDING
    ).exists()
    pending_parlays = Parlay.objects.filter(
        user=bot_user, status=BetStatus.PENDING
    ).exists()

    if pending_bets or pending_parlays:
        return

    with transaction.atomic():
        balance = UserBalance.objects.select_for_update().get(user=bot_user)
        if balance.balance >= min_balance:
            return

        bankruptcy = Bankruptcy.objects.create(
            user=bot_user,
            balance_at_bankruptcy=balance.balance,
        )

        amount = Decimal(str(random.randint(1000, 3000)))
        Bailout.objects.create(
            user=bot_user,
            bankruptcy=bankruptcy,
            amount=amount,
        )

        log_transaction(
            balance,
            amount,
            BalanceTransaction.Type.BAILOUT,
            "Bot bailout",
        )

        logger.info("Bot %s topped up with %s credits", bot_user.display_name, amount)
