# Vinosports

Sports betting simulation monorepo. One shared Django package (`vinosports-core`), one unified Django project serving all leagues.

## Structure

```
config/                                    # Unified Django config
  settings.py                              #   merged settings for all leagues
  urls.py                                  #   hub at /, epl at /epl/, nba at /nba/, nfl at /nfl/
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
nfl/             # NFL — fully featured (games, betting, bots, discussions, website, etc.)
```

## Key Architecture Decisions

- **Single Django project**: Hub, EPL, NBA, and NFL all run in one Django process. No `FORCE_SCRIPT_NAME`, no nginx prefix stripping. URLs are natively correct via `path("epl/", include("epl.urls"))` in `config/urls.py`
- **LeagueMiddleware**: Sets `request.league` (`"epl"`, `"nba"`, `"nfl"`, or `None`) from URL path. Context processors guard on this to avoid cross-league queries
- **Concrete models** in core: User, UserBalance, Badge, Challenge, Reward (identical across sports)
- **Abstract models** in core: BetSlip, Parlay, Comment, BotProfile (sport-specific fields added in league apps)
- **App labels**: Core apps use simple labels (`users`, `betting`). League apps use prefixed labels (`epl_betting`, `nba_betting`, `nfl_betting`, `epl_matches`, `nba_games`, `nfl_games`) to avoid collisions
- **URL namespaces**: All league URL `app_name` values are prefixed (`epl_website`, `nba_betting`, `nfl_games`, etc.). Use `{% url 'epl_matches:dashboard' %}` not `{% url 'dashboard' %}`
- **Template namespaces**: League template directories are prefixed (`epl_betting/`, `nba_website/`, `nfl_games/`) to avoid collisions under `APP_DIRS`
- **Static namespaces**: League static directories are prefixed (`epl_website/css/`, `nba_website/js/`, `nfl_website/css/`)
- **Model FK strings**: Use prefixed app labels (`"epl_matches.Match"`, `"nba_games.Game"`, `"nfl_games.Game"`)
- **Single shared DB**: All apps share one PostgreSQL instance. One user account + balance works across all leagues
- **Hub owns auth**: Signup, login, logout live in hub at the root path. League apps redirect `/login/` and `/signup/` to hub
- **Admin deduplication**: Shared core models (UserBalance, Badge, UserBadge) are registered in EPL's admin only, not duplicated across leagues
- **DHA frontend stack**: Django + HTMX + Alpine.js. Server-rendered templates, HTMX for server communication and `hx-boost` SPA-like navigation, Alpine.js for client-side UI state (dropdowns, sidebars, toggles). Tailwind CSS compiled at build time via standalone CLI (no Node.js). See `docs/0034-FRONTEND_PERFORMANCE.md`
- **WebSocket routing**: Defined in `config/asgi.py` with nested `URLRouter` — `path("epl/", URLRouter(...))`, `path("nba/", URLRouter(...))`, `path("nfl/", URLRouter(...))`

## Production

Live at **vinosports.com**. Hosted on Fly.io (iad region). See `docs/0001-CI_DEPLOYMENT.md` for full infrastructure details.

- **CI/CD**: Push to `main` → lint → test → auto-deploy via GitHub Actions
- **Processes**: `web` (Daphne), `worker` (Celery), `beat` — all in one Fly app
- **Database**: Fly Postgres (`vinosports-db`)
- **Redis**: Upstash Redis (`vinosports-redis`)
- **Media**: Tigris S3 (`vinosports-media`) — profile images, bot portraits
- **Static files**: WhiteNoise (served from Docker image, not S3)
- **Monitoring**: Sentry (free tier)
- **Config**: `fly.toml` at repo root. Secrets managed via `fly secrets set`

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
- NFL: http://vinosports.local/nfl/

Nginx is a simple passthrough proxy (port 80 → web:8000) with WebSocket upgrade headers. No prefix stripping, no multiple upstreams.

### Infrastructure Ports
- PostgreSQL: 5432
- Redis: 6379

### Environment
Copy `.env.example` to `.env` and fill in API keys:
- `BDL_API_KEY` — BallDontLie (NBA + EPL data, All-Star tier)
- `ANTHROPIC_API_KEY` — Claude API (bot commentary)

## Docker Services (7 total)

| Service | Description |
|---------|-------------|
| `db` | PostgreSQL |
| `redis` | Redis (Celery broker + Channels layer) |
| `web` | Django dev server (all leagues) |
| `tailwind` | Tailwind CSS watcher (rebuilds on template changes) |
| `worker` | Celery worker (`-Q epl,nba,nfl`) |
| `beat` | Celery beat scheduler |

## Common Commands

```bash
make up                # docker compose up --build -d + initial Tailwind build
make down              # docker compose down
make logs              # docker compose logs -f
make shell             # exec into web container
make migrate           # run migrations
make seed              # populate EPL + NBA + NFL data
make tw                # one-shot Tailwind build (minified)
make tw-watch          # start Tailwind watcher in foreground
make lint              # ruff check + format
make test              # run tests (parallel + reuse-db, ~30s)
make test-ci           # run tests with coverage report (parallel, no reuse-db)
```

## Dev Workflow

- Docker volume mounts provide **hot reload** — edit Python files and the dev server auto-restarts
- Web service uses `runserver` in dev (auto-reload). Production uses Daphne (see `fly.toml`)
- Tailwind watcher auto-rebuilds CSS when templates change (~1s rebuild)
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

~1,632 tests at ~90% source coverage. Tests run in parallel via pytest-xdist (`-n auto`).

```bash
make test              # fast local dev: parallel + --reuse-db (~30s)
make test-ci           # CI mode: parallel + coverage (no --reuse-db)
```

- Use factories, not JSON fixtures
- Test behavior (bet settled, balance updated), not implementation
- Celery tasks: use `task_always_eager=True` in test settings
- WebSocket: use `channels.testing.WebsocketCommunicator`
- Coverage is opt-in (not in `addopts`); use `make test-ci` or pass `--cov` flags explicitly

## Linting

Ruff is configured in root `pyproject.toml`:
- Rules: `E`, `F`, `I` (errors, pyflakes, isort)
- Line length: not enforced (`E501` ignored)
- Migrations excluded
- `vinosports` is a known first-party package for isort

## Docs

See `docs/` for architecture decisions and setup guides:
- `0000-INITIAL_VISION.md` — Original architectural rationale
- `0001-CI_DEPLOYMENT.md` — CI/CD, Fly.io infrastructure, Sentry, Tigris, provisioning guide
- `0004-DESIGN_SYSTEM.md` — Design system
- `0005-HUB_APPLICATION.md` — Hub architecture and global account management
- `0007-CENTRALIZED_AUTH.md` — Auth centralization into hub
- `0009-BOT_SCHEDULE_TEMPLATES.md` — Bot schedule template system
- `0019-UNIFIED_DJANGO_PROJECT.md` — Merge from three projects into one (this refactor)
- `0027-TEST_INFRASTRUCTURE.md` — Test infrastructure and baseline coverage
- `0028-TEST_COVERAGE_AND_PERFORMANCE.md` — Coverage push to 90% and parallelization
- `0034-FRONTEND_PERFORMANCE.md` — Tailwind build-time CLI, Alpine.js, hx-boost, WhiteNoise optimization
- `9999-PRE_LAUNCH_PLAN.md` — Pre-launch checklist (all phases complete)
