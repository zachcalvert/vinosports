import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-change-me-in-production")

DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS", "localhost,127.0.0.1,vinosports.local"
).split(",")

CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "http://vinosports.local"
).split(",")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "django_htmx",
    # Shared apps from vinosports-core
    "vinosports.core",
    "vinosports.users",
    "vinosports.betting",
    "vinosports.challenges",
    "vinosports.rewards",
    "vinosports.bots",
    # Hub
    "hub",
    # EPL
    "epl.matches",
    "epl.betting",
    "epl.bots",
    "epl.discussions",
    "epl.activity",
    "epl.rewards",
    "epl.website",
    # NBA
    "nba.games",
    "nba.betting",
    "nba.bots",
    "nba.discussions",
    "nba.activity",
    "nba.rewards",
    "nba.website",
    # NFL
    "nfl.games",
    "nfl.betting",
    "nfl.bots",
    "nfl.discussions",
    "nfl.activity",
    "nfl.website",
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
    "config.middleware.LeagueMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            # NBA project-level templates (base, dashboard, components)
            BASE_DIR / "nba" / "templates",
            # Shared templates from vinosports-core (volume mount in dev, site-packages in prod)
            *(
                [Path("/packages/vinosports-core/src/vinosports/templates")]
                if Path("/packages/vinosports-core/src/vinosports/templates").is_dir()
                else [Path(__import__("vinosports").__path__[0]) / "templates"]
            ),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "vinosports.context_processors.global_nav",
                # Hub
                "hub.context_processors.league_urls",
                # EPL (guarded by request.league)
                "epl.website.context_processors.theme",
                "epl.betting.context_processors.bankruptcy",
                "epl.betting.context_processors.parlay_slip",
                "epl.betting.context_processors.futures_sidebar",
                "epl.rewards.context_processors.unseen_rewards",
                "epl.activity.context_processors.activity_toasts",
                # NBA (guarded by request.league)
                "nba.website.context_processors.theme",
                "nba.betting.context_processors.bankruptcy",
                "nba.betting.context_processors.parlay_slip",
                "nba.betting.context_processors.futures_sidebar",
                "nba.rewards.context_processors.unseen_rewards",
                "nba.activity.context_processors.activity_toasts",
            ],
        },
    },
]

ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default="postgres://{user}:{password}@{host}:{port}/{name}".format(
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", ""),
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
            name=os.environ.get("DB_NAME", "vinosports"),
        )
    )
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

MEDIA_ROOT = BASE_DIR / "media"

# Media storage: Tigris (S3-compatible) in production, local filesystem in dev
_S3_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL_S3", "")
if _S3_ENDPOINT:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    AWS_STORAGE_BUCKET_NAME = os.environ.get("BUCKET_NAME", "vinosports-media")
    AWS_S3_ENDPOINT_URL = _S3_ENDPOINT
    AWS_S3_REGION_NAME = os.environ.get("AWS_REGION", "auto")
    AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.fly.storage.tigris.dev"
    AWS_DEFAULT_ACL = "public-read"
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    AWS_QUERYSTRING_AUTH = False
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
else:
    MEDIA_URL = "media/"
STATICFILES_DIRS = []

# EPL and NBA project-level static (team logos, etc.)
for _static_dir in [BASE_DIR / "epl" / "static", BASE_DIR / "nba" / "static"]:
    if _static_dir.is_dir():
        STATICFILES_DIRS.append(_static_dir)

# Shared static assets from vinosports-core (volume mount in dev, site-packages in prod)
_core_static = Path("/packages/vinosports-core/src/vinosports/static")
if _core_static.is_dir():
    STATICFILES_DIRS.append(_core_static)
else:
    _pkg_static = Path(__import__("vinosports").__path__[0]) / "static"
    if _pkg_static.is_dir():
        STATICFILES_DIRS.append(_pkg_static)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# League URLs (for global nav)
