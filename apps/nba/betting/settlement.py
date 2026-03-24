"""
Bet settlement logic.

settle_game_bets(game_pk) is the main entry point: it evaluates all PENDING bets
and parlay legs for a FINAL game, updates statuses, credits winnings, and checks
for bankruptcy.
"""

import logging
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone
from games.models import Game

from betting.balance import log_transaction
from betting.models import BetSlip, Parlay, ParlayLeg
from betting.stats import record_bet_result
from vinosports.betting.models import (
    Bailout,
    BalanceTransaction,
    Bankruptcy,
    BetStatus,
    UserBalance,
)

logger = logging.getLogger(__name__)

BANKRUPTCY_THRESHOLD = Decimal("0.50")


def _evaluate_bet_outcome(
    market: str, selection: str, line: float | None, game: Game
) -> str:
    """
    Pure logic: given market type, selection, line, and final game scores,
    return BetStatus value (WON, LOST, or VOID).
    """
    home = game.home_score
    away = game.away_score

    if market == BetSlip.Market.MONEYLINE:
        if home == away:
            return BetStatus.VOID
        if selection == BetSlip.Selection.HOME:
            return BetStatus.WON if home > away else BetStatus.LOST
        else:
            return BetStatus.WON if away > home else BetStatus.LOST

    elif market == BetSlip.Market.SPREAD:
        if selection == BetSlip.Selection.HOME:
            adjusted = home + line
            diff = adjusted - away
        else:
            adjusted = away + line
            diff = adjusted - home
        if diff == 0:
            return BetStatus.VOID
        return BetStatus.WON if diff > 0 else BetStatus.LOST

    elif market == BetSlip.Market.TOTAL:
        total = home + away
        diff = total - line
        if diff == 0:
            return BetStatus.VOID
        if selection == BetSlip.Selection.OVER:
            return BetStatus.WON if total > line else BetStatus.LOST
        else:
            return BetStatus.WON if total < line else BetStatus.LOST

    raise ValueError(f"Unknown market: {market}")


def american_to_decimal(odds: int) -> Decimal:
    """Convert American odds to decimal odds."""
    if odds > 0:
        return Decimal(odds) / 100 + 1
    else:
        return Decimal(100) / Decimal(abs(odds)) + 1


def decimal_to_american(dec: Decimal) -> int:
    """Convert decimal odds to American odds."""
    if dec >= 2:
        return int((dec - 1) * 100)
    else:
        return int(-100 / (dec - 1))


def calculate_payout(stake: Decimal, american_odds: int) -> Decimal:
    """Calculate payout from stake and American odds."""
    dec = american_to_decimal(american_odds)
    return (stake * dec).quantize(Decimal("0.01"))


def recalculate_parlay_odds(won_legs) -> int:
    """
    Given the WON legs of a parlay, compute the reduced American odds.
    Multiplies decimal odds of each leg, then converts back to American.
    """
    combined_decimal = Decimal("1")
    for leg in won_legs:
        combined_decimal *= american_to_decimal(leg.odds_at_placement)
    return decimal_to_american(combined_decimal)


@db_transaction.atomic
def settle_game_bets(game_pk: int) -> dict:
    """
    Settle all PENDING BetSlips and ParlayLegs for a FINAL game.
    Returns {"settled": int, "won": int, "lost": int, "void": int}.

    Idempotent: only touches PENDING bets.
    Raises ValueError if game is not FINAL or scores are missing.
    """
    game = Game.objects.get(pk=game_pk)
    if not game.is_final:
        raise ValueError(f"Game {game_pk} is not FINAL (status={game.status})")
    if game.home_score is None or game.away_score is None:
        raise ValueError(f"Game {game_pk} has no scores")

    now = timezone.now()
    counts = {"settled": 0, "won": 0, "lost": 0, "void": 0}
    affected_users = set()
    affected_parlay_ids = set()

    # --- Settle BetSlips ---
    bets = BetSlip.objects.filter(
        game=game, status=BetStatus.PENDING
    ).select_for_update()

    for bet in bets:
        outcome = _evaluate_bet_outcome(bet.market, bet.selection, bet.line, game)
        bet.status = outcome
        bet.settled_at = now

        if outcome == BetStatus.WON:
            bet.payout = calculate_payout(bet.stake, bet.odds_at_placement)
            log_transaction(
                bet.user,
                bet.payout,
                BalanceTransaction.Type.BET_WIN,
                f"Won: {bet.market} {bet.selection} on {game}",
            )
            record_bet_result(bet.user, won=True, stake=bet.stake, payout=bet.payout)
            counts["won"] += 1
        elif outcome == BetStatus.LOST:
            record_bet_result(bet.user, won=False, stake=bet.stake, payout=Decimal("0"))
            counts["lost"] += 1
        elif outcome == BetStatus.VOID:
            log_transaction(
                bet.user,
                bet.stake,
                BalanceTransaction.Type.BET_VOID,
                f"Void (push): {bet.market} {bet.selection} on {game}",
            )
            counts["void"] += 1

        bet.save()
        counts["settled"] += 1
        affected_users.add(bet.user)

    # --- Settle ParlayLegs ---
    legs = ParlayLeg.objects.filter(
        game=game, status=BetStatus.PENDING
    ).select_for_update()

    for leg in legs:
        outcome = _evaluate_bet_outcome(leg.market, leg.selection, leg.line, game)
        leg.status = outcome
        leg.save()
        affected_parlay_ids.add(leg.parlay_id)

    # --- Evaluate affected Parlays ---
    for parlay_id in affected_parlay_ids:
        _evaluate_parlay(parlay_id, now)
        parlay = Parlay.objects.get(pk=parlay_id)
        affected_users.add(parlay.user)

    # --- Check bankruptcy ---
    for user in affected_users:
        _check_bankruptcy(user)

    # --- Create ActivityEvent ---
    from activity.models import ActivityEvent

    if counts["settled"] > 0:
        ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.BET_SETTLEMENT,
            message=f"Settled {counts['settled']} bets on {game}",
            url=game.get_absolute_url(),
        )

    logger.info(
        "settle_game_bets: game=%s settled=%d won=%d lost=%d void=%d",
        game_pk,
        counts["settled"],
        counts["won"],
        counts["lost"],
        counts["void"],
    )
    affected_user_ids = [u.pk for u in affected_users]
    return {**counts, "affected_user_ids": affected_user_ids}


