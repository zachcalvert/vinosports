from decimal import Decimal

from django.db.models import Min

from vinosports.betting.constants import (
    PARLAY_MAX_LEGS,
    PARLAY_MAX_PAYOUT,
    PARLAY_MIN_LEGS,
)
from vinosports.betting.models import Bankruptcy, BetStatus, UserBalance

MIN_BET = Decimal("0.50")
PARLAY_SESSION_KEY = "wc_parlay_slip"


def bankruptcy(request):
    if getattr(request, "league", None) != "worldcup":
        return {}
    if not request.user.is_authenticated:
        return {}

    try:
        balance = UserBalance.objects.get(user=request.user)
    except UserBalance.DoesNotExist:
        return {}

    if balance.balance >= MIN_BET:
        return {}

    from worldcup.betting.models import BetSlip

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
    if getattr(request, "league", None) != "worldcup":
        return {}

    from worldcup.betting.forms import PlaceParlayForm
    from worldcup.betting.models import BetSlip
    from worldcup.matches.models import Match, Odds

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

    ODDS_FIELD_MAP = {
        BetSlip.Selection.HOME_WIN: "home_win",
        BetSlip.Selection.DRAW: "draw",
        BetSlip.Selection.AWAY_WIN: "away_win",
    }

    raw = list(request.session.get(PARLAY_SESSION_KEY, []))
    match_ids = {entry.get("match_id") for entry in raw if entry.get("match_id")}
    matches_by_id = (
        {
            m.pk: m
            for m in Match.objects.filter(pk__in=match_ids).select_related(
                "home_team", "away_team"
            )
        }
        if match_ids
        else {}
    )

    legs = []
    combined_odds = Decimal("1.00")
    for entry in raw:
        mid = entry.get("match_id")
        match = matches_by_id.get(mid)
        if not match:
            continue
        selection = entry.get("selection", "")
        odds_field = ODDS_FIELD_MAP.get(selection)
        best_odds = None
        if odds_field:
            best_odds = (
                Odds.objects.filter(match=match)
                .aggregate(best=Min(odds_field))
                .get("best")
            )
        legs.append(
            {
                "match": match,
                "selection": selection,
                "selection_display": dict(BetSlip.Selection.choices).get(
                    selection, selection
                ),
                "odds": best_odds,
            }
        )
        if best_odds:
            combined_odds *= best_odds

    if not legs:
        combined_odds = Decimal("1.00")

    leg_count = len(legs)
    return {
        "parlay_legs": legs,
        "parlay_combined_odds": combined_odds if legs else None,
        "parlay_leg_count": leg_count,
        "parlay_legs_needed": max(0, PARLAY_MIN_LEGS - leg_count),
        "parlay_min_legs": PARLAY_MIN_LEGS,
        "parlay_max_legs": PARLAY_MAX_LEGS,
        "parlay_max_payout": PARLAY_MAX_PAYOUT,
        "parlay_form": PlaceParlayForm(),
    }


def futures_sidebar(request):
    """Inject top-5 WINNER futures outcomes for the sidebar widget."""
    if getattr(request, "league", None) != "worldcup":
        return {}

    from vinosports.betting.models import FuturesMarketStatus
    from worldcup.betting.models import FuturesMarket, FuturesOutcome

    try:
        market = FuturesMarket.objects.get(
            season="2026",
            market_type="WINNER",
            status=FuturesMarketStatus.OPEN,
        )
    except FuturesMarket.DoesNotExist:
        return {}

    outcomes = (
        FuturesOutcome.objects.filter(market=market, is_active=True)
        .select_related("team")
        .order_by("odds")[:5]
    )
    return {"futures_winner_outcomes": outcomes}
