"""
Algorithmic odds engine — generates realistic NBA odds (moneyline, spread, totals)
in American format based on standings (win%, conference rank, home/away records).
"""

import logging

from django.utils import timezone
from games.models import Game, GameStatus, Standing

logger = logging.getLogger(__name__)

# --- Constants ---
WIN_PCT_WEIGHT = 0.60
RANK_WEIGHT = 0.40
RECORD_BLEND = 0.30  # weight for home/away record split vs overall strength

HOME_COURT_ADVANTAGE = 0.03  # ~3 pct-pts added to home win probability
MARGIN = 0.05  # 5% bookmaker vig

BASE_TOTAL = 222.0  # league-average total points
TOTAL_SWING = 15.0  # max adjustment from base total
SPREAD_FACTOR = 30.0  # win-prob differential → point spread

STANDARD_JUICE = -110
MIN_ML = -800
MAX_ML = 800
MIN_TOTAL = 195.0
MAX_TOTAL = 250.0

FALLBACK_WIN_PCT = 0.500
BOOKMAKER = "House"


def _parse_record(record_str: str) -> tuple[int, int]:
    """Parse '25-10' → (25, 10). Returns (0, 0) on bad input."""
    if not record_str or "-" not in record_str:
        return (0, 0)
    try:
        parts = record_str.split("-")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


def _team_strength(standing) -> float:
    """Blend win% (0.6) + normalised conference rank (0.4) → 0.0–1.0."""
    win_pct = float(standing.win_pct) if standing.win_pct else FALLBACK_WIN_PCT
    rank = standing.conference_rank or 8
    rank_score = (16 - rank) / 15.0  # rank 1 → 1.0, rank 15 → 0.067
    return WIN_PCT_WEIGHT * win_pct + RANK_WEIGHT * rank_score


def _win_probability(home_standing, away_standing) -> float:
    """
    Compute home-win probability from standings.
    Blends overall strength with home/away record splits, adds home-court edge.
    """
    h_str = _team_strength(home_standing) if home_standing else FALLBACK_WIN_PCT
    a_str = _team_strength(away_standing) if away_standing else FALLBACK_WIN_PCT

    # Blend in home/away record splits when available
    if home_standing and home_standing.home_record:
        hw, hl = _parse_record(home_standing.home_record)
        if hw + hl > 0:
            h_home_pct = hw / (hw + hl)
            h_str = (1 - RECORD_BLEND) * h_str + RECORD_BLEND * h_home_pct

    if away_standing and away_standing.away_record:
        aw, al = _parse_record(away_standing.away_record)
        if aw + al > 0:
            a_away_pct = aw / (aw + al)
            a_str = (1 - RECORD_BLEND) * a_str + RECORD_BLEND * a_away_pct

    # Home-court advantage
    h_str += HOME_COURT_ADVANTAGE

    total = h_str + a_str
    if total == 0:
        return 0.5

    p_home = h_str / total
    return max(0.05, min(0.95, p_home))


def _probability_to_american(prob: float) -> int:
    """Convert an implied probability (0–1) to American odds."""
    if prob <= 0 or prob >= 1:
        return -110  # safe fallback
    decimal_odds = 1.0 / prob
    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1) * 100))
    else:
        return int(round(-100 / (decimal_odds - 1)))


def _moneyline(p_home: float) -> tuple[int, int]:
    """Generate moneyline odds from home-win probability, with margin applied."""
    p_away = 1.0 - p_home
    # Apply margin (overround)
    p_home_vig = p_home * (1 + MARGIN)
    p_away_vig = p_away * (1 + MARGIN)

    home_ml = _probability_to_american(p_home_vig)
    away_ml = _probability_to_american(p_away_vig)

    home_ml = max(MIN_ML, min(MAX_ML, home_ml))
    away_ml = max(MIN_ML, min(MAX_ML, away_ml))
    return (home_ml, away_ml)


def _spread(p_home: float) -> tuple[float, int, int]:
    """
    Derive point spread from win probability.
    Negative spread_line = home is favored.
    """
    raw = -(p_home - 0.5) * SPREAD_FACTOR  # negative when home favored
    spread_line = round(raw * 2) / 2  # round to nearest 0.5
    return (spread_line, STANDARD_JUICE, STANDARD_JUICE)


def _total(home_standing, away_standing) -> tuple[float, int, int]:
    """Derive over/under total from team strengths."""
    h_str = _team_strength(home_standing) if home_standing else FALLBACK_WIN_PCT
    a_str = _team_strength(away_standing) if away_standing else FALLBACK_WIN_PCT

    adjustment = (h_str + a_str - 1.0) * TOTAL_SWING
    total_line = BASE_TOTAL + adjustment
    total_line = round(total_line * 2) / 2  # round to nearest 0.5
    total_line = max(MIN_TOTAL, min(MAX_TOTAL, total_line))
    return (total_line, STANDARD_JUICE, STANDARD_JUICE)


def generate_game_odds(home_standing, away_standing) -> dict:
    """
    Generate all NBA odds for a single game.
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


def generate_all_upcoming_odds(season: int | None = None) -> list[dict]:
    """
    Generate House odds for all SCHEDULED games in a season.
    Returns list of dicts with 'game' key + odds fields.
    """
    if season is None:
        today = timezone.now().date()
        season = today.year + 1 if today.month >= 10 else today.year

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
