"""
Preseason power rankings for NFL futures odds during the offseason.

When no standings exist for the target season (i.e. the offseason), the futures
odds engine falls back to these rankings to generate realistic odds.  Update
this file each offseason with the latest consensus power rankings.
"""

# Which upcoming season these rankings target.
RANKINGS_SEASON = 2026

# 1 = best, 32 = worst.  Keyed by Team.abbreviation.
PRESEASON_POWER_RANKINGS: dict[str, int] = {
    "SEA": 1,
    "LAR": 2,
    "BUF": 3,
    "NE": 4,
    "JAX": 5,
    "KC": 6,
    "DET": 7,
    "PHI": 8,
    "BAL": 9,
    "MIN": 10,
    "GB": 11,
    "WAS": 12,
    "PIT": 13,
    "CIN": 14,
    "DEN": 15,
    "TB": 16,
    "HOU": 17,
    "LAC": 18,
    "SF": 19,
    "ATL": 20,
    "DAL": 21,
    "ARI": 22,
    "NO": 23,
    "IND": 24,
    "CHI": 25,
    "NYJ": 26,
    "TEN": 27,
    "CAR": 28,
    "NYG": 29,
    "LV": 30,
    "MIA": 31,
    "CLE": 32,
}


def rank_to_strength(rank: int, total: int = 32) -> float:
    """Convert a 1-based power rank to a 0.0–1.0 strength score.

    Rank 1 → 1.0, rank 32 → 0.0.  Same scale as
    ``_championship_strength()`` in the odds engine.
    """
    return 1.0 - (rank - 1) / (total - 1)
