# Vinosports

Sports betting simulation monorepo. One shared Django package (`vinosports-core`), one unified Django project serving all leagues.

## Structure

```
config/                                    # Unified Django config
  settings.py                              #   merged settings for all leagues
  urls.py                                  #   hub at /, epl at /epl/, nba at /nba/
  asgi.py                                  #   unified WS routing (no middleware hack)
  celery.py                                #   single app "vinosports"
  middleware.py                            #   LeagueMiddleware (sets request.league)

packages/vinosports-core/src/vinosports/   # Shared pip-installable package
  core/          # BaseModel, id_hash, timestamps
  users/         # User model (email auth, is_bot flag)
  betting/       # UserBalance, BalanceTransaction, UserStats, AbstractBetSlip, AbstractParlay
  bots/          # AbstractBotProfile, AbstractBotComment (Claude API integration)
  challenges/    # ChallengeTemplate, Challenge, UserChallenge
  rewards/       # Reward, RewardDistribution, RewardRule
  discussions/   # AbstractComment
  activity/      # AbstractActivityEvent

hub/             # Central homepage, auth (signup/login/logout), SiteSettings, global account management
epl/             # EPL — fully featured (matches, betting, bots, discussions, website, etc.)
nba/             # NBA — fully featured (games, betting, bots, discussions, website, etc.)
```

## Key Architecture Decisions

- **Single Django project**: Hub, EPL, and NBA all run in one Django process. No `FORCE_SCRIPT_NAME`, no nginx prefix stripping. URLs are natively correct via `path("epl/", include("epl.urls"))` in `config/urls.py`
- **LeagueMiddleware**: Sets `request.league` (`"epl"`, `"nba"`, or `None`) from URL path. Context processors guard on this to avoid cross-league queries
- **Concrete models** in core: User, UserBalance, Badge, Challenge, Reward (identical across sports)
- **Abstract models** in core: BetSlip, Parlay, Comment, BotProfile (sport-specific fields added in league apps)
- **App labels**: Core apps use simple labels (`users`, `betting`). League apps use prefixed labels (`epl_betting`, `nba_betting`, `epl_matches`, `nba_games`) to avoid collisions
- **URL namespaces**: All league URL `app_name` values are prefixed (`epl_website`, `nba_betting`, etc.). Use `{% url 'epl_matches:dashboard' %}` not `{% url 'dashboard' %}`
- **Template namespaces**: League template directories are prefixed (`epl_betting/`, `nba_website/`) to avoid collisions under `APP_DIRS`
- **Static namespaces**: League static directories are prefixed (`epl_website/css/`, `nba_website/js/`)
- **Model FK strings**: Use prefixed app labels (`"epl_matches.Match"`, `"nba_games.Game"`)
- **Single shared DB**: All apps share one PostgreSQL instance. One user account + balance works across all leagues
- **Hub owns auth**: Signup, login, logout live in hub at the root path. League apps redirect `/login/` and `/signup/` to hub
- **Admin deduplication**: Shared core models (UserBalance, Badge, UserBadge) are registered in EPL's admin only, not duplicated across leagues
- **HTMX frontend**: Server-rendered templates with HTMX for interactivity. No JS framework
- **WebSocket routing**: Defined in `config/asgi.py` with nested `URLRouter` — `path("epl/", URLRouter(...))`, `path("nba/", URLRouter(...))`

## Running Locally

```bash
# Start everything (uses Docker)
make up

# Run migrations
make migrate

# Seed data (EPL + NBA)
make seed
```

### URLs (local dev)

Add to `/etc/hosts`:
```
127.0.0.1 vinosports.local
```

All apps served through nginx on port 80:
- Hub: http://vinosports.local
- EPL: http://vinosports.local/epl/
- NBA: http://vinosports.local/nba/

Nginx is a simple passthrough proxy (port 80 → web:8000) with WebSocket upgrade headers. No prefix stripping, no multiple upstreams.

### Infrastructure Ports
- PostgreSQL: 5432
- Redis: 6379

### Environment
Copy `.env.example` to `.env` and fill in API keys:
- `BDL_API_KEY` — BallDontLie (NBA + EPL data, All-Star tier)
- `ANTHROPIC_API_KEY` — Claude API (bot commentary)

## Docker Services (6 total)

| Service | Description |
|---------|-------------|
| `db` | PostgreSQL |
| `redis` | Redis (Celery broker + Channels layer) |
| `nginx` | Reverse proxy (port 80, WebSocket support) |
| `web` | Django dev server (all leagues) |
| `worker` | Celery worker (`-Q epl,nba`) |
| `beat` | Celery beat scheduler |

## Common Commands

```bash
make up                # docker compose up --build -d
make down              # docker compose down
make logs              # docker compose logs -f
make shell             # exec into web container
make migrate           # run migrations
make seed              # populate EPL + NBA data
make lint              # ruff check + format
make test              # run all test suites
```

## Dev Workflow

- Docker volume mounts provide **hot reload** — edit Python files and the dev server auto-restarts
- Web service uses `runserver` in dev (auto-reload). Dockerfile keeps Daphne for prod
- Worker/beat services mount code too but need manual container restart for changes
- Pre-commit hooks run ruff on every commit
- **Host dependency**: `ruff` must be installed locally for `make lint` / `make format` (`pip install ruff` or `brew install ruff`)

## Adding a New League

1. Create a Python package at the repo root (e.g., `nfl/`)
2. Add apps with prefixed labels (`nfl_games`, `nfl_betting`, etc.)
3. Prefix template and static directories (`nfl_betting/`, `nfl_website/`)
4. Create `nfl/urls.py` combining all sub-app URL includes
5. Add `path("nfl/", include("nfl.urls"))` to `config/urls.py`
6. Add apps to `INSTALLED_APPS` in `config/settings.py`
7. Add context processors with `if getattr(request, 'league', None) != 'nfl': return {}` guards
8. Add WS routes to `config/asgi.py`
9. Add Celery task autodiscovery to `config/celery.py`

## Testing

```bash
make test              # run all tests from web container
```

- Use factories, not JSON fixtures
- Test behavior (bet settled, balance updated), not implementation
- Celery tasks: use `task_always_eager=True` in test settings
- WebSocket: use `channels.testing.WebsocketCommunicator`

## Linting

Ruff is configured in root `pyproject.toml`:
- Rules: `E`, `F`, `I` (errors, pyflakes, isort)
- Line length: not enforced (`E501` ignored)
- Migrations excluded
- `vinosports` is a known first-party package for isort

## Docs

See `docs/` for architecture decisions and setup guides:
- `0000-INITIAL_VISION.md` — Original architectural rationale
- `0004-DESIGN_SYSTEM.md` — Design system
- `0005-HUB_APPLICATION.md` — Hub architecture and global account management
- `0007-CENTRALIZED_AUTH.md` — Auth centralization into hub
- `0009-BOT_SCHEDULE_TEMPLATES.md` — Bot schedule template system
- `0019-UNIFIED_DJANGO_PROJECT.md` — Merge from three projects into one (this refactor)
