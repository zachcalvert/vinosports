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
    "config.admin.VinoAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third-party
    "django_htmx",
    # Shared apps from vinosports-core
    "vinosports.core",
    "vinosports.users",
    "vinosports.betting",
    "vinosports.challenges",
    "vinosports.rewards",
    "vinosports.bots",
    "vinosports.activity",
    "vinosports.reactions",
    # Hub
    "hub",
    "news",
    "reddit",
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
    # World Cup
    "worldcup.matches",
    "worldcup.betting",
    "worldcup.bots",
    "worldcup.discussions",
    "worldcup.activity",
    "worldcup.rewards",
    "worldcup.website",
    # UCL
    "ucl.matches",
    "ucl.betting",
    "ucl.bots",
    "ucl.discussions",
    "ucl.activity",
    "ucl.rewards",
    "ucl.website",
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
    "vinosports.middleware.RateLimitMiddleware",
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
            # Project-level templates (admin overrides)
            BASE_DIR / "templates",
            # NBA project-level templates (base, dashboard, components)
            BASE_DIR / "nba" / "templates",
            # NFL project-level templates
            BASE_DIR / "nfl" / "templates",
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
                "vinosports.activity.context_processors.unread_notification_count",
                # Hub
                "hub.context_processors.league_urls",
                "news.context_processors.latest_articles",
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
                # NFL (guarded by request.league)
                "nfl.website.context_processors.theme",
                "nfl.betting.context_processors.bankruptcy",
                "nfl.betting.context_processors.parlay_slip",
                "nfl.betting.context_processors.futures_sidebar",
                "nfl.activity.context_processors.activity_toasts",
                # World Cup (guarded by request.league)
                "worldcup.website.context_processors.theme",
                "worldcup.betting.context_processors.bankruptcy",
                "worldcup.betting.context_processors.parlay_slip",
                "worldcup.betting.context_processors.futures_sidebar",
                "worldcup.rewards.context_processors.unseen_rewards",
                "worldcup.activity.context_processors.activity_toasts",
                # UCL (guarded by request.league)
                "ucl.website.context_processors.theme",
                "ucl.betting.context_processors.bankruptcy",
                "ucl.betting.context_processors.parlay_slip",
                "ucl.betting.context_processors.futures_sidebar",
                "ucl.rewards.context_processors.unseen_rewards",
                "ucl.activity.context_processors.activity_toasts",
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

# Anonymous rate limiting (per IP, league pages only)
RATE_LIMIT_REQUESTS = 20  # max requests per window
RATE_LIMIT_WINDOW = 60  # seconds

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_ROOT = BASE_DIR / "media"

# Media storage: Tigris (S3-compatible) in production, local filesystem in dev
_S3_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL_S3", "")
if _S3_ENDPOINT or os.environ.get("WHITENOISE_MANIFEST"):
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage"
            if _S3_ENDPOINT
            else "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
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
for _static_dir in [
    BASE_DIR / "epl" / "static",
    BASE_DIR / "nba" / "static",
    BASE_DIR / "nfl" / "static",
    BASE_DIR / "worldcup" / "static",
]:
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
        "url": "/nfl/",
        "status": "active",
        "description": "NFL weekly picks, spreads, and survivor pools.",
        "icon": "ph-duotone ph-football",
    },
    "worldcup": {
        "name": "FIFA World Cup 2026",
        "short": "WC",
        "url": "/worldcup/",
        "icon": "ph-duotone ph-globe",
        "status": "active",
        "description": "Bet on the 2026 FIFA World Cup — group stage, knockouts, and futures.",
    },
    "ucl": {
        "name": "UEFA Champions League",
        "short": "UCL",
        "url": "/ucl/",
        "icon": "ph-duotone ph-trophy",
        "status": "active",
        "description": "Bet on the Champions League — league phase, knockouts, and futures.",
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
    "nfl.*": {"queue": "nfl"},
    "news.*": {"queue": "news"},
    "reddit.*": {"queue": "default"},
    "worldcup.*": {"queue": "worldcup"},
    "ucl.*": {"queue": "ucl"},
}

