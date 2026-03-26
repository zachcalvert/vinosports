# 0019: Unified Django Project

**Date:** 2026-03-25

## Overview

Merged three separate Django projects (hub, EPL, NBA) into a single Django project served by one web process. This eliminates `FORCE_SCRIPT_NAME`, nginx prefix stripping, and the multi-container web architecture that was the source of recurring WebSocket and static file routing issues. Docker services dropped from 8+ to 6. The entire URL space is now natively correct — no middleware hacks, no path rewriting, no cross-container session concerns.

## Motivation

The multi-project architecture introduced compounding pain:

1. **WebSocket routing failures.** Nginx stripped `/epl/` and `/nba/` prefixes before proxying, but Django Channels' `URLRouter` received paths without the prefix that `FORCE_SCRIPT_NAME` expected. A custom `ScriptNameStripMiddleware` partially fixed this but introduced new path-matching bugs (missing leading slashes). Every WebSocket feature required debugging the prefix dance.

2. **Static file 404s.** Requests for `/static/website/css/styles.css` from EPL pages hit `hub-web` instead of `epl-web` because nginx routed all `/static/` to the hub upstream. Each league's static namespace collided (`website/css/styles.css` existed in both EPL and NBA).

3. **Context processor scoping.** Each project ran its own set of context processors, but the shared `global_navbar.html` template needed data from all of them. `FORCE_SCRIPT_NAME` and `HUB_URL` were passed as settings and threaded through context processors in increasingly fragile ways.

4. **Operational overhead.** Three Dockerfiles, three web containers, three sets of volume mounts, separate migration commands, separate shell targets. Every infrastructure change had to be applied three times.

Since there was no production database or deployment, the cost of merging was purely the refactor itself — no migration history to preserve, no backwards compatibility to maintain.

## What Changed

### Directory Structure

```
# Before                          # After
apps/hub/                         hub/
  hub/                              models.py, views.py, ...
  config/                           templates/hub/
  Dockerfile
apps/epl/                         epl/
  matches/, betting/, ...           matches/, betting/, ...
  config/                           urls.py (league combiner)
  Dockerfile                        static/
apps/nba/                         nba/
  games/, betting/, ...             games/, betting/, ...
  config/                           urls.py (league combiner)
  Dockerfile                        templates/ (project-level)
                                    static/
                                  config/
                                    settings.py (unified)
                                    urls.py, asgi.py, celery.py
                                    middleware.py (LeagueMiddleware)
                                  Dockerfile (single)
                                  manage.py (root)
```

### Namespace Resolution

Every shared namespace got a league prefix to prevent collisions:

| Layer | Before | After |
|---|---|---|
| Python imports | `from matches.models` | `from epl.matches.models` |
| App labels | `matches`, `games` | `epl_matches`, `nba_games` |
| URL namespaces | `website:dashboard` | `epl_website:dashboard` |
| Template dirs | `betting/partials/` | `epl_betting/partials/` |
| Static dirs | `website/css/styles.css` | `epl_website/css/styles.css` |
| Model FK strings | `"matches.Match"` | `"epl_matches.Match"` |

### URL Routing

```python
# config/urls.py — single, flat, no prefix stripping
path("epl/", include("epl.urls"))
path("nba/", include("nba.urls"))
path("", include("hub.urls"))
```

URLs like `/epl/games/123/` now route directly through Django's URL resolver. No nginx rewriting, no `FORCE_SCRIPT_NAME`, no `SCRIPT_NAME` template variable.

### WebSocket Routing

```python
# config/asgi.py — nested URLRouter, no middleware hack
URLRouter([
    path("epl/", URLRouter(epl_matches_ws + epl_activity_ws + epl_rewards_ws)),
    path("nba/", URLRouter(nba_games_ws + nba_activity_ws)),
])
```

Templates connect directly: `ws-connect="/epl/ws/live/dashboard/"` instead of `ws-connect="{{ SCRIPT_NAME }}/ws/live/dashboard/"`.

### LeagueMiddleware

A 10-line middleware sets `request.league` based on the URL path prefix:

```python
if path.startswith("/epl/"):
    request.league = "epl"
elif path.startswith("/nba/"):
    request.league = "nba"
else:
    request.league = None
```

Each league's context processors guard on this value, short-circuiting with `{}` for requests outside their league. This prevents EPL's parlay slip query from running on NBA pages and vice versa.

### Infrastructure

| | Before | After |
|---|---|---|
| Web containers | 3 (hub-web, epl-web, nba-web) | 1 (web) |
| Celery workers | 2 (epl-worker, nba-worker) | 1 (worker, `-Q epl,nba`) |
| Celery beat | 2 (epl-beat, nba-beat) | 1 (beat) |
| Dockerfiles | 3 | 1 |
| Nginx upstreams | 3 (with prefix stripping) | 1 (passthrough) |
| Total services | 8+ | 6 |
| Migration commands | 2 (`migrate-epl`, `migrate-nba`) | 1 (`migrate`) |

### Admin Deduplication

Shared core models (`UserBalance`, `Badge`, `UserBadge`) were registered in both EPL and NBA admin modules. With a single project, these can only be registered once. EPL's admin retains the registrations (slightly richer with `UserBadgeInline`); NBA's duplicates were removed.

## What This Enables

### Simpler Feature Development

Adding a new league (NFL, MLB) means creating a new Python package at the repo root, adding it to `INSTALLED_APPS`, and adding one line to `config/urls.py`. No Dockerfile, no nginx upstream, no docker-compose service block, no `FORCE_SCRIPT_NAME` configuration.

### Cross-League Features

A unified project makes cross-league features trivial:

- **Combined leaderboard** across EPL + NBA (single DB query joining `UserBalance`)
- **Cross-league challenges** ("Place bets on 3 different leagues this week")
- **Unified activity feed** on the hub homepage
- **Shared admin dashboard** with all leagues visible

These were theoretically possible before (shared DB), but practically painful because each feature required coordinating across three separate Django processes.

### Reliable WebSocket Connections

WebSocket routing is now a standard Django Channels concern — no middleware, no path rewriting, no debugging which container received the upgrade request. The "Reconnecting..." status indicator that plagued the multi-project setup is gone.

### Simplified Deployment

One Docker image, one web process, one worker, one beat scheduler. Deployment scripts, CI pipelines, and health checks all target a single application. Horizontal scaling means running more instances of the same image, not managing separate deployments per league.

## Migration Notes

- All old migration files were deleted and regenerated with `makemigrations`
- The PostgreSQL schema was dropped and recreated (no production data to preserve)
- The `apps/` directory and per-project Dockerfiles/configs can be deleted
- `CLAUDE.md` should be updated to reflect the new structure (see [0000-INITIAL_VISION.md](./0000-INITIAL_VISION.md) for the original architecture)
- The `currency_tags` template warning is cosmetic — same templatetag name exists in hub, EPL, and NBA (each has its own copy for its templates)

## Related Docs

- [0000-INITIAL_VISION.md](./0000-INITIAL_VISION.md) — Original multi-project architecture rationale
- [0005-HUB_APPLICATION.md](./0005-HUB_APPLICATION.md) — Hub as central auth provider
- [0006-NBA_PORT.md](./0006-NBA_PORT.md) — NBA port from standalone to monorepo
- [0007-CENTRALIZED_AUTH.md](./0007-CENTRALIZED_AUTH.md) — Auth centralization into hub
- [0015-GLOBAL_NAVBAR.md](./0015-GLOBAL_NAVBAR.md) — Global navbar (now uses `request.league` instead of `FORCE_SCRIPT_NAME`)
