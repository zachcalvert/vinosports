# 0001: CI, Deployment & Infrastructure

## Infrastructure (Fly.io)

### Architecture

One Fly app, three process groups. The unified Django project (hub + EPL + NBA) runs as a single deployable unit.

```
vinosports (Fly app, iad region)
├── web     → daphne (HTTP + WebSocket)
├── worker  → celery worker -Q epl,nba,default
└── beat    → celery beat
```

Attached services:
- **Fly Postgres** (`vinosports-db`) — shared database for all leagues
- **Upstash Redis** (`vinosports-redis`) — Celery broker, Channels layer, cache
- **Tigris** (`vinosports-media`) — S3-compatible object storage for media uploads

### Why One App (Not Per-League)

The project was unified into a single Django process (see `docs/0019-UNIFIED_DJANGO_PROJECT.md`). One app means:
- Shared sessions and cookies work naturally (one domain, one DB)
- Single deploy deploys everything
- No cross-service networking complexity
- `LeagueMiddleware` handles `/epl/` and `/nba/` routing within the single process

### Domain

`vinosports.com` with subpaths (`/epl/`, `/nba/`). Dedicated IPv4 + IPv6. Fly handles TLS termination via Let's Encrypt. Daphne serves both HTTP and WebSocket — no nginx needed in production.

DNS (Gandi):
- `A` `@` → Fly dedicated IPv4
- `AAAA` `@` → Fly IPv6
- `CNAME` `www` → `vinosports.fly.dev.`

### Process Sizing

| Process | Memory | CPU | Purpose |
|---------|--------|-----|---------|
| web | 1GB | shared-1x | Daphne ASGI (HTTP + WS) |
| worker | 1GB | shared-1x | Celery (data ingestion, odds, bots, settlement) |
| beat | 256MB | shared-1x | Celery beat scheduler |

### Media Storage (Tigris)

User-uploaded files (profile images, bot portraits) are stored in Tigris, Fly's S3-compatible object storage. Configured via `STORAGES` in `config/settings.py` when `AWS_ENDPOINT_URL_S3` is set:

- **Bucket**: `vinosports-media` (public reads enabled)
- **URLs**: Virtual-hosted style — `https://vinosports-media.fly.storage.tigris.dev/<key>`
- **ACL**: `public-read` on upload; bucket set to public via `fly storage update vinosports-media --public`
- **Static files** remain served by WhiteNoise from the Docker image (not S3)

Env vars set automatically by `fly storage create`:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_ENDPOINT_URL_S3`
- `AWS_REGION`
- `BUCKET_NAME`

### Estimated Monthly Cost (~200 users, ~25 bots)

| Service | Spec | Cost |
|---------|------|------|
| Postgres (Fly) | shared-cpu, 256MB, 1GB disk | ~$7 |
| Redis (Upstash) | Free or $10 plan | $0–10 |
| Dedicated IPv4 | Static IP | $2 |
| web | shared-cpu-1x, 1GB | ~$7 |
| worker | shared-cpu-1x, 1GB | ~$7 |
| beat | shared-cpu-1x, 256MB | ~$3 |
| Tigris | Free tier (5GB storage, 10K requests) | $0 |
| Sentry | Free tier (5K errors/mo) | $0 |
| **Total** | | **~$26–36/mo** |

Claude API costs for bot commentary are separate and will likely exceed infrastructure costs.

---

## CI (GitHub Actions)

### Pipeline: `.github/workflows/ci.yml`

```
push to main / PR → lint → test → deploy (main only)
```

**Lint** — Ruff check + format (v0.15.7)

**Test** — pytest with parallel execution (`-n auto`), coverage across vinosports-core, hub, EPL, NBA. Services: PostgreSQL 16 + Redis 7.

**Deploy** — `flyctl deploy --remote-only` after lint+test pass. Only runs on pushes to `main` (not PRs). Requires `FLY_API_TOKEN` GitHub secret.

### Deploy Flow

1. Push to `main` triggers CI
2. Lint and test run in parallel
3. On success, `flyctl deploy --remote-only` builds the Docker image on Fly's remote builders
4. Fly runs the release command (`python manage.py migrate --noinput`)
5. New machines roll out (web, worker, beat)

---

## Monitoring (Sentry)

Error tracking via Sentry cloud (free tier). SDK auto-discovers Django and Celery integrations.

- **DSN** set via `SENTRY_DSN` Fly secret
- **PII collection** enabled (`send_default_pii=True`) for request headers and user info
- **Performance** traces sampled at 10%
- **Profiles** sampled at 10%

---

## Provisioning Checklist

```bash
# Create app
fly apps create vinosports

# Dedicated IPv4
fly ips allocate-v4 --app vinosports

# Postgres
fly postgres create --name vinosports-db --region iad --vm-size shared-cpu-1x --volume-size 1
fly postgres attach vinosports-db --app vinosports

# Redis
fly redis create --name vinosports-redis --region iad

# Tigris (S3 media storage)
fly storage create --name vinosports-media --app vinosports
fly storage update vinosports-media --public

# Secrets
fly secrets set \
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')" \
  REDIS_URL="<from fly redis create output>" \
  BDL_API_KEY="<key>" \
  ANTHROPIC_API_KEY="<key>" \
  SENTRY_DSN="<from sentry project>"

# Domain + TLS
fly certs add vinosports.com
fly certs add www.vinosports.com
# → Configure DNS: A/AAAA for @, CNAME www → vinosports.fly.dev

# GitHub Actions secret
fly tokens create deploy -x 999999h
# → Add as FLY_API_TOKEN in GitHub repo settings

# First deploy
fly deploy

# Seed data
fly ssh console
python manage.py seed
```

---

## Production Debugging

```bash
# Tail logs (all processes)
fly logs

# Tail logs (specific process)
fly logs -p web
fly logs -p worker
fly logs -p beat

# SSH into web machine
fly ssh console

# Run management commands
fly ssh console -C "python manage.py shell"

# Check machine status
fly status

# Check certificate status
fly certs check vinosports.com
```
