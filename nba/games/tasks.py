import logging

from celery import shared_task

from nba.games.services import (
    sync_games,
    sync_live_scores,
    sync_players,
    sync_standings,
    sync_teams,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_teams(self):
    """Sync all NBA teams from the data API."""
    try:
        count = sync_teams()
        return {"synced": count}
    except Exception as exc:
        logger.error("fetch_teams failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_players(self):
    """Sync all NBA players from BallDontLie."""
    try:
        count = sync_players()
        return {"synced": count}
    except Exception as exc:
        logger.error("fetch_players failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_schedule(self, season: int | None = None):
    """Sync full game schedule for a season (defaults to current)."""
    if season is None:
        season = _current_season()
    try:
        count = sync_games(season)
        return {"synced": count, "season": season}
    except Exception as exc:
        logger.error("fetch_schedule failed (season=%s): %s", season, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_standings(self, season: int | None = None):
    """Sync conference standings for a season."""
    if season is None:
        season = _current_season()
    try:
        count = sync_standings(season)
        return {"synced": count, "season": season}
    except Exception as exc:
        logger.error("fetch_standings failed (season=%s): %s", season, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def fetch_live_scores(self):
    """Update scores for all currently in-progress games."""
    try:
        count = sync_live_scores()
        return {"updated": count}
    except Exception as exc:
        logger.error("fetch_live_scores failed: %s", exc)
        raise self.retry(exc=exc)


def _current_season() -> int:
    """Return the BDL season year for the current NBA season.

    BDL uses the *start* year: the 2025-26 season is labelled "2025".
    Oct-Dec → current calendar year; Jan-Sep → previous calendar year.
    """
    from nba.games.services import today_et

    today = today_et()
    if today.month >= 10:
        return today.year
    return today.year - 1