LEAGUE_URLS = {
    "epl": {
        "name": "English Premier League",
        "short": "EPL",
        "url": "/epl/",
        "icon": "ph-duotone ph-soccer-ball",
        "status": "active",
        "description": "Place bets on Premier League matches, climb the leaderboard, and compete with AI-powered rivals.",
    },
    "nba": {
        "name": "NBA",
        "short": "NBA",
        "url": "/nba/",
        "icon": "ph-duotone ph-basketball",
        "status": "active",
        "description": "NBA betting simulation with game props, player stats, and playoff brackets.",
    },
    "nfl": {
        "name": "NFL",
        "short": "NFL",
        "url": None,
        "status": "coming_soon",
        "description": "NFL weekly picks, spreads, and survivor pools.",
        "icon": "ph-duotone ph-football",
    },
}

LOGIN_URL = "/login/"

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "epl.*": {"queue": "epl"},
    "nba.*": {"queue": "nba"},
}

# Beat Schedule — EPL and NBA tasks merged, prefixed to avoid key collisions
CELERY_BEAT_SCHEDULE = {
    # ===== EPL =====
    # --- Data ingestion ---
    "epl-fetch-teams-monthly": {
        "task": "epl.matches.tasks.fetch_teams",
        "schedule": crontab(hour=3, minute=0, day_of_month=1),
    },
    "epl-fetch-fixtures-daily": {
        "task": "epl.matches.tasks.fetch_fixtures",
        "schedule": crontab(hour=3, minute=0),
    },
    "epl-fetch-standings-daily-midweek": {
        "task": "epl.matches.tasks.fetch_standings",
        "schedule": crontab(hour=3, minute=0, day_of_week="tue,wed,thu"),
    },
    "epl-fetch-standings-3h-matchdays": {
        "task": "epl.matches.tasks.fetch_standings",
        "schedule": crontab(
            hour="0,3,6,9,12,15,18,21", minute=0, day_of_week="fri,sat,sun,mon"
        ),
    },
    "epl-fetch-live-scores-5m-on-matchdays": {
        "task": "epl.matches.tasks.fetch_live_scores",
        "schedule": crontab(minute="*/5", hour="11-23", day_of_week="fri,sat,sun,mon"),
    },
    "epl-prefetch-hype-data-6h": {
        "task": "epl.matches.tasks.prefetch_upcoming_hype_data",
        "schedule": timedelta(hours=6),
    },
    # --- EPL Odds ---
    "epl-generate-odds-10m": {
        "task": "epl.betting.tasks.generate_odds",
        "schedule": timedelta(minutes=10),
    },
    # --- EPL Futures ---
    "epl-update-futures-odds-hourly": {
        "task": "epl.betting.tasks.update_futures_odds",
        "schedule": crontab(minute=30),
    },
    # --- EPL Challenges ---
    "epl-rotate-daily-challenges": {
        "task": "epl.website.challenge_tasks.rotate_daily_challenges",
        "schedule": crontab(hour=5, minute=0),
    },
    "epl-rotate-weekly-challenges": {
        "task": "epl.website.challenge_tasks.rotate_weekly_challenges",
        "schedule": crontab(hour=4, minute=0, day_of_week="friday"),
    },
    "epl-expire-challenges-30m": {
        "task": "epl.website.challenge_tasks.expire_challenges",
        "schedule": timedelta(minutes=30),
    },
    # --- EPL Bots ---
    "epl-run-bot-strategies-hourly": {
        "task": "epl.bots.tasks.run_bot_strategies",
        "schedule": crontab(minute=5),
    },
    "epl-generate-featured-parlays-weekly": {
        "task": "epl.bots.tasks.generate_featured_parlays",
        "schedule": crontab(hour=8, minute=0, day_of_week="friday"),
    },
    "epl-generate-prematch-comments-hourly": {
        "task": "epl.bots.tasks.generate_prematch_comments",
        "schedule": crontab(minute=15),
    },
    "epl-generate-postmatch-comments-hourly": {
        "task": "epl.bots.tasks.generate_postmatch_comments",
        "schedule": crontab(minute=30),
    },
    # --- EPL Activity ---
    "epl-broadcast-activity-event-20s": {
        "task": "epl.activity.tasks.broadcast_next_activity_event",
        "schedule": timedelta(seconds=20),
    },
    "epl-cleanup-old-activity-events-daily": {
        "task": "epl.activity.tasks.cleanup_old_activity_events",
        "schedule": crontab(hour=4, minute=30),
    },
    # ===== NBA =====
    # --- Data ingestion ---
    "nba-fetch-teams-monthly": {
        "task": "nba.games.tasks.fetch_teams",
        "schedule": crontab(hour=3, minute=0, day_of_month=1),
    },
    "nba-fetch-schedule-daily": {
        "task": "nba.games.tasks.fetch_schedule",
        "schedule": crontab(hour=6, minute=0),
    },
    "nba-fetch-standings-morning": {
        "task": "nba.games.tasks.fetch_standings",
        "schedule": crontab(hour=8, minute=0),
    },
    "nba-fetch-standings-postgame": {
        "task": "nba.games.tasks.fetch_standings",
        "schedule": crontab(hour=2, minute=0),
    },
    "nba-fetch-live-scores-2m": {
        "task": "nba.games.tasks.fetch_live_scores",
        "schedule": crontab(minute="*/2", hour="17-23,0-5"),
    },
    # --- NBA Odds ---
    "nba-generate-odds-10m": {
        "task": "nba.betting.tasks.generate_odds",
        "schedule": timedelta(minutes=10),
    },
    # --- NBA Futures ---
    "nba-update-futures-odds-hourly": {
        "task": "nba.betting.tasks.update_futures_odds",
        "schedule": crontab(minute=45),
    },
    # --- NBA Settlement ---
    "nba-settle-pending-bets-5m": {
        "task": "nba.betting.tasks.settle_pending_bets",
        "schedule": crontab(minute="*/5", hour="19-23,0-2"),
    },
    # --- NBA Bots ---
    "nba-run-bot-strategies-hourly": {
        "task": "nba.bots.tasks.run_bot_strategies",
        "schedule": crontab(minute=5),
    },
    "nba-generate-featured-parlays-daily": {
        "task": "nba.bots.tasks.generate_featured_parlays",
        "schedule": crontab(hour=10, minute=0),
    },
    "nba-generate-pregame-comments-hourly": {
        "task": "nba.discussions.tasks.generate_pregame_comments",
        "schedule": crontab(minute=15),
    },
    "nba-generate-postgame-comments-hourly": {
        "task": "nba.discussions.tasks.generate_postgame_comments",
        "schedule": crontab(minute=30),
    },
    # --- NBA Activity ---
    "nba-broadcast-activity-event-20s": {
        "task": "nba.activity.tasks.broadcast_next_activity_event",
        "schedule": timedelta(seconds=20),
    },
    "nba-cleanup-old-activity-events-daily": {
        "task": "nba.activity.tasks.cleanup_old_activity_events",
        "schedule": crontab(hour=5, minute=0),
    },
    # --- NBA Challenges ---
    "nba-rotate-daily-challenges": {
        "task": "nba.website.challenge_tasks.rotate_daily_challenges",
        "schedule": crontab(hour=6, minute=30),
    },
    "nba-rotate-weekly-challenges": {
        "task": "nba.website.challenge_tasks.rotate_weekly_challenges",
        "schedule": crontab(hour=6, minute=30, day_of_week="monday"),
    },
    "nba-expire-challenges-30m": {
        "task": "nba.website.challenge_tasks.expire_challenges",
        "schedule": timedelta(minutes=30),
    },
    # ===== Cross-league =====
    "expire-featured-parlays-30m": {
        "task": "vinosports.betting.tasks.expire_featured_parlays",
        "schedule": timedelta(minutes=30),
    },
}

# External APIs
BDL_API_KEY = os.environ.get("BDL_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_TIMEOUT = 30

# EPL-specific
EPL_CURRENT_SEASON = "2025"

# --- Production security ---
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# --- Sentry ---
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=True,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment="production" if not DEBUG else "development",
    )
