"""Futures odds generation for World Cup markets."""

import logging
from decimal import Decimal

from vinosports.betting.models import FuturesMarketStatus
from worldcup.betting.models import FuturesMarket, FuturesOutcome
from worldcup.matches.models import Standing, Team

logger = logging.getLogger(__name__)


def _softmax_odds(strength_map, margin=Decimal("1.15")):
    """Convert {team: strength} to {team: decimal_odds} with margin."""
    total = sum(strength_map.values())
    if total == 0:
        n = len(strength_map)
        return {
            t: (Decimal(str(n)) * margin).quantize(Decimal("0.01"))
            for t in strength_map
        }

    odds = {}
    for team, strength in strength_map.items():
        prob = strength / total
        if prob < Decimal("0.001"):
            prob = Decimal("0.001")
        raw_odds = margin / prob
        odds[team] = max(Decimal("1.05"), min(Decimal("500.00"), raw_odds)).quantize(
            Decimal("0.01")
        )
    return odds


def generate_winner_odds():
    """Generate tournament winner odds for all 48 teams."""
    teams = Team.objects.all()
    strength_map = {}
    for team in teams:
        standing = Standing.objects.filter(team=team).first()
        if standing:
            strength_map[team] = Decimal(
                str(standing.points * 10 + standing.goal_difference + 100)
            )
        else:
            strength_map[team] = Decimal("50")
    return _softmax_odds(strength_map)


def generate_group_winner_odds(group):
    """Generate group winner odds for 4 teams in a group."""
    standings = Standing.objects.filter(group=group).select_related("team")
    strength_map = {}
    for s in standings:
        strength_map[s.team] = Decimal(str(s.points * 10 + s.goal_difference + 50))
    if not strength_map:
        for team in group.teams.all():
            strength_map[team] = Decimal("25")
    return _softmax_odds(strength_map, margin=Decimal("1.10"))


def update_all_futures_odds():
    """Recalculate odds for all open futures markets."""
    markets = FuturesMarket.objects.filter(status=FuturesMarketStatus.OPEN)
    for market in markets:
        if market.market_type == FuturesMarket.MarketType.WINNER:
            odds_map = generate_winner_odds()
        elif market.market_type == FuturesMarket.MarketType.GROUP_WINNER:
            if not market.group:
                continue
            odds_map = generate_group_winner_odds(market.group)
        elif market.market_type == FuturesMarket.MarketType.FINALIST:
            odds_map = generate_winner_odds()
            # Finalist odds are roughly half the winner odds
            odds_map = {
                t: max(Decimal("1.05"), (o / 2).quantize(Decimal("0.01")))
                for t, o in odds_map.items()
            }
        else:
            continue

        for team, odds in odds_map.items():
            FuturesOutcome.objects.filter(
                market=market, team=team, is_active=True
            ).update(odds=odds)

    logger.info("Updated futures odds for %d markets", markets.count())
