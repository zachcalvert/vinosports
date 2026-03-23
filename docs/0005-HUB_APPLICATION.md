# 0005: Hub Application

**Date:** 2026-03-23

## Purpose

The hub (`apps/hub/`) is the centralized entry point for vinosports. It runs as a standalone Django project at [vinosports.com](https://vinosports.com) (or `localhost:7999` locally) and serves two roles:

1. **League directory** — Homepage with cards for each league (EPL, NBA, NFL). Active leagues link out to their respective apps; upcoming leagues show "Coming Soon."
2. **Global account management** — Display name, balance (coins), and currency preference are shared across all leagues. The hub provides a single place to manage these settings.

## Architecture

The hub is a Django project that owns global user management. It reads from vinosports-core's `User` and `UserBalance` tables and defines its own `SiteSettings` model for registration caps.

```
apps/hub/
├── config/             # Django settings, urls, wsgi
│   ├── settings.py     # LEAGUE_URLS registry, LOGIN_URL
│   ├── urls.py
│   └── wsgi.py
├── hub/                # The hub Django app
│   ├── admin.py                # UserAdmin, SiteSettingsAdmin
│   ├── context_processors.py   # Injects league URLs + hub URL into all templates
│   ├── forms.py                # DisplayNameForm, CurrencyForm, SignupForm, LoginForm
│   ├── models.py               # SiteSettings (registration caps, singleton)
│   ├── views.py                # HomeView, SignupView, LoginView, LogoutView, AccountView
│   ├── migrations/
│   ├── templatetags/
│   │   └── currency_tags.py    # Currency formatting filters ({{ amount|currency:user }})
│   ├── templates/hub/
│   │   ├── base.html           # Shared layout (navbar, footer, Tailwind, Oswald font)
│   │   ├── home.html           # League directory cards
│   │   ├── signup.html         # Registration form
│   │   ├── login.html          # Login form
│   │   ├── account.html        # Global account settings
│   │   └── components/
│   │       ├── navbar.html     # Auth-aware navbar (display name + balance when logged in)
│   │       └── footer.html
│   └── static/hub/
│       ├── css/styles.css      # Hub subset of the vinosports design system
│       └── img/                # Logo assets
├── Dockerfile
├── manage.py
└── requirements.txt
```

## Key Design Decisions

### SiteSettings model

The hub's only model is `SiteSettings` — a singleton (`pk=1`) that controls registration caps (`max_users`) and the closed-registration message. Uses `select_for_update()` inside `transaction.atomic()` to prevent race conditions during signup.

### Hub owns auth

Signup, login, and logout all live in the hub. League apps redirect their `/login/` and `/signup/` URLs to the hub. Each league keeps a thin local `LogoutView` because CSRF tokens cannot be validated cross-port (different Origin headers). Sessions are shared across all apps via the same `SECRET_KEY` and `django_session` table — login on hub:7999 authenticates on epl:8000 and nba:8001.

See `docs/0007-CENTRALIZED_AUTH.md` for the full migration rationale.

### League registry in settings

`LEAGUE_URLS` in `config/settings.py` is the single source of truth for league metadata:

```python
LEAGUE_URLS = {
    "epl": {"name": "...", "short": "EPL", "url": "...", "status": "active", "icon": "..."},
    "nba": {"name": "...", "short": "NBA", "url": "...", "status": "coming_soon", ...},
    "nfl": {"name": "...", "short": "NFL", "url": None, "status": "coming_soon", ...},
}
```

A context processor (`hub.context_processors.league_urls`) injects this into every template. The homepage iterates over it to render league cards, and the account page uses it to link to league-specific settings.

### Currency tags are duplicated, not shared

The `currency_tags.py` template tag library exists in both the hub and EPL apps. It's ~45 lines of pure formatting logic with no model dependencies. Extracting it into vinosports-core's template tags would require all consumers to add a core templatetags dependency — not worth the coupling for such a small utility.

## What Lives Where

| Setting | Location | Why |
|---------|----------|-----|
| Display name | Hub account page | Global identity across all leagues |
| Balance (coins) | Hub account page | One balance shared across all leagues |
| Currency preference | Hub account page | Affects how balance displays everywhere |
| Avatar (icon, color, frame, crest) | League account pages | Frames are unlocked by league-specific badges |
| Activity toasts toggle | League account pages | Activity events are league-specific |
| Betting stats / history | League account pages | Stats are per-league |
| Badges | League account pages | Earned through league-specific actions |

## Running Locally

The hub runs as a Docker Compose service alongside the league apps:

| Service | Port | Description |
|---------|------|-------------|
| `hub-web` | 7999 | Hub dev server (auto-reload) |

```bash
make up          # Starts everything including the hub
# Or start just the hub:
docker compose up hub-web
```

The hub shares the same PostgreSQL and Redis instances as the league apps. No separate database setup is needed.

## Adding a New League

When a new league app is ready:

1. Add an entry to `LEAGUE_URLS` in `apps/hub/config/settings.py`
2. Set `"status": "active"` and provide the `"url"`
3. The homepage will automatically show an active card with a link
