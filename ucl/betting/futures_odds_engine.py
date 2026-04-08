"""Futures odds generation for UCL markets.

Strength is derived from UEFA club coefficients (approximated as static ratings).
Once the league phase begins, standings points layer on top of the baseline.
"""

import logging
import math
from decimal import Decimal

from ucl.betting.models import FuturesMarket, FuturesOutcome
from ucl.matches.models import Standing, Team
from vinosports.betting.models import FuturesMarketStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UEFA club coefficient approximations (2025-26 season).
# Higher = stronger. Scale is arbitrary but exponential transform makes
# the relative gaps produce realistic betting odds.
# ---------------------------------------------------------------------------
UEFA_CLUB_COEFFICIENTS: dict[str, int] = {
    "Real Madrid": 136,
    "Manchester City": 128,
    "Bayern Munich": 127,
    "Liverpool": 114,
    "Chelsea": 109,
    "Paris Saint-Germain": 108,
    "Barcelona": 107,
    "Internazionale": 101,
    "Borussia Dortmund": 97,
    "Juventus": 91,
    "Arsenal": 88,
    "Atletico Madrid": 87,
    "Atlético Madrid": 87,
    "Benfica": 85,
    "AC Milan": 80,
    "Tottenham Hotspur": 72,
    "Bayer Leverkusen": 72,
    "RB Leipzig": 65,
    "Sporting CP": 64,
    "Feyenoord": 62,
    "Newcastle United": 58,
    "PSV Eindhoven": 57,
    "Marseille": 56,
    "AS Monaco": 55,
    "Celtic": 53,
    "Club Brugge": 52,
    "Villarreal": 51,
    "Galatasaray": 50,
    "Aston Villa": 48,
    "Shakhtar Donetsk": 47,
    "Red Star Belgrade": 44,
    "Union St.-Gilloise": 40,
    "Dinamo Zagreb": 39,
    "Red Bull Salzburg": 38,
    "Bodo/Glimt": 30,
    "FK Qarabag": 28,
    "Ajax Amsterdam": 60,
    "Atalanta": 70,
    "Athletic Club": 45,
    "Eintracht Frankfurt": 55,
    "F.C. København": 32,
    "Napoli": 75,
    "Olympiacos": 35,
    "Slavia Prague": 33,
    "Kairat Almaty": 20,
    "Pafos": 18,
}

_FALLBACK_COEFFICIENT = 35


def _team_coefficient(team: Team) -> int:
    """Look up a team's UEFA coefficient, trying name variants."""
    if team.name in UEFA_CLUB_COEFFICIENTS:
        return UEFA_CLUB_COEFFICIENTS[team.name]
    if team.short_name and team.short_name in UEFA_CLUB_COEFFICIENTS:
        return UEFA_CLUB_COEFFICIENTS[team.short_name]
    # Case-insensitive fallback
    name_lower = team.name.lower()
    for key, val in UEFA_CLUB_COEFFICIENTS.items():
        if key.lower() == name_lower:
            return val
    logger.debug("No UEFA coefficient found for '%s', using fallback", team.name)
    return _FALLBACK_COEFFICIENT


def _coefficient_to_strength(coefficient: int) -> Decimal:
    """Convert UEFA coefficient to relative strength via exponential scaling.

    Formula: strength = exp((coefficient - 70) / 20)
    """
    exp_val = (coefficient - 70) / 20
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
    """Generate tournament winner odds for all 36 teams.

    Strength = UEFA coefficient strength + in-tournament bonus from standings.
    """
    teams = Team.objects.all()
    strength_map = {}
    for team in teams:
        base = _coefficient_to_strength(_team_coefficient(team))

        standing = Standing.objects.filter(team=team).first()
        if standing and (standing.points > 0 or standing.played > 0):
            bonus = Decimal(
                str(standing.points * 15 + max(0, standing.goal_difference))
            )
            base = base + bonus / Decimal("10")

        strength_map[team] = base

    return _softmax_odds(strength_map)


def generate_top_8_odds() -> dict:
    """Generate odds for finishing in the top 8 of the league phase.

    Top 8 automatically qualify for the Round of 16.
    """
    teams = Team.objects.all()
    strength_map = {}
    for team in teams:
        base = _coefficient_to_strength(_team_coefficient(team))

        standing = Standing.objects.filter(team=team).first()
        if standing and (standing.points > 0 or standing.played > 0):
            bonus = Decimal(
                str(standing.points * 20 + max(0, standing.goal_difference))
            )
            base = base + bonus / Decimal("5")

        strength_map[team] = base

    return _softmax_odds(strength_map, margin=Decimal("1.10"))


def update_all_futures_odds() -> None:
    """Recalculate odds for all open futures markets and write to DB."""
    markets = FuturesMarket.objects.filter(status=FuturesMarketStatus.OPEN)
    updated = 0
    for market in markets:
        if market.market_type == FuturesMarket.MarketType.WINNER:
            odds_map = generate_winner_odds()
        elif market.market_type == FuturesMarket.MarketType.TOP_8:
            odds_map = generate_top_8_odds()
        elif market.market_type == FuturesMarket.MarketType.FINALIST:
            winner_odds = generate_winner_odds()
            odds_map = {
                t: max(Decimal("1.05"), (o / Decimal("1.8")).quantize(Decimal("0.01")))
                for t, o in winner_odds.items()
            }
        else:
            continue

        for team, odds in odds_map.items():
            rows = FuturesOutcome.objects.filter(
                market=market,
                team=team,
            ).update(odds=odds)
            updated += rows

    logger.info(
        "Updated %d futures outcome rows across %d markets", updated, markets.count()
    )
