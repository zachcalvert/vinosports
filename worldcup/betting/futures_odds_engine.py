"""Futures odds generation for World Cup markets.

Pre-tournament strength is derived from FIFA ranking points (April 2026).
Once group play begins, standings points layer on top of the baseline.
"""

import logging
import math
from decimal import Decimal

from vinosports.betting.models import FuturesMarketStatus
from worldcup.betting.models import FuturesMarket, FuturesOutcome
from worldcup.matches.models import Standing, Team

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FIFA ranking points (April 2026).
# Source: FIFA World Rankings, extracted April 2026.
# Keys use the names as returned by football-data.org / FIFA.
# ---------------------------------------------------------------------------
FIFA_RANKING_POINTS: dict[str, int] = {
    "France": 1877,
    "Spain": 1876,
    "Argentina": 1875,
    "England": 1826,
    "Portugal": 1764,
    "Brazil": 1761,
    "Netherlands": 1758,
    "Morocco": 1756,
    "Belgium": 1735,
    "Germany": 1730,
    "Croatia": 1717,
    "Italy": 1700,
    "Colombia": 1693,
    "Senegal": 1689,
    "Mexico": 1681,
    "USA": 1673,
    "Uruguay": 1673,
    "Japan": 1660,
    "Switzerland": 1649,
    "Denmark": 1621,
    "IR Iran": 1615,
    "Türkiye": 1599,
    "Ecuador": 1595,
    "Austria": 1593,
    "Korea Republic": 1589,
    "Nigeria": 1585,
    "Australia": 1581,
    "Algeria": 1564,
    "Egypt": 1563,
    "Canada": 1556,
    "Norway": 1551,
    "Ukraine": 1547,
    "Panama": 1541,
    "Côte d'Ivoire": 1533,
    "Poland": 1528,
    "Serbia": 1509,
    "Paraguay": 1504,
    "Hungary": 1501,
    "Tunisia": 1483,
    "Cameroon": 1481,
    "Congo DR": 1478,
    "Slovakia": 1474,
    "Venezuela": 1468,
    "Uzbekistan": 1465,
    "Costa Rica": 1460,
    "Mali": 1459,
    "Peru": 1456,
    "Chile": 1455,
    "Qatar": 1455,
    "Romania": 1451,
    "Iraq": 1447,
    "Slovenia": 1446,
    "South Africa": 1430,
    "Saudi Arabia": 1421,
    "Burkina Faso": 1412,
    "Jordan": 1391,
    "Albania": 1388,
    "Bosnia and Herzegovina": 1386,
    "Honduras": 1380,
    "United Arab Emirates": 1370,
    "Cabo Verde": 1366,
    "Jamaica": 1358,
    "Georgia": 1350,
    "Ghana": 1346,
    "Iceland": 1345,
    "Bolivia": 1329,
    "New Zealand": 1282,
    "Guatemala": 1243,
    "El Salvador": 1225,
    # Common name variants (football-data.org may use these)
    "United States": 1673,
    "Iran": 1615,
    "Turkey": 1599,
    "South Korea": 1589,
    "Republic of Korea": 1589,
    "Bosnia-Herzegovina": 1386,
    "Ivory Coast": 1533,
    "Cape Verde": 1366,
    "DR Congo": 1478,
    "China PR": 1252,
    "China": 1252,
    "Trinidad and Tobago": 1273,
}

# Fallback points for teams not in the ranking table
_FALLBACK_POINTS = 1300


def _team_rating(team: Team) -> int:
    """Look up a team's FIFA rating, trying name variants."""
    # Direct match
    if team.name in FIFA_RANKING_POINTS:
        return FIFA_RANKING_POINTS[team.name]
    # Try short_name
    if team.short_name and team.short_name in FIFA_RANKING_POINTS:
        return FIFA_RANKING_POINTS[team.short_name]
    # Try TLA (e.g. "USA")
    if team.tla and team.tla in FIFA_RANKING_POINTS:
        return FIFA_RANKING_POINTS[team.tla]
    # Case-insensitive fallback
    name_lower = team.name.lower()
    for key, val in FIFA_RANKING_POINTS.items():
        if key.lower() == name_lower:
            return val
    logger.debug("No FIFA ranking found for team '%s', using fallback", team.name)
    return _FALLBACK_POINTS


