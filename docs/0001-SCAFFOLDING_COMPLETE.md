# 0001: Scaffolding Complete

**Date:** 2026-03-22

## What Was Built

The vinosports monorepo is fully scaffolded and running locally with Docker Compose. The EPL project has been ported from the standalone [epl-bets](https://github.com/zachcalvert/epl-bets) repo. The NBA project has a working skeleton with models and consumers but no views, services, or templates yet.

## Repository Structure

```
vinosports/
├── packages/vinosports-core/       # Shared pip-installable Django package
├── apps/epl/                        # EPL betting simulation (fully ported)
├── apps/nba/                        # NBA betting simulation (skeleton)
├── docker-compose.yml               # Local dev: postgres, redis, web/worker/beat per league
├── docs/
└── pyproject.toml                   # Workspace-level ruff config
```

## vinosports-core Package

**8 Django apps** providing shared infrastructure:

| App | Type | Contents |
|-----|------|----------|
| `core` | Abstract only | `BaseModel` (id_hash, timestamps), `generate_short_id()` |
| `users` | Concrete | `User` (email auth, display_name, avatars, is_bot), `UserManager` |
| `betting` | Mixed | **Concrete:** UserBalance, BalanceTransaction, UserStats, Badge, UserBadge, Bankruptcy, Bailout. **Abstract:** AbstractBetSlip, AbstractParlay, AbstractParlayLeg. **Utilities:** `balance.py`, `constants.py`, `leaderboard.py` |
| `challenges` | Concrete | ChallengeTemplate, Challenge, UserChallenge |
| `rewards` | Concrete | Reward, RewardDistribution, RewardRule + `_broadcast_rewards()` |
| `discussions` | Abstract only | AbstractComment |
| `activity` | Abstract only | AbstractActivityEvent |
| `bots` | Abstract only | AbstractBotProfile, AbstractBotComment |

Also includes `middleware.py` (BotScannerBlockMiddleware).

## EPL Project (`apps/epl/`)

Fully ported from epl-bets with all imports remapped to vinosports-core:

- **matches/** — Team, Match, Standing, MatchStats, MatchNotes, Odds models + services (football-data.org client) + tasks (fetch teams/fixtures/standings/live scores) + views + WebSocket consumer + template tags
- **betting/** — BetSlip, Parlay, ParlayLeg (1X2 markets, decimal odds) + views + tasks (odds generation, settlement) + context processors + forms + signals
- **bots/** — BotProfile, BotComment + strategies (8 types) + registry (15 bots) + comment service (Claude API) + tasks
- **discussions/** — Comment (FK → Match) + views + forms
- **activity/** — ActivityEvent + consumer + tasks + context processor
- **challenges/** — views + urls + engine + tasks (rotation, expiration)
- **rewards/** — NotificationConsumer + context processor
- **website/** — Auth views, account/avatar, admin dashboard, theme, SiteSettings + template tags (currency, match) + 80 HTMX templates

## NBA Project (`apps/nba/`)

Skeleton with models only — proves the architecture works with a second league:

- **games/** — Team, Game, Standing, GameStats, Odds (American format) + WebSocket consumer
- **betting/** — BetSlip (moneyline/spread/total), Parlay, ParlayLeg
- **bots/** — BotProfile, BotComment (no strategies yet)
- **discussions/** — Comment (FK → Game)
- **activity/** — ActivityEvent

## Docker Compose Stack

```
postgres (shared DB, unified public schema)
redis
epl-web (Daphne, port 8000) + epl-worker + epl-beat
nba-web (Daphne, port 8001) + nba-worker + nba-beat
```

Both league projects share one Postgres database — one user account, one balance, one badge collection across all leagues. Celery workers and beat schedulers are league-specific.

## Key Architectural Decisions Made

1. **Abstract vs concrete split** — Models identical across leagues are concrete in vinosports-core (one migration set). Models that differ per sport are abstract bases that league projects extend.
2. **App labels** — Core apps use simple labels (`users`, `betting`). League-specific apps use prefixed labels (`epl_betting`, `nba_betting`) to avoid collisions.
3. **Odds model stays league-specific** — EPL uses 3 decimal fields (home_win/draw/away_win). NBA uses American odds with spread/total lines. Too different to abstract.
4. **Board app dropped** — Forum/board posts removed entirely. All discussion happens on match/game detail pages via Comments.
5. **Single database** — Both leagues share one Postgres instance with a unified `public` schema. Shared tables (users, balances, badges) enable cross-league identity.

## What's Not Done Yet

- No data in the database (teams, matches, standings, odds)
- No bot users created
- No CI/CD pipelines
- No Fly.io deployment config
- NBA project has no views, services, tasks, or templates
- No tests ported
