from decimal import Decimal

from django.db.models import Min

from vinosports.betting.constants import (
    PARLAY_MAX_LEGS,
    PARLAY_MAX_PAYOUT,
    PARLAY_MIN_LEGS,
)
from vinosports.betting.models import Bankruptcy, BetStatus, UserBalance

MIN_BET = Decimal("0.50")
PARLAY_SESSION_KEY = "ucl_parlay_slip"


def bankruptcy(request):
    if getattr(request, "league", None) != "ucl":
        return {}
    if not request.user.is_authenticated:
        return {}

    try:
        balance = UserBalance.objects.get(user=request.user)
    except UserBalance.DoesNotExist:
        return {}

    if balance.balance >= MIN_BET:
        return {}

    from ucl.betting.models import BetSlip

    has_pending = BetSlip.objects.filter(
        user=request.user, status=BetStatus.PENDING
    ).exists()
    if has_pending:
        return {}

    bankruptcy_obj, _ = Bankruptcy.objects.get_or_create(user=request.user)
    return {"bankruptcy": bankruptcy_obj}


def parlay_slip(request):
    if getattr(request, "league", None) != "ucl":
        return {}
    slip = request.session.get(PARLAY_SESSION_KEY, [])

    if slip:
        from ucl.matches.models import Odds

        match_ids = [leg["match_id"] for leg in slip]
        latest_odds = (
            Odds.objects.filter(match_id__in=match_ids)
            .values("match_id")
            .annotate(latest=Min("id"))
        )
        odds_map = {}
        for entry in latest_odds:
            odds_obj = Odds.objects.get(id=entry["latest"])
            odds_map[odds_obj.match_id] = odds_obj

        for leg in slip:
            mid = leg["match_id"]
            odds_obj = odds_map.get(mid)
            if odds_obj:
                sel = leg["selection"]
                if sel == "HOME_WIN":
                    leg["current_odds"] = float(odds_obj.home_win)
                elif sel == "DRAW":
                    leg["current_odds"] = float(odds_obj.draw)
                elif sel == "AWAY_WIN":
                    leg["current_odds"] = float(odds_obj.away_win)

    return {
        "parlay_slip": slip,
        "parlay_count": len(slip),
        "parlay_min_legs": PARLAY_MIN_LEGS,
        "parlay_max_legs": PARLAY_MAX_LEGS,
        "parlay_max_payout": PARLAY_MAX_PAYOUT,
    }


def futures_sidebar(request):
    if getattr(request, "league", None) != "ucl":
        return {}

    from ucl.betting.models import FuturesMarket

    markets = FuturesMarket.objects.filter(status="OPEN").order_by("market_type")
    return {"futures_markets": markets}
