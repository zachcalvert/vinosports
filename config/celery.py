import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("vinosports")
app.config_from_object("django.conf:settings", namespace="CELERY")
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
