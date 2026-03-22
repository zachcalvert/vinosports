# Vinosports

A monorepo for sports betting simulations across multiple leagues, powered by a shared Django package.

Each league (EPL, NBA, and eventually NFL, World Cup, March Madness) is a standalone Django project that installs `vinosports-core` — a shared package providing user accounts, play-money balances, betting infrastructure, AI bot commentary, challenges, and rewards. One user account and one balance works across all leagues.

**Live:** [eplbets.net](https://eplbets.net) (the original EPL Bets, being migrated here)
**Domain:** [vinosports.com](https://vinosports.com) (future unified frontend)

## Architecture

```
vinosports/
├── packages/vinosports-core/    # Shared Django apps (pip-installable)
├── apps/epl/                     # EPL betting simulation (fully ported)
├── apps/nba/                     # NBA betting simulation (skeleton)
├── docker-compose.yml            # Local dev stack
└── docs/                         # Architecture decisions and plans
```

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

# Build and start everything
docker compose up --build

# In another terminal, run migrations
docker compose run --rm epl-web python manage.py migrate --noinput
docker compose run --rm nba-web python manage.py migrate --noinput

# Create a superuser
docker compose run --rm epl-web python manage.py createsuperuser
```

The EPL app is at [localhost:8000](http://localhost:8000), NBA at [localhost:8001](http://localhost:8001).

### Environment Variables

Create a `.env` file in the repo root (git-ignored):

```bash
FOOTBALL_DATA_API_KEY=your-key-here
ANTHROPIC_API_KEY=your-key-here  # For bot comment generation
```

### Populating Data

See [docs/0002-DATA_POPULATION.md](docs/0002-DATA_POPULATION.md) for the full guide. The short version:

```bash
docker compose run --rm epl-web python manage.py shell -c "
from matches.tasks import fetch_teams, fetch_fixtures, fetch_standings
fetch_teams()
fetch_fixtures()
fetch_standings()
from betting.tasks import generate_odds
generate_odds()
"
```

### Setting Up Bots

See [docs/0003-BOT_SETUP.md](docs/0003-BOT_SETUP.md) for the full guide.

### Docker Compose Services

| Service | Port | Description |
|---------|------|-------------|
| `db` | 5432 | PostgreSQL (shared by all leagues) |
| `redis` | 6379 | Redis (Celery broker + Channels layer) |
| `epl-web` | 8000 | EPL Daphne server (HTTP + WebSocket) |
| `epl-worker` | — | EPL Celery worker |
| `epl-beat` | — | EPL Celery beat scheduler |
| `nba-web` | 8001 | NBA Daphne server |
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
# vinosports-core tests
docker compose run --rm epl-web python -m pytest packages/vinosports-core/tests/

# EPL tests
docker compose run --rm epl-web python -m pytest

# NBA tests
docker compose run --rm nba-web python -m pytest
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
