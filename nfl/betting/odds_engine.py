"""
Algorithmic odds engine — generates realistic NFL odds (moneyline, spread, totals)
in American format based on standings (win%, point differential).

NFL-specific: key number snapping (3, 7, 10), lower totals (38-54), tighter spreads.
"""

import logging

from django.utils import timezone

from nfl.games.models import Game, GameStatus, Standing

logger = logging.getLogger(__name__)

# --- Constants ---
WIN_PCT_WEIGHT = 0.50
POINT_DIFF_WEIGHT = 0.50

HOME_FIELD_ADVANTAGE = 0.03  # ~3 pct-pts (NFL home field ~57%)
MARGIN = 0.05  # 5% bookmaker vig

BASE_TOTAL = 44.0  # NFL league-average total points
TOTAL_SWING = 8.0  # max adjustment from base total
SPREAD_FACTOR = 28.0  # win-prob differential → point spread (NFL tighter than NBA)

STANDARD_JUICE = -110
MIN_ML = -600
MAX_ML = 600
MIN_TOTAL = 35.0
MAX_TOTAL = 60.0

FALLBACK_WIN_PCT = 0.500
BOOKMAKER = "House"

# NFL key numbers — spreads snap to these when the raw value is close
KEY_NUMBERS = {3: 1.0, 7: 0.8, 10: 0.5}  # number: snap radius


def _norm_point_diff(standing) -> float:
    """Normalise point differential to 0.0–1.0 scale."""
    pd = standing.point_differential
    # NFL point differentials typically range -200 to +200 over 17 games
    return max(0.0, min(1.0, (pd + 200) / 400))


def _team_strength(standing) -> float:
    """Blend win% (0.5) + normalised point differential (0.5) → 0.0–1.0."""
    win_pct = float(standing.win_pct) if standing.win_pct else FALLBACK_WIN_PCT
    pd_score = _norm_point_diff(standing)
    return WIN_PCT_WEIGHT * win_pct + POINT_DIFF_WEIGHT * pd_score


def _win_probability(home_standing, away_standing) -> float:
    """Compute home-win probability from standings + home field advantage."""
    h_str = _team_strength(home_standing) if home_standing else FALLBACK_WIN_PCT
    a_str = _team_strength(away_standing) if away_standing else FALLBACK_WIN_PCT

    h_str += HOME_FIELD_ADVANTAGE

    total = h_str + a_str
    if total == 0:
        return 0.5

    p_home = h_str / total
    return max(0.05, min(0.95, p_home))


def _probability_to_american(prob: float) -> int:
    """Convert an implied probability (0–1) to American odds."""
    if prob <= 0 or prob >= 1:
        return -110
    decimal_odds = 1.0 / prob
    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1) * 100))
    else:
        return int(round(-100 / (decimal_odds - 1)))


def _moneyline(p_home: float) -> tuple[int, int]:
    """Generate moneyline odds from home-win probability, with margin applied."""
    p_away = 1.0 - p_home
    p_home_vig = p_home * (1 + MARGIN)
    p_away_vig = p_away * (1 + MARGIN)

    home_ml = _probability_to_american(p_home_vig)
    away_ml = _probability_to_american(p_away_vig)

    home_ml = max(MIN_ML, min(MAX_ML, home_ml))
    away_ml = max(MIN_ML, min(MAX_ML, away_ml))
    return (home_ml, away_ml)


def _snap_to_key_number(raw_spread: float) -> float:
    """
    Snap raw spread to NFL key numbers (3, 7, 10) when close.
    Key numbers are the most common margins of victory in football.
    """
    abs_spread = abs(raw_spread)
    sign = -1 if raw_spread < 0 else 1

    for key, radius in KEY_NUMBERS.items():
        if abs(abs_spread - key) <= radius:
            return sign * float(key)

    # Not near a key number — round to nearest 0.5
    return round(raw_spread * 2) / 2


def _spread(p_home: float) -> tuple[float, int, int]:
    """
    Derive point spread from win probability.
    Negative spread_line = home is favored.
    Snaps to key numbers (3, 7, 10) when close.
    """
    raw = -(p_home - 0.5) * SPREAD_FACTOR
    spread_line = _snap_to_key_number(raw)
    return (spread_line, STANDARD_JUICE, STANDARD_JUICE)


def _total(home_standing, away_standing) -> tuple[float, int, int]:
    """Derive over/under total from combined team strength."""
    h_str = _team_strength(home_standing) if home_standing else FALLBACK_WIN_PCT
    a_str = _team_strength(away_standing) if away_standing else FALLBACK_WIN_PCT

    adjustment = (h_str + a_str - 1.0) * TOTAL_SWING
    total_line = BASE_TOTAL + adjustment
    total_line = round(total_line * 2) / 2  # round to nearest 0.5
    total_line = max(MIN_TOTAL, min(MAX_TOTAL, total_line))
    return (total_line, STANDARD_JUICE, STANDARD_JUICE)


def generate_game_odds(home_standing, away_standing) -> dict:
    """
    Generate all NFL odds for a single game.
    Returns dict matching the Odds model fields.
    """
    p_home = _win_probability(home_standing, away_standing)

    home_ml, away_ml = _moneyline(p_home)
    spread_line, spread_home, spread_away = _spread(p_home)
    total_line, over_odds, under_odds = _total(home_standing, away_standing)

    return {
        "home_moneyline": home_ml,
        "away_moneyline": away_ml,
        "spread_line": spread_line,
        "spread_home": spread_home,
        "spread_away": spread_away,
        "total_line": total_line,
        "over_odds": over_odds,
        "under_odds": under_odds,
    }


def _current_season() -> int:
    """NFL: season = the year the season starts in."""
    today = timezone.now().date()
    return today.year if today.month >= 9 else today.year - 1


def generate_all_upcoming_odds(season: int | None = None) -> list[dict]:
    """
    Generate House odds for all SCHEDULED games in a season.
    Returns list of dicts with 'game' key + odds fields.
    """
    if season is None:
        season = _current_season()

    games = (
        Game.objects.filter(season=season, status=GameStatus.SCHEDULED)
        .select_related("home_team", "away_team")
        .order_by("game_date")
    )

    standings_map = {s.team_id: s for s in Standing.objects.filter(season=season)}

    results = []
    for game in games:
        home_standing = standings_map.get(game.home_team_id)
        away_standing = standings_map.get(game.away_team_id)
        odds = generate_game_odds(home_standing, away_standing)
        results.append({"game": game, **odds})

    logger.info(
        "generate_all_upcoming_odds: %d games (season %s)", len(results), season
    )
    return results
