# Vinosports

A monorepo for sports betting simulations across multiple leagues, powered by a shared Django package.

Each league (EPL, NBA, and eventually NFL, World Cup, March Madness) is a standalone Django project that installs `vinosports-core` — a shared package providing user accounts, play-money balances, betting infrastructure, AI bot commentary, challenges, and rewards. One user account and one balance works across all leagues.

<img width="1016" height="632" alt="Screenshot 2026-03-25 at 9 09 47 AM" src="https://github.com/user-attachments/assets/ac54fbfd-8b0a-4b4f-855f-475039470243" />


**Live:** [eplbets.net](https://eplbets.net) (the original EPL Bets, being migrated here)
**Domain:** [vinosports.com](https://vinosports.com) (future unified frontend)

## Architecture

```
vinosports/
├── packages/vinosports-core/    # Shared Django apps (pip-installable)
├── apps/hub/                     # Central homepage + global account settings
├── apps/epl/                     # EPL betting simulation (fully ported)
├── apps/nba/                     # NBA betting simulation (skeleton)
├── docker-compose.yml            # Local dev stack
└── docs/                         # Architecture decisions and plans
```

The **hub** (`apps/hub/`) is the top-level entry point. It provides a league directory (EPL, NBA, NFL cards) and manages global account settings (display name, balance, currency). It has no models — it reads from vinosports-core's shared database. See [docs/0005-HUB_APPLICATION.md](docs/0005-HUB_APPLICATION.md) for details.

See [docs/0000-INITIAL_VISION.md](docs/0000-INITIAL_VISION.md) for the full architectural rationale and [docs/0001-SCAFFOLDING_COMPLETE.md](docs/0001-SCAFFOLDING_COMPLETE.md) for what's been built.

## Local Development

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A [football-data.org](https://www.football-data.org/) API key (free tier, for EPL data)

### Quick Start

```bash
# Clone the repo
git clone https://github.com/zachcalvert/vinosports.git
cd vinosports

# Copy env template and fill in API keys
cp .env.example .env

# Build and start everything
make up

# Run migrations (both leagues)
make migrate

# Create a superuser
docker compose run --rm epl-web python manage.py createsuperuser

# Populate EPL data
make seed
```

The hub is at [localhost:7999](http://localhost:7999), EPL at [localhost:8000](http://localhost:8000), NBA at [localhost:8001](http://localhost:8001).

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
| `make migrate` | Run migrations for both leagues |
| `make seed` | Populate EPL data (teams, fixtures, standings, odds) |
| `make shell-epl` | Shell into the EPL container |
| `make shell-nba` | Shell into the NBA container |
| `make lint` | Run ruff check + format |
| `make test` | Run all test suites |
| `make test-epl` | Run EPL tests only |
| `make test-nba` | Run NBA tests only |
| `make test-core` | Run vinosports-core tests only |

### Hot Reload

Docker Compose mounts your local source code into all containers. Web services run Django's `runserver` in dev mode, so Python file changes trigger an automatic restart — no rebuild needed. Worker and beat services also mount source code but need a manual container restart to pick up changes.

Dockerfiles retain Daphne as the production server; the `runserver` override is only in `docker-compose.yml`.

### Populating Data

See [docs/0002-DATA_POPULATION.md](docs/0002-DATA_POPULATION.md) for the full guide. The short version is `make seed`.

### Setting Up Bots

See [docs/0003-BOT_SETUP.md](docs/0003-BOT_SETUP.md) for the full guide.

### Docker Compose Services

| Service | Port | Description |
|---------|------|-------------|
| `db` | 5432 | PostgreSQL (shared by all leagues) |
| `redis` | 6379 | Redis (Celery broker + Channels layer) |
| `hub-web` | 7999 | Hub homepage + global account settings |
| `epl-web` | 8000 | EPL dev server (auto-reload) |
| `epl-worker` | — | EPL Celery worker |
| `epl-beat` | — | EPL Celery beat scheduler |
| `nba-web` | 8001 | NBA dev server (auto-reload) |
| `nba-worker` | — | NBA Celery worker |
| `nba-beat` | — | NBA Celery beat scheduler |

### Running Without Docker

```bash
# Create a venv and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e packages/vinosports-core
pip install psycopg2-binary whitenoise django-htmx

# Run the EPL project (requires local Postgres and Redis)
cd apps/epl
python manage.py migrate
python manage.py runserver
```

## Testing

**Test coverage is required for all contributions.** The project has three test suites that mirror the package structure:

```
packages/vinosports-core/tests/    # Shared models, balance logic, challenge engine
apps/epl/tests/                     # EPL-specific: settlement, odds engine, data ingestion
apps/nba/tests/                     # NBA-specific: spread/total settlement, API client
```

### Running Tests

```bash
make test          # All suites
make test-epl      # EPL tests only
make test-nba      # NBA tests only
make test-core     # vinosports-core tests only
```

### Test Guidelines

- **Every new model, view, or service must have tests.** No exceptions.
- **Test behavior, not implementation.** Assert on outcomes (bet settled correctly, balance updated, WebSocket message sent), not on internal method calls.
- **Use factories over fixtures.** Create test data with factory functions or `Model.objects.create()`, not JSON fixtures.
- **Test the boundaries.** If a model is abstract in vinosports-core and concrete in a league project, test the concrete version in the league's test suite. Test the abstract logic (shared fields, methods) in vinosports-core's tests.
- **Integration tests for Celery tasks.** Use `@shared_task` with `task_always_eager=True` in test settings so tasks run synchronously.
- **WebSocket tests.** Use `channels.testing.WebsocketCommunicator` for consumer tests.

### CI

Tests run automatically via GitHub Actions with path-based triggers:

- Changes to `packages/vinosports-core/` trigger **all three** test suites
- Changes to `apps/epl/` trigger only the EPL + core suites
- Changes to `apps/nba/` trigger only the NBA + core suites

## Linting

[Ruff](https://docs.astral.sh/ruff/) handles both linting and formatting. Configuration lives in the root `pyproject.toml` (rules: `E`, `F`, `I`; line length not enforced; migrations excluded).

```bash
make lint    # ruff check --fix + ruff format
```

A pre-commit hook runs ruff automatically on every commit. Install it with:

```bash
pre-commit install
```

## Contributing

1. Fork the repo and create a feature branch
2. Write your code with tests
3. Run the relevant test suite locally and ensure it passes
4. Open a PR — CI will run the appropriate checks

## Tech Stack

- **Django 5.1** with email-based auth
- **Daphne** (ASGI) for WebSocket support
- **Django Channels** + Redis for real-time score updates
- **Celery** + Redis for background tasks
- **PostgreSQL** for persistence
- **HTMX** for interactive UI (no JS framework)
- **Claude API** for AI bot commentary
- **Docker Compose** for local development
