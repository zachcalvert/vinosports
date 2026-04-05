import logging
import os

from celery import Celery
from celery.signals import after_setup_logger

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("vinosports")
app.config_from_object("django.conf:settings", namespace="CELERY")


class _ActivityBroadcastFilter(logging.Filter):
    """Suppress INFO-level Celery logs for the high-frequency activity broadcast tasks."""

    def filter(self, record):
        if record.levelno >= logging.WARNING:
            return True
        return "broadcast_next_activity_event" not in record.getMessage()


@after_setup_logger.connect
def _quiet_activity_broadcasts(logger, **kwargs):
    logger.addFilter(_ActivityBroadcastFilter())


app.conf.beat_schedule = {
    "dismiss-expired-notifications": {
        "task": "vinosports.activity.tasks.dismiss_expired_notifications",
        "schedule": 3600.0,  # Every hour
    },
}

app.autodiscover_tasks(
    [
        "vinosports.activity",
        "vinosports.betting",
        "epl.matches",
        "epl.betting",
        "epl.bots",
        "epl.discussions",
        "epl.activity",
        "epl.rewards",
        "epl.website",
        "nba.games",
        "nba.betting",
        "nba.bots",
        "nba.discussions",
        "nba.activity",
        "nba.rewards",
        "nba.website",
        "news",
        "nfl.games",
        "nfl.betting",
        "nfl.bots",
        "nfl.discussions",
        "nfl.activity",
        "nfl.website",
    ]
)
app.autodiscover_tasks(
    ["epl.website", "nba.website"],
    related_name="challenge_tasks",
)
