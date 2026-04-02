"""
Bot bet placement service.

Translates BetInstruction/ParlayInstruction objects into real BetSlips and Parlays
using the same balance flow as human users.
"""

import logging
from decimal import Decimal

from nba.betting.balance import log_transaction
from nba.betting.models import BetSlip, Parlay, ParlayLeg
from nba.betting.settlement import (
    american_to_decimal,
    calculate_payout,
    decimal_to_american,
)
from nba.bots.strategies import BetInstruction, ParlayInstruction
from vinosports.betting.models import BalanceTransaction

logger = logging.getLogger(__name__)


def place_bot_bets(
    user, instructions: list[BetInstruction | ParlayInstruction]
) -> dict:
    """
    Place bets for a bot user from strategy output.

    Each bet is independent — a balance failure on one does not block others.
    Returns {"placed": int, "skipped": int}.
    """
    from nba.activity.models import ActivityEvent
    from nba.games.models import Game

    placed = 0
    skipped = 0

    for instr in instructions:
        if isinstance(instr, ParlayInstruction):
            ok = _place_parlay(user, instr)
            if ok:
                legs_count = len(instr.legs)
                # Link to the first leg's game, consistent with how the EPL app handles parlays
                try:
                    first_game = Game.objects.get(pk=instr.legs[0].game_id)
                    parlay_url = first_game.get_absolute_url()
                except (IndexError, Game.DoesNotExist):
                    logger.warning(
                        "place_bot_bets: could not resolve game URL for parlay (user=%s)",
                        user,
                    )
                    parlay_url = ""
                ActivityEvent.objects.create(
                    event_type=ActivityEvent.EventType.BOT_BET,
                    message=(
                        f"{user.display_name} placed a"
                        f" {legs_count}-leg parlay for ${instr.stake}"
                    ),
                    url=parlay_url,
                )
        else:
            ok = _place_single_bet(user, instr)
            if ok:
                try:
                    game = Game.objects.select_related("home_team", "away_team").get(
                        pk=instr.game_id
                    )
                    team_abbr = (
                        game.home_team.abbreviation
                        if instr.selection == "HOME"
                        else game.away_team.abbreviation
                    )
                    message = (
                        f"{user.display_name} bet ${instr.stake}"
                        f" on {team_abbr} {instr.market.lower()}"
                    )
                    game_url = game.get_absolute_url()
                except Game.DoesNotExist:
                    message = f"{user.display_name} bet ${instr.stake}"
                    game_url = ""
                ActivityEvent.objects.create(
                    event_type=ActivityEvent.EventType.BOT_BET,
                    message=message,
                    url=game_url,
                )

        if ok:
            placed += 1
        else:
            skipped += 1

    return {"placed": placed, "skipped": skipped}


def _place_single_bet(user, instr: BetInstruction) -> bool:
    try:
        log_transaction(
            user,
            -instr.stake,
            BalanceTransaction.Type.BET_PLACEMENT,
            f"Bot bet: {instr.market} {instr.selection} (game {instr.game_id})",
        )
    except ValueError:
        logger.info("Bot %s: insufficient balance for $%s bet", user, instr.stake)
        return False

    BetSlip.objects.create(
        user=user,
        game_id=instr.game_id,
        market=instr.market,
        selection=instr.selection,
        line=instr.line,
        odds_at_placement=instr.odds,
        stake=instr.stake,
    )
    return True


def _place_parlay(user, instr: ParlayInstruction) -> bool:
    if len(instr.legs) < 2:
        return False

    # Compute combined odds
    combined_decimal = Decimal("1")
    for leg in instr.legs:
        combined_decimal *= american_to_decimal(leg.odds)
    combined_odds = decimal_to_american(combined_decimal)

    max_payout = calculate_payout(instr.stake, combined_odds)
    cap = Decimal("100000000.00")
    max_payout = min(max_payout, cap)

    try:
        log_transaction(
            user,
            -instr.stake,
            BalanceTransaction.Type.PARLAY_PLACEMENT,
            f"Bot parlay: {len(instr.legs)} legs",
        )
    except ValueError:
        logger.info("Bot %s: insufficient balance for $%s parlay", user, instr.stake)
        return False

    parlay = Parlay.objects.create(
        user=user,
        stake=instr.stake,
        combined_odds=combined_odds,
        max_payout=max_payout,
    )

    for leg in instr.legs:
        ParlayLeg.objects.create(
            parlay=parlay,
            game_id=leg.game_id,
            market=leg.market,
            selection=leg.selection,
            line=leg.line,
            odds_at_placement=leg.odds,
        )

    return True
