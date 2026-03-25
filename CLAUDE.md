# Vinosports

Sports betting simulation monorepo. One shared Django package (`vinosports-core`), one Django project per league.

## Structure

```
packages/vinosports-core/src/vinosports/   # Shared pip-installable package
  core/          # BaseModel, id_hash, timestamps
  users/         # User model (email auth, is_bot flag)
  betting/       # UserBalance, BalanceTransaction, UserStats, AbstractBetSlip, AbstractParlay
  bots/          # AbstractBotProfile, AbstractBotComment (Claude API integration)
  challenges/    # ChallengeTemplate, Challenge, UserChallenge
  rewards/       # Reward, RewardDistribution, RewardRule
  discussions/   # AbstractComment
  activity/      # AbstractActivityEvent

apps/hub/        # Hub — central homepage, auth (signup/login/logout), SiteSettings, global account management
apps/epl/        # EPL — fully featured (matches, betting, bots, discussions, website, etc.)
apps/nba/        # NBA — skeleton (models defined, no views/templates yet)
```

## Key Architecture Decisions

- **Concrete models** in core: User, UserBalance, Badge, Challenge, Reward (identical across sports)
- **Abstract models** in core: BetSlip, Parlay, Comment, BotProfile (sport-specific fields added in league apps)
- **App labels**: Core apps use simple labels (`users`, `betting`). League apps use prefixed labels (`epl_betting`, `nba_betting`) to avoid collisions
- **Single shared DB**: All apps (hub + leagues) share one PostgreSQL instance. One user account + balance works across all leagues
- **Hub owns auth**: Signup, login, logout live in hub at the root path. League apps redirect `/login/` and `/signup/` to hub
- **Hub as entry point**: `apps/hub/` is the central homepage, auth provider, and global account manager. Owns `SiteSettings` (registration caps) and `UserAdmin`. League apps handle league-specific settings (avatar, badges, stats)
- **Unified domain**: All apps served via nginx reverse proxy on `vinosports.local`. Hub at root, EPL at `/epl/`, NBA at `/nba/`. Sessions and CSRF tokens work across all apps (same domain, same DB, same `SECRET_KEY`)
- **FORCE_SCRIPT_NAME**: EPL and NBA use `FORCE_SCRIPT_NAME` so Django's `reverse()` and `{% url %}` include the `/epl/` or `/nba/` prefix. Nginx strips the prefix before proxying to the Django app
- **HTMX frontend**: Server-rendered templates with HTMX for interactivity. No JS framework

## Running Locally

```bash
# Start everything (uses Docker)
make up

# Run migrations (both leagues)
make migrate

# Seed EPL data (teams, fixtures, standings, odds)
make seed
```

### URLs (local dev)

Add to `/etc/hosts`:
```
127.0.0.1 vinosports.local
```

All apps are served through nginx on port 80:
- Hub: http://vinosports.local
- EPL: http://vinosports.local/epl/
- NBA: http://vinosports.local/nba/

Nginx reverse proxy strips the `/epl/` and `/nba/` prefixes before forwarding to the Django apps. `FORCE_SCRIPT_NAME` ensures Django generates prefixed URLs in `{% url %}`, `reverse()`, and redirects.

### Infrastructure Ports
- PostgreSQL: 5432
- Redis: 6379

### Environment
Copy `.env.example` to `.env` and fill in API keys:
- `BDL_API_KEY` — BallDontLie (NBA + EPL data, All-Star tier)
- `ANTHROPIC_API_KEY` — Claude API (bot commentary)

## Common Commands

```bash
make up                # docker compose up --build -d
make down              # docker compose down
make logs              # docker compose logs -f
make shell-epl         # exec into EPL container
make shell-nba         # exec into NBA container
# Hub: docker compose exec hub-web python manage.py <cmd>
make migrate           # run migrations for both leagues
make seed              # populate EPL data
make lint              # ruff check + format
make test              # run all test suites
```

## Dev Workflow

- Docker volume mounts provide **hot reload** — edit Python files and the dev server auto-restarts
- Web services use `runserver` in dev (auto-reload). Dockerfiles keep Daphne for prod
- Worker/beat services mount code too but need manual container restart for changes
- Pre-commit hooks run ruff on every commit
- **Host dependency**: `ruff` must be installed locally for `make lint` / `make format` (`pip install ruff` or `brew install ruff`)

## Testing

```bash
# Core tests
docker compose run --rm epl-web python -m pytest packages/vinosports-core/tests/

# EPL tests
docker compose run --rm epl-web python -m pytest

# NBA tests
docker compose run --rm nba-web python -m pytest
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
- `0000-INITIAL_VISION.md` — Full architectural rationale
- `0001-SCAFFOLDING_COMPLETE.md` — Build progress
- `0002-DATA_POPULATION.md` — Data ingestion
- `0003-BOT_SETUP.md` — Bot configuration
- `0004-DESIGN_SYSTEM.md` — Design system
- `0005-HUB_APPLICATION.md` — Hub architecture and global account management
- `0007-CENTRALIZED_AUTH.md` — Auth centralization into hub
- `0009-BOT_SCHEDULE_TEMPLATES.md` — Bot schedule template system (NBA) and EPL porting guide
