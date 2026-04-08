import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def fetch_teams(self):
    """Sync UCL teams from BallDontLie."""
    from ucl.matches.services import sync_teams

    try:
        created, updated = sync_teams()
        logger.info("Teams sync: %d created, %d updated", created, updated)
    except Exception as exc:
        logger.error("Teams sync failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def fetch_matches(self):
    """Sync UCL matches from BallDontLie."""
    from ucl.matches.services import sync_matches

    try:
        created, updated = sync_matches()
        logger.info("Matches sync: %d created, %d updated", created, updated)
    except Exception as exc:
        logger.error("Matches sync failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def fetch_standings(self):
    """Sync UCL league phase standings from BallDontLie."""
    from ucl.matches.services import sync_standings

    try:
        created, updated = sync_standings()
        logger.info("Standings sync: %d created, %d updated", created, updated)
    except Exception as exc:
        logger.error("Standings sync failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


@shared_task
def fetch_live_scores():
    """Poll for live UCL score updates and broadcast changes."""
    from ucl.matches.services import poll_live_scores

    poll_live_scores()