def _rating_to_strength(rating_points: int) -> Decimal:
    """
    Convert FIFA rating points to a relative strength value.

    Uses exponential scaling so that top-ranked teams get significantly
    higher strength than the field, producing realistic spread in odds
    (favorites ~6-12x, heavy underdogs ~200-500x for 48-team tournament).

    Formula: strength = exp((points - 1500) / 100)
    """
    exp_val = (rating_points - 1500) / 100
    return Decimal(str(round(math.exp(exp_val), 6)))


def _softmax_odds(strength_map: dict, margin: Decimal = Decimal("1.15")) -> dict:
    """Convert {team: strength} → {team: decimal_odds} with bookmaker margin."""
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
        if prob < Decimal("0.0005"):
            prob = Decimal("0.0005")
        raw_odds = margin / prob
        odds[team] = max(Decimal("1.05"), min(Decimal("999.00"), raw_odds)).quantize(
            Decimal("0.01")
        )
    return odds


def generate_winner_odds() -> dict:
    """Generate tournament winner odds for all 48 teams.

    Strength = FIFA ranking strength + in-tournament bonus from standings
    (once group play begins, points accumulate and shift odds dynamically).
    """
    teams = Team.objects.all()
    strength_map = {}
    for team in teams:
        # Base strength from FIFA ranking
        base = _rating_to_strength(_team_rating(team))

        # Layer in standings bonus once matches have been played
        standing = Standing.objects.filter(team=team).first()
        if standing and (standing.points > 0 or standing.played > 0):
            bonus = Decimal(
                str(standing.points * 15 + max(0, standing.goal_difference))
            )
            base = base + bonus / Decimal("10")

        strength_map[team] = base

    return _softmax_odds(strength_map)


def generate_group_winner_odds(group) -> dict:
    """Generate group winner odds for the 4 teams in a group."""
    standings = Standing.objects.filter(group=group).select_related("team")
    strength_map = {}

    if standings.exists():
        for s in standings:
            base = _rating_to_strength(_team_rating(s.team))
            if s.points > 0 or s.played > 0:
                bonus = Decimal(str(s.points * 20 + max(0, s.goal_difference)))
                base = base + bonus / Decimal("5")
            strength_map[s.team] = base
    else:
        # Pre-tournament: use FIFA rankings for all teams in the group
        for team in group.teams.all():
            strength_map[team] = _rating_to_strength(_team_rating(team))

    if not strength_map:
        for team in group.teams.all():
            strength_map[team] = Decimal("1.0")

    return _softmax_odds(strength_map, margin=Decimal("1.10"))


def update_all_futures_odds() -> None:
    """Recalculate odds for all open futures markets and write to DB."""
    markets = FuturesMarket.objects.filter(status=FuturesMarketStatus.OPEN)
    updated = 0
    for market in markets:
        if market.market_type == FuturesMarket.MarketType.WINNER:
            odds_map = generate_winner_odds()
        elif market.market_type == FuturesMarket.MarketType.GROUP_WINNER:
            if not market.group:
                continue
            odds_map = generate_group_winner_odds(market.group)
        elif market.market_type == FuturesMarket.MarketType.FINALIST:
            # Finalist odds ≈ winner odds halved (teams need to reach the final, not win it)
            winner_odds = generate_winner_odds()
            odds_map = {
                t: max(Decimal("1.05"), (o / Decimal("1.8")).quantize(Decimal("0.01")))
                for t, o in winner_odds.items()
            }
        else:
            continue

        for team, odds in odds_map.items():
            rows = FuturesOutcome.objects.filter(
                market=market, team=team, is_active=True
            ).update(odds=odds)
            updated += rows

    logger.info(
        "Updated %d futures outcome rows across %d markets", updated, markets.count()
    )
