"""
Futures odds engine — generates realistic American odds for NFL season-level
markets (Super Bowl, Conference, Division) based on standings.
"""

import logging
import math

from django.utils import timezone

from nfl.games.models import Conference, Division, Standing

logger = logging.getLogger(__name__)

# --- Constants ---
WIN_PCT_WEIGHT = 0.50
POINT_DIFF_WEIGHT = 0.50

MARGIN_SUPER_BOWL = 0.30  # ~130% book for 32-team Super Bowl market
MARGIN_CONFERENCE = 0.20  # ~120% for 16-team conference market
MARGIN_DIVISION = 0.15  # ~115% for 4-team division market

SOFTMAX_TEMPERATURE_SUPER_BOWL = 2.0
SOFTMAX_TEMPERATURE_CONFERENCE = 1.8
SOFTMAX_TEMPERATURE_DIVISION = 1.5

FALLBACK_WIN_PCT = 0.500
MIN_ODDS = -500
MAX_ODDS = 10000

# AFC/NFC → divisions mapping
CONFERENCE_DIVISIONS = {
    Conference.AFC: [
        Division.AFC_EAST,
        Division.AFC_NORTH,
        Division.AFC_SOUTH,
        Division.AFC_WEST,
    ],
    Conference.NFC: [
        Division.NFC_EAST,
        Division.NFC_NORTH,
        Division.NFC_SOUTH,
        Division.NFC_WEST,
    ],
}


def _norm_point_diff(standing) -> float:
    """Normalise point differential to 0.0–1.0 scale."""
    pd = standing.point_differential
    return max(0.0, min(1.0, (pd + 200) / 400))


def _championship_strength(standing) -> float:
    """Compute championship strength from standings (0.0-1.0 scale)."""
    win_pct = float(standing.win_pct) if standing.win_pct else FALLBACK_WIN_PCT
    pd_score = _norm_point_diff(standing)
    return WIN_PCT_WEIGHT * win_pct + POINT_DIFF_WEIGHT * pd_score


def _softmax(strengths: list[float], temperature: float) -> list[float]:
    """Convert raw strength scores to probabilities via softmax."""
    scaled = [s / temperature for s in strengths]
    max_s = max(scaled)
    exps = [math.exp(s - max_s) for s in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def _apply_margin(probabilities: list[float], margin: float) -> list[float]:
    """Scale probabilities to include bookmaker margin (vig)."""
    return [p * (1.0 + margin) for p in probabilities]


def _probability_to_american(prob: float) -> int:
    """Convert an implied probability (0-1) to American odds."""
    if prob <= 0 or prob >= 1:
        return 10000
    decimal_odds = 1.0 / prob
    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1) * 100))
    else:
        return int(round(-100 / (decimal_odds - 1)))


def _clamp_american(odds: int) -> int:
    """Clamp American odds to reasonable range."""
    if odds > 0:
        return max(100, min(MAX_ODDS, odds))
    else:
        return max(MIN_ODDS, min(-100, odds))


def _generate_odds_from_standings(
    standings: list, temperature: float, margin: float
) -> list[dict]:
    """Generate odds for a list of standings using softmax."""
    if not standings:
        return []

    strengths = [_championship_strength(s) for s in standings]
    probs = _softmax(strengths, temperature)
    probs_with_margin = _apply_margin(probs, margin)

    return [
        {"team_id": s.team_id, "odds": _clamp_american(_probability_to_american(p))}
        for s, p in zip(standings, probs_with_margin)
    ]


def generate_super_bowl_odds(standings: list) -> list[dict]:
    """Generate Super Bowl Winner odds from all 32 team standings."""
    return _generate_odds_from_standings(
        standings, SOFTMAX_TEMPERATURE_SUPER_BOWL, MARGIN_SUPER_BOWL
    )


def generate_conference_odds(standings: list) -> list[dict]:
    """Generate conference winner odds from conference-filtered standings."""
    return _generate_odds_from_standings(
        standings, SOFTMAX_TEMPERATURE_CONFERENCE, MARGIN_CONFERENCE
    )


def generate_division_odds(standings: list) -> list[dict]:
    """Generate division winner odds from division-filtered standings (4 teams)."""
    return _generate_odds_from_standings(
        standings, SOFTMAX_TEMPERATURE_DIVISION, MARGIN_DIVISION
    )


def _current_season() -> int:
    """NFL: season = the year the season starts in."""
    today = timezone.now().date()
    return today.year if today.month >= 9 else today.year - 1


def generate_futures_odds(
    season: int | None = None,
    market_type: str = "SUPER_BOWL",
    division: str = "",
    conference: str = "",
) -> list[dict]:
    """
    Generate futures odds for a given market type and season.

    Returns list of dicts: [{"team_id": int, "odds": int}, ...]
    """
    if season is None:
        season = _current_season()

    qs = Standing.objects.filter(season=season).select_related("team")

    if market_type == "DIVISION" and division:
        qs = qs.filter(division=division)
    elif market_type in ("AFC_CHAMPION", "NFC_CHAMPION") and conference:
        qs = qs.filter(conference=conference)
    elif market_type == "AFC_CHAMPION":
        qs = qs.filter(conference=Conference.AFC)
    elif market_type == "NFC_CHAMPION":
        qs = qs.filter(conference=Conference.NFC)

    standings = list(qs)

    if not standings:
        logger.warning("generate_futures_odds: no standings for season %s", season)
        return []

    if market_type == "SUPER_BOWL":
        results = generate_super_bowl_odds(standings)
    elif market_type in ("AFC_CHAMPION", "NFC_CHAMPION"):
        results = generate_conference_odds(standings)
    elif market_type == "DIVISION":
        results = generate_division_odds(standings)
    else:
        logger.error("generate_futures_odds: unknown market_type %s", market_type)
        return []

    logger.info(
        "generate_futures_odds: %d outcomes for %s (season %s)",
        len(results),
        market_type,
        season,
    )
    return results
