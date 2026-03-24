import os
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-change-me-in-production")

DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Shared apps from vinosports-core
    "vinosports.core",
    "vinosports.users",
    "vinosports.betting",
    "vinosports.challenges",
    "vinosports.rewards",
    # League-specific apps
    "matches",
    "betting",
    "bots",
    "discussions",
    "activity",
    "website",
]

AUTH_USER_MODEL = "users.User"

MIDDLEWARE = [
    "vinosports.middleware.BotScannerBlockMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "website.context_processors.hub_url",
                "website.context_processors.theme",
                "betting.context_processors.bankruptcy",
                "betting.context_processors.parlay_slip",
                "rewards.context_processors.unseen_rewards",
                "activity.context_processors.activity_toasts",
            ],
        },
    },
]

ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "vinosports"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_DEFAULT_QUEUE = "epl"

# Beat Schedule
# - Data ingestion runs at off-peak UTC hours (3-5am)
# - Live/matchday tasks scoped to Fri-Mon windows (typical EPL schedule)
# - Interval tasks (odds, activity) run continuously
# - Bot/challenge tasks on predictable daily/weekly cadence
CELERY_BEAT_SCHEDULE = {
    # --- Data ingestion ---
    "fetch-teams-monthly": {
        "task": "matches.tasks.fetch_teams",
        "schedule": crontab(hour=3, minute=0, day_of_month=1),
    },
    "fetch-fixtures-daily": {
        "task": "matches.tasks.fetch_fixtures",
        "schedule": crontab(hour=3, minute=0),
    },
    "fetch-standings-daily-midweek": {
        "task": "matches.tasks.fetch_standings",
        "schedule": crontab(hour=3, minute=0, day_of_week="tue,wed,thu"),
    },
    "fetch-standings-3h-matchdays": {
        "task": "matches.tasks.fetch_standings",
        "schedule": crontab(
            hour="0,3,6,9,12,15,18,21", minute=0, day_of_week="fri,sat,sun,mon"
        ),
    },
    "fetch-live-scores-5m-on-matchdays": {
        "task": "matches.tasks.fetch_live_scores",
        "schedule": crontab(minute="*/5", hour="11-23", day_of_week="fri,sat,sun,mon"),
    },
    "prefetch-hype-data-6h": {
        "task": "matches.tasks.prefetch_upcoming_hype_data",
        "schedule": timedelta(hours=6),
    },
    # --- Odds ---
    "generate-odds-10m": {
        "task": "betting.tasks.generate_odds",
        "schedule": timedelta(minutes=10),
    },
    # --- Challenges ---
    "rotate-daily-challenges": {
        "task": "challenges.tasks.rotate_daily_challenges",
        "schedule": crontab(hour=5, minute=0),
    },
    "rotate-weekly-challenges": {
        "task": "challenges.tasks.rotate_weekly_challenges",
        "schedule": crontab(hour=4, minute=0, day_of_week="friday"),
    },
    "expire-challenges-30m": {
        "task": "challenges.tasks.expire_challenges",
        "schedule": timedelta(minutes=30),
    },
    # --- Bots ---
    "run-bot-strategies-daily-thu-sat": {
        "task": "bots.tasks.run_bot_strategies",
        "schedule": crontab(hour=8, minute=0, day_of_week="thu,fri,sat"),
    },
    "generate-prematch-comments-2h-thu-sat": {
        "task": "bots.tasks.generate_prematch_comments",
        "schedule": crontab(
            hour="8,10,12,14,16,18,20,22", minute=0, day_of_week="thu,fri,sat"
        ),
    },
    "generate-postmatch-comments-30m-matchdays": {
        "task": "bots.tasks.generate_postmatch_comments",
        "schedule": crontab(minute="0,30", hour="14-23", day_of_week="fri,sat,sun,mon"),
    },
    # --- Activity feed ---
    "broadcast-activity-event-20s": {
        "task": "activity.tasks.broadcast_next_activity_event",
        "schedule": timedelta(seconds=20),
    },
    "cleanup-old-activity-events-daily": {
        "task": "activity.tasks.cleanup_old_activity_events",
        "schedule": crontab(hour=4, minute=30),
    },
}

# External APIs
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_TIMEOUT = 30
CURRENT_SEASON = "2025"

# Hub URL (for linking back to the homepage)
HUB_URL = os.environ.get("HUB_URL", "http://localhost:7999")

LOGIN_URL = HUB_URL + "/login/"
