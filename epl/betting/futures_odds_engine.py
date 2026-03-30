"""
Futures odds engine — generates realistic decimal odds for EPL season-level
markets (Winner, Top 4, Relegation) based on league standings.
"""

import logging
import math
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

from epl.matches.models import Standing

logger = logging.getLogger(__name__)

# --- Constants ---
PPG_WEIGHT = 0.60
POSITION_WEIGHT = 0.40
GOAL_DIFF_BONUS = 0.10  # extra weight for goal difference in title races

MARGIN_WINNER = 0.15  # ~115% book for 20-team winner market
MARGIN_TOP_4 = 0.10  # ~110% for binary yes/no per team
MARGIN_RELEGATION = 0.12

SOFTMAX_TEMPERATURE_WINNER = 1.8  # lower = more concentrated on favorites
SOFTMAX_TEMPERATURE_TOP_4 = 2.5  # higher = more spread out
SOFTMAX_TEMPERATURE_RELEGATION = 1.8

MIN_ODDS = Decimal("1.50")
MAX_ODDS = Decimal("500.00")
TWO_PLACES = Decimal("0.01")


def _team_strength(standing) -> float:
    """Compute team strength from standings (0.0-1.0 scale)."""
    played = max(standing.played, 1)
    ppg = standing.points / played
    ppg_norm = ppg / 3.0  # max 3 PPG
    pos_rating = (21 - standing.position) / 20.0  # pos 1 = 1.0, pos 20 = 0.05
    return PPG_WEIGHT * ppg_norm + POSITION_WEIGHT * pos_rating


def _title_strength(standing) -> float:
    """Enhanced strength for title race — adds goal difference and points gap."""
    base = _team_strength(standing)
    played = max(standing.played, 1)
    # Normalize goal difference: +40 GD in 38 games ≈ elite
    gd_norm = max(0.0, min(1.0, (standing.goal_difference / played + 1.0) / 2.0))
    return base + GOAL_DIFF_BONUS * gd_norm


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


def _prob_to_decimal_odds(prob: float) -> Decimal:
    """Convert implied probability to decimal odds, clamped."""
    if prob <= 0:
        return MAX_ODDS
    raw = Decimal(str(1.0 / prob))
    clamped = max(MIN_ODDS, min(MAX_ODDS, raw))
    return clamped.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def generate_winner_odds(standings: list) -> list[dict]:
    """Generate title winner odds from standings."""
    if not standings:
        return []

    strengths = [_title_strength(s) for s in standings]
    probs = _softmax(strengths, SOFTMAX_TEMPERATURE_WINNER)
    probs_with_margin = _apply_margin(probs, MARGIN_WINNER)

    return [
        {"team_id": s.team_id, "odds": _prob_to_decimal_odds(p)}
        for s, p in zip(standings, probs_with_margin)
    ]


def generate_top_4_odds(standings: list) -> list[dict]:
    """Generate Top 4 finish odds. Each team gets odds for finishing in positions 1-4."""
    if not standings:
        return []

    strengths = [_team_strength(s) for s in standings]
    probs = _softmax(strengths, SOFTMAX_TEMPERATURE_TOP_4)

    # Cumulative probability for finishing in top 4: sum of top-N slice
    # Approximate: top 4 probability is roughly 4x the individual win probability
    # but capped and adjusted for realism
    results = []
    for s, p in zip(standings, probs):
        top_4_prob = min(0.95, p * 4.0)  # rough approximation
        top_4_prob_vig = top_4_prob * (1.0 + MARGIN_TOP_4)
        results.append(
            {"team_id": s.team_id, "odds": _prob_to_decimal_odds(top_4_prob_vig)}
        )

    return results


def generate_relegation_odds(standings: list) -> list[dict]:
    """Generate relegation odds. Weakest teams get shortest odds."""
    if not standings:
        return []

    # Invert strengths: weakest teams have highest relegation probability
    strengths = [_team_strength(s) for s in standings]
    inverted = [1.0 - s for s in strengths]
    probs = _softmax(inverted, SOFTMAX_TEMPERATURE_RELEGATION)

    # 3 teams relegated: scale probabilities (each team's chance ≈ 3x individual prob)
    probs_scaled = [min(0.95, p * 3.0) for p in probs]
    probs_with_margin = _apply_margin(probs_scaled, MARGIN_RELEGATION)

    return [
        {"team_id": s.team_id, "odds": _prob_to_decimal_odds(p)}
        for s, p in zip(standings, probs_with_margin)
    ]


def generate_futures_odds(
    season: str | None = None, market_type: str = "WINNER"
) -> list[dict]:
    """
    Generate futures odds for all teams in a season.

    Returns list of dicts: [{"team_id": int, "odds": Decimal}, ...]
    """
    season = season or getattr(settings, "EPL_CURRENT_SEASON", "2025")
    standings = list(Standing.objects.filter(season=season).select_related("team"))

    if not standings:
        logger.warning("generate_futures_odds: no standings for season %s", season)
        return []

    generators = {
        "WINNER": generate_winner_odds,
        "TOP_4": generate_top_4_odds,
        "RELEGATION": generate_relegation_odds,
    }

    generator = generators.get(market_type)
    if not generator:
        logger.error("generate_futures_odds: unknown market_type %s", market_type)
        return []

    results = generator(standings)
    logger.info(
        "generate_futures_odds: %d outcomes for %s (season %s)",
        len(results),
        market_type,
        season,
    )
    return results
