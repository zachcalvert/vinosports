# Vinosports

[![CI](https://github.com/zachcalvert/vinosports/actions/workflows/ci.yml/badge.svg)](https://github.com/zachcalvert/vinosports/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/zachcalvert/vinosports/branch/main/graph/badge.svg)](https://codecov.io/gh/zachcalvert/vinosports)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Sports betting simulation platform across multiple leagues, powered by Django and HTMX. One user account, one play-money balance, all leagues.

**Live at [vinosports.com](https://vinosports.com)**

<img width="1213" height="972" alt="vinosports_home" src="https://github.com/user-attachments/assets/5df80df5-9868-421c-9d22-a519c397a52d" />

## Architecture

A single unified Django project serving all leagues. `vinosports-core` is a shared pip-installable package providing user accounts, play-money balances, betting infrastructure, AI bot commentary, challenges, and rewards.

```
vinosports/
├── config/                        # Django config (settings, urls, asgi, celery)
├── packages/vinosports-core/      # Shared Django apps (pip-installable)
├── hub/                           # Central homepage, auth, global account settings
├── epl/                           # EPL betting simulation (fully featured)
├── nba/                           # NBA betting simulation (fully featured)
├── Dockerfile                     # Single Dockerfile for all services
├── docker-compose.yml             # Local dev stack (6 services)
└── docs/                          # Architecture decisions and plans
```

The **hub** (`hub/`) is the top-level entry point at `/`. It provides a league directory and manages global account settings. League apps are mounted at `/epl/` and `/nba/` via standard Django URL includes — no prefix stripping, no `FORCE_SCRIPT_NAME`.

A `LeagueMiddleware` sets `request.league` from the URL path, and each league's context processors guard on this value to avoid unnecessary queries on other leagues' pages.

See [docs/0000-INITIAL_VISION.md](docs/0000-INITIAL_VISION.md) for the original architectural rationale and [docs/0019-UNIFIED_DJANGO_PROJECT.md](docs/0019-UNIFIED_DJANGO_PROJECT.md) for the merge from three projects into one.

## Local Development

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- Add `127.0.0.1 vinosports.local` to `/etc/hosts`

### Quick Start

```bash
# Clone the repo
git clone https://github.com/zachcalvert/vinosports.git
cd vinosports

# Copy env template and fill in API keys
cp .env.example .env

# Build and start everything
make up

# Run migrations
make migrate

# Create a superuser
docker compose exec web python manage.py createsuperuser

# Populate data (EPL + NBA)
make seed
```

All apps are served through nginx on port 80:
- Hub: http://vinosports.local
- EPL: http://vinosports.local/epl/
- NBA: http://vinosports.local/nba/

### Environment Variables

Create a `.env` file in the repo root (git-ignored) or copy from `.env.example`:

```bash
BDL_API_KEY=your-key-here          # BallDontLie (NBA + EPL data)
ANTHROPIC_API_KEY=your-key-here    # For bot comment generation
```

### Common Commands

A `Makefile` wraps the most-used workflows:

| Command | Description |
|---------|-------------|
| `make up` | Build and start all services |
| `make down` | Stop all services |
| `make restart` | Rebuild and restart |
| `make logs` | Tail all service logs |
| `make migrate` | Run migrations |
| `make seed` | Populate EPL + NBA data |
| `make shell` | Shell into the web container |
| `make lint` | Run ruff check + format |
| `make test` | Run tests (parallel, fast) |
| `make test-ci` | Run tests with coverage report |

### Hot Reload

Docker Compose mounts your local source code into all containers. The web service runs Django's `runserver` in dev mode, so Python file changes trigger an automatic restart — no rebuild needed. Worker and beat services also mount source code but need a manual container restart to pick up changes.

### Populating Data

See [docs/0002-DATA_POPULATION.md](docs/0002-DATA_POPULATION.md) for the full guide. The short version is `make seed`.

### Setting Up Bots

See [docs/0003-BOT_SETUP.md](docs/0003-BOT_SETUP.md) for the full guide.

### Docker Compose Services

| Service | Port | Description |
|---------|------|-------------|
| `db` | 5432 | PostgreSQL (shared by all leagues) |
| `redis` | 6379 | Redis (Celery broker + Channels layer) |
| `nginx` | 80 | Reverse proxy (WebSocket upgrade support) |
| `web` | — | Django dev server (all leagues) |
| `worker` | — | Celery worker (EPL + NBA queues) |
| `beat` | — | Celery beat scheduler |

## Testing

The test suite covers ~90% of source code across ~1,450 tests. Tests run in parallel via pytest-xdist.

```bash
make test       # Fast: parallel, reuses DB (~30s after first run)
make test-ci    # CI: parallel + coverage report
```

### Test Guidelines

- **Test behavior, not implementation.** Assert on outcomes (bet settled correctly, balance updated, WebSocket message sent), not on internal method calls.
- **Use factories over fixtures.** Create test data with factory functions or `Model.objects.create()`, not JSON fixtures.
- **Integration tests for Celery tasks.** Use `task_always_eager=True` in test settings so tasks run synchronously.
- **WebSocket tests.** Use `channels.testing.WebsocketCommunicator` for consumer tests.

See [docs/0028-TEST_COVERAGE_AND_PERFORMANCE.md](docs/0028-TEST_COVERAGE_AND_PERFORMANCE.md) for the full story on coverage and performance.

## Contributing

Contributions are welcome! Please include tests with your changes — the CI pipeline enforces lint and test gates on all pull requests. If you're adding a new feature or fixing a bug, write tests that cover the behavior. Run `make test` locally before pushing to catch issues early.

## Linting

[Ruff](https://docs.astral.sh/ruff/) handles both linting and formatting. Configuration lives in the root `pyproject.toml` (rules: `E`, `F`, `I`; line length not enforced; migrations excluded).

```bash
make lint    # ruff check --fix + ruff format
```

A pre-commit hook runs ruff automatically on every commit.

## Tech Stack

- **Django 5.2** with email-based auth
- **Daphne** (ASGI) for WebSocket support
- **Django Channels** + Redis for real-time score updates
- **Celery** + Redis for background tasks
- **PostgreSQL** for persistence
- **HTMX** for interactive UI (no JS framework)
- **Claude API** for AI bot commentary
- **Docker Compose** for local development

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
