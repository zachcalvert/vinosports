# 0005: Hub Application

**Date:** 2026-03-23

## Purpose

The hub (`apps/hub/`) is the centralized entry point for vinosports. It runs as a standalone Django project at [vinosports.com](https://vinosports.com) (or `localhost:7999` locally) and serves two roles:

1. **League directory** — Homepage with cards for each league (EPL, NBA, NFL). Active leagues link out to their respective apps; upcoming leagues show "Coming Soon."
2. **Global account management** — Display name, balance (coins), and currency preference are shared across all leagues. The hub provides a single place to manage these settings.

## Architecture

The hub is a thin Django project. It has no models of its own — it reads from vinosports-core's `User` and `UserBalance` tables in the shared PostgreSQL database.

```
apps/hub/
├── config/             # Django settings, urls, wsgi
│   ├── settings.py     # LEAGUE_URLS registry, LOGIN_URL redirect
│   ├── urls.py
│   └── wsgi.py
├── hub/                # The hub Django app
│   ├── context_processors.py   # Injects league URLs + hub URL into all templates
│   ├── forms.py                # DisplayNameForm, CurrencyForm
│   ├── views.py                # HomeView, AccountView, CurrencyUpdateView
│   ├── templatetags/
│   │   └── currency_tags.py    # Currency formatting filters ({{ amount|currency:user }})
│   ├── templates/hub/
│   │   ├── base.html           # Shared layout (navbar, footer, Tailwind, Oswald font)
│   │   ├── home.html           # League directory cards
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

### No models, no migrations

The hub installs `vinosports.core`, `vinosports.users`, and `vinosports.betting` from the shared package but defines no models itself. It reads user profiles and balances directly from the shared DB. This keeps it lightweight and ensures there's exactly one source of truth for account data.

### No auth forms

Login and signup are handled by the league apps (currently EPL at `/login/` and `/signup/`). The hub's `LOGIN_URL` redirects unauthenticated users to EPL's login page. Sessions are shared across all apps via the same `SECRET_KEY` and `SESSION_COOKIE_DOMAIN`.

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
