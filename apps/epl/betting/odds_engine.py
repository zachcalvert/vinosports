"""
Algorithmic odds engine — generates realistic 1X2 decimal odds for EPL matches
based on league standings (position, PPG, goal difference) and home advantage.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from matches.models import Match, Standing

logger = logging.getLogger(__name__)

HOME_ADVANTAGE = Decimal("1.25")
DRAW_BASELINE = Decimal("0.27")
MARGIN = Decimal("0.05")
MIN_ODDS = Decimal("1.05")
MAX_ODDS = Decimal("25.00")

PPG_WEIGHT = Decimal("0.60")
POSITION_WEIGHT = Decimal("0.40")

FALLBACK_STRENGTH = Decimal("0.50")

TWO_PLACES = Decimal("0.01")


def _team_strength(standing):
    played = max(standing.played, 1)
    ppg = Decimal(standing.points) / Decimal(played)
    ppg_norm = ppg / Decimal("3.0")
    pos_rating = (Decimal(21) - Decimal(standing.position)) / Decimal(20)
    return (PPG_WEIGHT * ppg_norm) + (POSITION_WEIGHT * pos_rating)


def generate_match_odds(home_standing, away_standing):
    home_strength = (
        _team_strength(home_standing) if home_standing else FALLBACK_STRENGTH
    )
    away_strength = (
        _team_strength(away_standing) if away_standing else FALLBACK_STRENGTH
    )

    home_strength = home_strength * HOME_ADVANTAGE

    total = home_strength + away_strength
    if total == 0:
        total = Decimal("1")
        home_strength = Decimal("0.5")
        away_strength = Decimal("0.5")

    p_home_raw = home_strength / total
    p_away_raw = away_strength / total

    gap = abs(p_home_raw - p_away_raw)
    p_draw = max(
        DRAW_BASELINE * (Decimal("1") - gap),
        Decimal("0.08"),
    )

    remaining = Decimal("1") - p_draw
    p_home = p_home_raw * remaining
    p_away = p_away_raw * remaining

    p_home = max(p_home, Decimal("0.01"))
    p_draw = max(p_draw, Decimal("0.01"))
    p_away = max(p_away, Decimal("0.01"))

    margin_factor = Decimal("1") / (Decimal("1") + MARGIN)

    home_odds = (Decimal("1") / p_home) * margin_factor
    draw_odds = (Decimal("1") / p_draw) * margin_factor
    away_odds = (Decimal("1") / p_away) * margin_factor

    home_odds = _clamp(home_odds)
    draw_odds = _clamp(draw_odds)
    away_odds = _clamp(away_odds)

    return {
        "home_win": home_odds,
        "draw": draw_odds,
        "away_win": away_odds,
    }


def _clamp(odds):
    clamped = max(MIN_ODDS, min(MAX_ODDS, odds))
    return clamped.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def generate_all_upcoming_odds(season=None):
    season = season or getattr(settings, "CURRENT_SEASON", "2025")

    matches = (
        Match.objects.filter(
            season=season,
            status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
        )
        .select_related("home_team", "away_team")
        .order_by("kickoff")
    )

    standings = Standing.objects.filter(season=season)
    standings_map = {s.team_id: s for s in standings}

    results = []
    for match in matches:
        home_standing = standings_map.get(match.home_team_id)
        away_standing = standings_map.get(match.away_team_id)

        odds = generate_match_odds(home_standing, away_standing)
        results.append(
            {
                "match": match,
                **odds,
            }
        )

    logger.info(
        "generate_all_upcoming_odds: generated odds for %d matches (season %s)",
        len(results),
        season,
    )
    return results
