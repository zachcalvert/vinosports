from decimal import Decimal

from games.models import Game

from betting.forms import PlaceParlayForm
from betting.models import BetSlip
from betting.settlement import american_to_decimal
from vinosports.betting.constants import (
    PARLAY_MAX_LEGS,
    PARLAY_MAX_PAYOUT,
    PARLAY_MIN_LEGS,
)
from vinosports.betting.models import Bankruptcy, BetStatus, UserBalance

MIN_BET = Decimal("0.50")
PARLAY_SESSION_KEY = "parlay_slip"


def bankruptcy(request):
    if not request.user.is_authenticated:
        return {}

    try:
        balance = UserBalance.objects.get(user=request.user)
    except UserBalance.DoesNotExist:
        return {}

    if balance.balance >= MIN_BET:
        return {}

    has_pending_bets = BetSlip.objects.filter(
        user=request.user, status=BetStatus.PENDING
    ).exists()

    if has_pending_bets:
        return {}

    bankruptcy_count = Bankruptcy.objects.filter(user=request.user).count()

    return {
        "is_bankrupt": True,
        "bankrupt_balance": balance.balance,
        "bankruptcy_count": bankruptcy_count,
    }


def parlay_slip(request):
    """Provide parlay slip context to every template via base.html."""
    if not request.user.is_authenticated:
        return {
            "parlay_leg_count": 0,
            "parlay_legs_needed": PARLAY_MIN_LEGS,
            "parlay_legs": [],
            "parlay_combined_odds": None,
            "parlay_min_legs": PARLAY_MIN_LEGS,
            "parlay_max_legs": PARLAY_MAX_LEGS,
            "parlay_max_payout": PARLAY_MAX_PAYOUT,
            "parlay_form": PlaceParlayForm(),
        }

    raw = list(request.session.get(PARLAY_SESSION_KEY, []))
    game_ids = {entry.get("game_id") for entry in raw if entry.get("game_id")}
    games_by_id = (
        {
            g.pk: g
            for g in Game.objects.filter(pk__in=game_ids).select_related(
                "home_team", "away_team"
            )
        }
        if game_ids
        else {}
    )

    legs = []
    combined_decimal = Decimal("1.00")
    for entry in raw:
        gid = entry.get("game_id")
        game = games_by_id.get(gid)
        if not game:
            continue

        selection = entry.get("selection", "")
        market = entry.get("market", "")
        odds_value = entry.get("odds")

        if odds_value is not None:
            dec = american_to_decimal(int(odds_value))
            combined_decimal *= dec

        legs.append(
            {
                "game": game,
                "market": market,
                "market_display": dict(BetSlip.Market.choices).get(market, market),
                "selection": selection,
                "selection_display": dict(BetSlip.Selection.choices).get(
                    selection, selection
                ),
                "odds": odds_value,
                "line": entry.get("line"),
            }
        )

    if not legs:
        combined_decimal = Decimal("1.00")

    leg_count = len(legs)
    return {
        "parlay_legs": legs,
        "parlay_combined_odds": combined_decimal if legs else None,
        "parlay_leg_count": leg_count,
        "parlay_legs_needed": max(0, PARLAY_MIN_LEGS - leg_count),
        "parlay_min_legs": PARLAY_MIN_LEGS,
        "parlay_max_legs": PARLAY_MAX_LEGS,
        "parlay_max_payout": PARLAY_MAX_PAYOUT,
        "parlay_form": PlaceParlayForm(),
    }
