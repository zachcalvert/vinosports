"""
Futures odds engine — generates realistic American odds for NBA season-level
markets (Champion, Conference Winner) based on standings.
"""

import logging
import math

from django.utils import timezone

from nba.games.models import Standing

logger = logging.getLogger(__name__)

# --- Constants ---
WIN_PCT_WEIGHT = 0.50
RANK_WEIGHT = 0.30
ROAD_WEIGHT = 0.20  # teams with strong road records are battle-tested

MARGIN_CHAMPION = 0.30  # ~130% book for 30-team champion market
MARGIN_CONFERENCE = 0.20  # ~120% for 15-team conference market

SOFTMAX_TEMPERATURE_CHAMPION = 2.0
SOFTMAX_TEMPERATURE_CONFERENCE = 1.8

FALLBACK_WIN_PCT = 0.500
MIN_ODDS = -500
MAX_ODDS = 10000


def _parse_record(record_str: str) -> tuple[int, int]:
    """Parse '25-10' -> (25, 10). Returns (0, 0) on bad input."""
    if not record_str or "-" not in record_str:
        return (0, 0)
    try:
        parts = record_str.split("-")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


def _championship_strength(standing) -> float:
    """Compute championship strength from standings (0.0-1.0+ scale)."""
    win_pct = float(standing.win_pct) if standing.win_pct else FALLBACK_WIN_PCT
    rank = standing.conference_rank or 8
    rank_score = (16 - rank) / 15.0

    base = WIN_PCT_WEIGHT * win_pct + RANK_WEIGHT * rank_score

    # Blend in road record (strong road teams perform better in playoffs)
    if standing.away_record:
        aw, al = _parse_record(standing.away_record)
        if aw + al > 0:
            road_pct = aw / (aw + al)
            base += ROAD_WEIGHT * road_pct

    return base


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
        return 10000  # long shot fallback
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


def generate_champion_odds(standings: list) -> list[dict]:
    """Generate NBA Champion odds from all team standings."""
    if not standings:
        return []

    strengths = [_championship_strength(s) for s in standings]
    probs = _softmax(strengths, SOFTMAX_TEMPERATURE_CHAMPION)
    probs_with_margin = _apply_margin(probs, MARGIN_CHAMPION)

    return [
        {"team_id": s.team_id, "odds": _clamp_american(_probability_to_american(p))}
        for s, p in zip(standings, probs_with_margin)
    ]


def generate_conference_odds(standings: list) -> list[dict]:
    """Generate conference winner odds from conference-filtered standings."""
    if not standings:
        return []

    strengths = [_championship_strength(s) for s in standings]
    probs = _softmax(strengths, SOFTMAX_TEMPERATURE_CONFERENCE)
    probs_with_margin = _apply_margin(probs, MARGIN_CONFERENCE)

    return [
        {"team_id": s.team_id, "odds": _clamp_american(_probability_to_american(p))}
        for s, p in zip(standings, probs_with_margin)
    ]


def generate_futures_odds(
    season: int | None = None, market_type: str = "CHAMPION", conference: str = ""
) -> list[dict]:
    """
    Generate futures odds for all teams in a season.

    Returns list of dicts: [{"team_id": int, "odds": int}, ...]
    """
    if season is None:
        today = timezone.now().date()
        season = today.year if today.month >= 10 else today.year - 1

    qs = Standing.objects.filter(season=season).select_related("team")
    if market_type == "CONFERENCE" and conference:
        qs = qs.filter(conference=conference)

    standings = list(qs)

    if not standings:
        logger.warning("generate_futures_odds: no standings for season %s", season)
        return []

    if market_type == "CHAMPION":
        results = generate_champion_odds(standings)
    elif market_type == "CONFERENCE":
        results = generate_conference_odds(standings)
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
