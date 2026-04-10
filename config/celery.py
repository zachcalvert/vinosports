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
        "vinosports.core",
        "vinosports.activity",
        "vinosports.betting",
        "vinosports.bots",
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
        "reddit",
        "nfl.games",
        "nfl.betting",
        "nfl.bots",
        "nfl.discussions",
        "nfl.activity",
        "nfl.website",
        "worldcup.matches",
        "worldcup.betting",
        "worldcup.bots",
        "worldcup.discussions",
        "worldcup.activity",
        "worldcup.website",
        "ucl.matches",
        "ucl.betting",
        "ucl.bots",
        "ucl.discussions",
        "ucl.activity",
        "ucl.website",
    ]
)
app.autodiscover_tasks(
    ["epl.website", "nba.website", "worldcup.website", "ucl.website"],
    related_name="challenge_tasks",
)
