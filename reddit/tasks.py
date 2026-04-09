import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def fetch_subreddit_snapshots(self):
    """Fetch hot posts for all configured subreddits. Runs twice daily (6am + 2pm ET)."""
    from .service import fetch_all_snapshots

    try:
        count = fetch_all_snapshots()
        return {"status": "ok", "snapshots_created": count}
    except Exception as exc:
        logger.exception("Subreddit snapshot fetch failed")
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@shared_task
def purge_old_snapshots():
    """Delete snapshots older than 7 days. Runs daily."""
    from .service import purge_old_snapshots as purge

    deleted = purge(days=7)
    return {"status": "ok", "deleted": deleted}
