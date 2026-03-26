# Vinosports

A monorepo for sports betting simulations across multiple leagues, powered by a shared Django package.

Each league (EPL, NBA, and eventually NFL, World Cup, March Madness) lives as a Python package within a single unified Django project. `vinosports-core` is a shared package providing user accounts, play-money balances, betting infrastructure, AI bot commentary, challenges, and rewards. One user account and one balance works across all leagues.

<img width="1016" height="632" alt="Screenshot 2026-03-25 at 9 09 47 AM" src="https://github.com/user-attachments/assets/ac54fbfd-8b0a-4b4f-855f-475039470243" />


**Live:** [eplbets.net](https://eplbets.net) (the original EPL Bets, being migrated here)
**Domain:** [vinosports.com](https://vinosports.com) (future unified frontend)

## Architecture

```
vinosports/
├── config/                        # Unified Django config (settings, urls, asgi, celery)
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
| `make test` | Run all test suites |

### Hot Reload

Docker Compose mounts your local source code into all containers. The web service runs Django's `runserver` in dev mode, so Python file changes trigger an automatic restart — no rebuild needed. Worker and beat services also mount source code but need a manual container restart to pick up changes.

The Dockerfile retains Daphne as the production server; the `runserver` override is only in `docker-compose.yml`.

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

### Running Without Docker

```bash
# Create a venv and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e packages/vinosports-core
pip install psycopg2-binary whitenoise django-htmx

# Run the project (requires local Postgres and Redis)
python manage.py migrate
python manage.py runserver
```

## Testing

```bash
make test    # Run all tests
```

### Test Guidelines

- **Test behavior, not implementation.** Assert on outcomes (bet settled correctly, balance updated, WebSocket message sent), not on internal method calls.
- **Use factories over fixtures.** Create test data with factory functions or `Model.objects.create()`, not JSON fixtures.
- **Integration tests for Celery tasks.** Use `task_always_eager=True` in test settings so tasks run synchronously.
- **WebSocket tests.** Use `channels.testing.WebsocketCommunicator` for consumer tests.

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