def _evaluate_parlay(parlay_id: int, now=None) -> None:
    """
    Evaluate whether a parlay can be resolved after settling one or more legs.

    Rules:
    - Any leg LOST -> parlay LOST (immediately)
    - All legs WON -> parlay WON, payout = calculate_payout(stake, combined_odds)
    - All resolved, mix of WON + VOID -> recalculate with reduced odds
    - All legs VOID -> refund stake
    - Any legs still PENDING -> do nothing (wait)
    """
    parlay = Parlay.objects.select_for_update().get(pk=parlay_id)
    if parlay.status != BetStatus.PENDING:
        return  # Already settled

    if now is None:
        now = timezone.now()

    legs = parlay.legs.all()
    statuses = set(legs.values_list("status", flat=True))

    # Any LOST leg -> parlay is LOST
    if BetStatus.LOST in statuses:
        parlay.status = BetStatus.LOST
        parlay.settled_at = now
        parlay.save()
        record_bet_result(
            parlay.user, won=False, stake=parlay.stake, payout=Decimal("0")
        )
        return

    # Still have PENDING legs -> wait
    if BetStatus.PENDING in statuses:
        return

    # All legs resolved (WON and/or VOID, no PENDING, no LOST)
    won_legs = legs.filter(status=BetStatus.WON)
    void_legs = legs.filter(status=BetStatus.VOID)

    if void_legs.count() == legs.count():
        # All VOID -> refund
        parlay.status = BetStatus.VOID
        parlay.settled_at = now
        parlay.save()
        log_transaction(
            parlay.user,
            parlay.stake,
            BalanceTransaction.Type.PARLAY_VOID,
            "Parlay void: all legs pushed",
        )
    elif won_legs.count() == legs.count():
        # All WON -> full payout
        payout = calculate_payout(parlay.stake, parlay.combined_odds)
        payout = min(payout, parlay.max_payout)
        parlay.status = BetStatus.WON
        parlay.payout = payout
        parlay.settled_at = now
        parlay.save()
        log_transaction(
            parlay.user,
            payout,
            BalanceTransaction.Type.PARLAY_WIN,
            "Parlay won",
        )
        record_bet_result(parlay.user, won=True, stake=parlay.stake, payout=payout)
    else:
        # Mix of WON + VOID -> recalculate with reduced odds
        reduced_odds = recalculate_parlay_odds(won_legs)
        payout = calculate_payout(parlay.stake, reduced_odds)
        payout = min(payout, parlay.max_payout)
        parlay.status = BetStatus.WON
        parlay.payout = payout
        parlay.combined_odds = reduced_odds
        parlay.settled_at = now
        parlay.save()
        log_transaction(
            parlay.user,
            payout,
            BalanceTransaction.Type.PARLAY_WIN,
            f"Parlay won (reduced: {void_legs.count()} void leg(s))",
        )
        record_bet_result(parlay.user, won=True, stake=parlay.stake, payout=payout)


def _check_bankruptcy(user) -> bool:
    """
    Check if user's balance is at or below the threshold.
    If so, create a Bankruptcy record. Returns True if bankrupt.
    """
    try:
        balance_obj = UserBalance.objects.get(user=user)
    except UserBalance.DoesNotExist:
        return False

    if balance_obj.balance <= BANKRUPTCY_THRESHOLD:
        Bankruptcy.objects.create(user=user, balance_at_bankruptcy=balance_obj.balance)
        logger.info("User %s declared bankrupt (balance=%s)", user, balance_obj.balance)
        return True
    return False


def grant_bailout(user, amount: Decimal = Decimal("500.00")) -> Bailout:
    """
    Grant a bailout to a bankrupt user. Credits balance and creates a Bailout record.
    Raises ValueError if user is not bankrupt (balance > threshold).
    """
    try:
        balance_obj = UserBalance.objects.get(user=user)
    except UserBalance.DoesNotExist:
        raise ValueError("User has no balance record")

    if balance_obj.balance > BANKRUPTCY_THRESHOLD:
        raise ValueError(f"User is not bankrupt (balance={balance_obj.balance})")

    latest_bankruptcy = (
        Bankruptcy.objects.filter(user=user).order_by("-created_at").first()
    )

    log_transaction(user, amount, BalanceTransaction.Type.BAILOUT, "Bailout granted")

    bailout = Bailout.objects.create(
        user=user,
        amount=amount,
        bankruptcy=latest_bankruptcy,
    )
    logger.info("Bailout granted to %s: %s", user, amount)
    return bailout
