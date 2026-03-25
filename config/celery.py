import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("vinosports")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(
    [
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
    ]
)
