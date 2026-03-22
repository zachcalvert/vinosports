# 0001: CI, Deployment & Infrastructure

## Infrastructure (Fly.io)

### Organization Layout

All services live under a single Fly organization:

```
vinosports (Fly org)
├── vinosports-epl        # EPL Django app (web + worker + beat processes)
├── vinosports-nba        # NBA Django app (web + worker + beat processes)
├── vinosports-db          # Shared Postgres cluster
└── vinosports-redis       # Upstash Redis (shared)
```

### Per-League Fly App

Each league deploys as one Fly app with three process groups:

```toml
# apps/epl/fly.toml
[processes]
  web = "daphne -b 0.0.0.0 -p 8000 config.asgi:application"
  worker = "celery -A config worker -l info"
  beat = "celery -A config beat -l info"
```

`fly deploy` from a league directory deploys all three processes together. Worker and beat run as separate machines for clean monitoring and independent restarts.

### Shared Services

- **Postgres**: One Fly Postgres cluster, one database (`vinosports`), one `public` schema. All league projects share the same user accounts, balances, badges, challenges, and rewards tables. League-specific tables (matches, games, odds, bets) coexist in the same schema with distinct table name prefixes via Django app labels.
- **Redis**: Upstash Redis (Fly's official Redis partner). Used for Celery broker/results, Django Channels layer, and caching. Upstash free tier (10K commands/day) is sufficient for ~200 users + 25 bots; paid tier ($10/mo) available if needed.

### Estimated Monthly Cost (~200 users, ~25 bots)

| Service | Spec | Cost |
|---------|------|------|
| Postgres (Fly) | shared-cpu, 256MB, 1GB disk | ~$7 |
| Redis (Upstash) | Free or $10 plan | $0–10 |
| EPL web | shared-cpu-1x, 256MB | ~$3 |
| EPL worker | shared-cpu-1x, 256MB | ~$3 |
| EPL beat | shared-cpu-1x, 256MB | ~$3 |
| NBA web | shared-cpu-1x, 256MB | ~$3 |
| NBA worker | shared-cpu-1x, 256MB | ~$3 |
| NBA beat | shared-cpu-1x, 256MB | ~$3 |
| **Total** | | **~$25–35/mo** |

Claude API costs for bot commentary are separate and will likely exceed infrastructure costs.

## CI (GitHub Actions)

### Test Suites

Three independent test suites, each runnable in isolation:

```
packages/vinosports-core/tests/    # Shared models, balance logic, utilities
apps/epl/tests/                    # EPL-specific: odds engine, settlement, data ingestion
apps/nba/tests/                    # NBA-specific: spread/total settlement, API client
```

### Path-Based Workflow Triggers

Each workflow only runs when relevant files change:

- **vinosports-core changes** → run core tests + EPL tests + NBA tests → deploy both leagues
- **EPL-only changes** → run EPL tests only → deploy EPL only
- **NBA-only changes** → run NBA tests only → deploy NBA only

```yaml
# .github/workflows/vinosports-core.yml
on:
  push:
    paths:
      - 'packages/vinosports-core/**'

# .github/workflows/epl.yml
on:
  push:
    paths:
      - 'packages/vinosports-core/**'   # core changes affect EPL
      - 'apps/epl/**'

# .github/workflows/nba.yml
on:
  push:
    paths:
      - 'packages/vinosports-core/**'   # core changes affect NBA
      - 'apps/nba/**'
```

### Deploy Flow

CI runs tests, then deploys on success. Each league has its own `fly.toml` and deploys independently via `flyctl deploy` scoped to its directory. The Docker build context is the monorepo root (to access `packages/vinosports-core`), with the league-specific Dockerfile.