# Beat Schedule — EPL and NBA tasks merged, prefixed to avoid key collisions
CELERY_BEAT_SCHEDULE = {
    # ===================================================================
    # Cross-league orchestrators (fan out to per-league subtasks)
    # ===================================================================
    "all-fetch-teams-monthly": {
        "task": "vinosports.core.tasks.all_fetch_teams",
        "schedule": crontab(hour=3, minute=0, day_of_month=1),
    },
    "all-generate-odds-10m": {
        "task": "vinosports.core.tasks.all_generate_odds",
        "schedule": timedelta(minutes=10),
    },
    "all-update-futures-odds-hourly": {
        "task": "vinosports.core.tasks.all_update_futures_odds",
        "schedule": crontab(minute=30),
    },
    "all-run-bot-strategies-hourly": {
        "task": "vinosports.core.tasks.all_run_bot_strategies",
        "schedule": crontab(minute=5),
    },
    "all-generate-prematch-comments-hourly": {
        "task": "vinosports.core.tasks.all_generate_prematch_comments",
        "schedule": crontab(minute=15),
    },
    "all-generate-featured-parlays-daily": {
        "task": "vinosports.core.tasks.all_generate_featured_parlays",
        "schedule": crontab(hour=9, minute=0),
    },
    "all-cleanup-activity-events-daily": {
        "task": "vinosports.core.tasks.all_cleanup_activity_events",
        "schedule": crontab(hour=4, minute=30),
    },
    "expire-featured-parlays-30m": {
        "task": "vinosports.betting.tasks.expire_featured_parlays",
        "schedule": timedelta(minutes=30),
    },
    # ===================================================================
    # Per-league data ingestion (different APIs/windows — can't consolidate)
    # ===================================================================
    # --- EPL ---
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
    # --- NBA ---
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
        "schedule": crontab(minute="*/2", hour="17-23,0-6"),
    },
    # --- NFL ---
    "nfl-fetch-schedule-daily": {
        "task": "nfl.games.tasks.fetch_schedule",
        "schedule": crontab(hour=6, minute=30),
    },
    "nfl-fetch-standings-morning": {
        "task": "nfl.games.tasks.fetch_standings",
        "schedule": crontab(hour=8, minute=30),
    },
    "nfl-fetch-standings-postgame": {
        "task": "nfl.games.tasks.fetch_standings",
        "schedule": crontab(hour=2, minute=30),
    },
    "nfl-fetch-live-scores-2m": {
        "task": "nfl.games.tasks.fetch_live_scores",
        "schedule": crontab(minute="*/2", hour="13-23,0-2", day_of_week="thu,sun,mon"),
    },
    # --- World Cup ---
    "wc-fetch-matches-daily": {
        "task": "worldcup.matches.tasks.fetch_matches",
        "schedule": crontab(hour=4, minute=30),
    },
    "wc-fetch-standings-4h": {
        "task": "worldcup.matches.tasks.fetch_standings",
        "schedule": crontab(hour="0,4,8,12,16,20", minute=0),
    },
    "wc-fetch-live-scores-2m": {
        "task": "worldcup.matches.tasks.fetch_live_scores",
        "schedule": crontab(minute="*/2", hour="10-23,0-2"),
    },
    # --- UCL ---
    "ucl-fetch-matches-daily": {
        "task": "ucl.matches.tasks.fetch_matches",
        "schedule": crontab(hour=4, minute=45),
    },
    "ucl-fetch-standings-4h": {
        "task": "ucl.matches.tasks.fetch_standings",
        "schedule": crontab(hour="0,4,8,12,16,20", minute=15),
    },
    "ucl-fetch-live-scores-2m": {
        "task": "ucl.matches.tasks.fetch_live_scores",
        "schedule": crontab(minute="*/2", hour="17-23,0-1", day_of_week="tue,wed,thu"),
    },
    # ===================================================================
    # Settlement safety nets (primary trigger is inline from live scores)
    # ===================================================================
    "nba-settle-pending-bets-daily": {
        "task": "nba.betting.tasks.settle_pending_bets",
        "schedule": crontab(hour=6, minute=0),
    },
    "nfl-settle-pending-bets-daily": {
        "task": "nfl.betting.tasks.settle_pending_bets",
        "schedule": crontab(hour=6, minute=0),
    },
    # ===================================================================
    # Challenges (EPL + NBA only)
    # ===================================================================
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
    # ===================================================================
    # News
    # ===================================================================
    # Daily catch-up — primary trigger is inline from match completion
    "news-generate-recaps-daily": {
        "task": "news.tasks.generate_pending_recaps",
        "schedule": crontab(hour=6, minute=0),
    },
    "news-weekly-roundup-epl": {
        "task": "news.tasks.generate_weekly_roundup_task",
        "schedule": crontab(hour=10, minute=0, day_of_week=1),
        "args": ("epl",),
    },
    "news-weekly-roundup-nba": {
        "task": "news.tasks.generate_weekly_roundup_task",
        "schedule": crontab(hour=10, minute=0, day_of_week=1),
        "args": ("nba",),
    },
    "news-weekly-roundup-nfl": {
        "task": "news.tasks.generate_weekly_roundup_task",
        "schedule": crontab(hour=10, minute=0, day_of_week=1),
        "args": ("nfl",),
    },
    "news-betting-trend-epl": {
        "task": "news.tasks.generate_betting_trend_task",
        "schedule": crontab(hour=10, minute=0, day_of_week=3),
        "args": ("epl",),
    },
    "news-betting-trend-nba": {
        "task": "news.tasks.generate_betting_trend_task",
        "schedule": crontab(hour=10, minute=0, day_of_week=3),
        "args": ("nba",),
    },
    "news-betting-trend-nfl": {
        "task": "news.tasks.generate_betting_trend_task",
        "schedule": crontab(hour=10, minute=0, day_of_week=3),
        "args": ("nfl",),
    },
    "news-cross-league": {
        "task": "news.tasks.generate_cross_league_task",
        "schedule": crontab(hour=10, minute=0, day_of_week=5),
    },
    # ===================================================================
    # Reddit
    # ===================================================================
    "reddit-fetch-morning": {
        "task": "reddit.tasks.fetch_subreddit_snapshots",
        "schedule": crontab(hour=10, minute=0),
    },
    "reddit-fetch-afternoon": {
        "task": "reddit.tasks.fetch_subreddit_snapshots",
        "schedule": crontab(hour=18, minute=0),
    },
    "reddit-purge-old-snapshots": {
        "task": "reddit.tasks.purge_old_snapshots",
        "schedule": crontab(hour=4, minute=0),
    },
}

# External APIs
BDL_API_KEY = os.environ.get("BDL_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_TIMEOUT = 30

# Reddit API
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_API_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "vinosports/1.0")

LEAGUE_SUBREDDITS = {
    "epl": "soccer",
    "nba": "nba",
    "nfl": "nfl",
    "worldcup": "soccer",
    "ucl": "soccer",
}

# EPL-specific
EPL_CURRENT_SEASON = "2025"

# World Cup
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")

# UCL
UCL_CURRENT_SEASON = "2025"

# --- Logging ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "django.security.DisallowedHost": {
            "handlers": [],
            "propagate": False,
        },
    },
}

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
    from django.core.exceptions import DisallowedHost

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=True,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment="production" if not DEBUG else "development",
        ignore_errors=[DisallowedHost],
    )
