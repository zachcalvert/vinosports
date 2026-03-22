# 0000: Vinosports Initial Vision

## Motivation

Two existing Django betting simulation apps — [epl-bets](https://github.com/zachcalvert/epl-bets) and nba-bets — share ~60-70% identical infrastructure code. Both use the same tech stack (Django 5.1, Daphne, Channels, Celery, Redis, HTMX, PostgreSQL) and the same architectural patterns (real-time WebSocket score updates, play-money betting, AI bot commentary via Claude, challenges, rewards, activity feeds).

The domain-specific code — team/match models, data ingestion from sport APIs, odds representation, bet market types — is concentrated in a small number of files per project. Everything else (user management, balance tracking, bet settlement flow, bot infrastructure, challenges, rewards) is duplicated.

The long-term vision is a unified sports platform at **vinosports.com** covering multiple leagues (EPL, NBA, NFL, World Cup, March Madness) with a shared frontend shell — similar to how ESPN presents a uniform interface across sports. The domain vinosports.com has been purchased for this purpose.

## Architecture

### Monorepo with Shared Package

```
vinosports/
├── packages/
│   └── vinosports-core/              # Shared pip-installable Django package
│       └── src/vinosports/
│           ├── core/                  # BaseModel, id_hash generation
│           ├── users/                 # Concrete User model (email auth, avatars)
│           ├── betting/               # Shared betting infrastructure
│           ├── bots/                  # Bot profile + Claude integration
│           ├── activity/              # Real-time activity feed
│           ├── discussions/           # Match/game comments
│           ├── challenges/            # Daily/weekly challenges
│           └── rewards/               # Reward distribution system
├── apps/
│   ├── epl/                           # EPL Django project
│   └── nba/                           # NBA Django project
└── docs/
```

Each league is a standalone Django project that installs `vinosports-core` as an editable dependency. League projects contain only domain-specific code: team/match models, data ingestion services, odds engines, bet market definitions, sport-specific Celery schedules, and HTMX templates.

### Abstract vs Concrete Model Split

**Concrete models in vinosports-core** are identical across all leagues and carry their own migrations:
- `User` (email auth, display name, currency, avatar, is_bot flag)
- `UserBalance`, `BalanceTransaction`, `UserStats` (play-money economy)
- `Badge`, `UserBadge` (achievement system)
- `Bankruptcy`, `Bailout` (going broke and recovery)
- `ChallengeTemplate`, `Challenge`, `UserChallenge` (challenge engine)
- `Reward`, `RewardDistribution`, `RewardRule` (reward distribution)

**Abstract models in vinosports-core** define shared structure; league projects create concrete versions adding sport-specific fields:
- `AbstractBetSlip` — shared: user, stake, status, payout. League adds: match/game FK, selection choices, odds format
- `AbstractParlay`, `AbstractParlayLeg` — same pattern
- `AbstractComment` — shared: user, parent, body. League adds: match/game FK
- `AbstractBotProfile`, `AbstractBotComment` — shared: persona, Claude integration. League adds: strategy choices, match/game FK
- `AbstractActivityEvent` — shared: message, broadcast state. League adds: sport-specific event types

### Why Abstract Models for Betting

The bet market structures differ fundamentally between sports:
- **EPL**: 1X2 market (Home Win / Draw / Away Win), decimal odds (e.g., 2.45)
- **NBA**: Three markets (Moneyline / Spread / Total), American odds (e.g., -110, +150), point spreads and over/under lines

Forcing these into a single concrete model would require nullable fields, conditional logic, and a leaky abstraction. Abstract bases let each sport define its natural betting vocabulary while sharing the settlement flow, balance tracking, and payout mechanics.

### App Label Strategy

Django identifies apps by their `app_label`. Core apps use simple labels (`users`, `betting`, `challenges`, `rewards`). League-specific apps that extend core functionality use prefixed labels to avoid collisions:

| vinosports-core App | Label | League App | Label |
|---------------------|-------|------------|-------|
| `vinosports.users` | `users` | — | — |
| `vinosports.betting` | `betting` | `epl/betting` | `epl_betting` |
| `vinosports.challenges` | `challenges` | — | — |
| `vinosports.rewards` | `rewards` | — | — |
| — | — | `epl/matches` | `matches` |
| — | — | `epl/bots` | `epl_bots` |

### What's Excluded

- **Forum/board posts** — Dropped from vinosports-core. All user discussion happens on match/game detail pages via the Comment model.
- **Frontend unification** — Future work. Current focus is backend package extraction. The unified vinosports.com shell will be a separate frontend project that consumes league APIs.

## Tech Stack (Inherited from EPL Bets)

- **Django 5.1** with custom User model
- **Daphne** ASGI server for WebSocket support
- **Django Channels** + **channels-redis** for real-time updates
- **Celery** + **Redis** for background task scheduling
- **PostgreSQL** for persistence
- **HTMX** for server-rendered interactive UI (no JS framework)
- **Anthropic Claude API** for AI bot commentary
- **httpx** for external API calls

## Design Principles

1. **EPL Bets is the reference** — When in doubt, follow the patterns established in epl-bets. It's the more mature, battle-tested codebase.
2. **Domain isolation** — League-specific code never leaks into vinosports-core. The shared package has no knowledge of any specific sport.
3. **Abstract bases over GenericForeignKeys** — Prefer abstract models with explicit FKs over Django's ContentType/GenericFK system. Simpler queries, better type safety, clearer migrations.
4. **Additive league projects** — Adding a new league (NFL, March Madness) should require only: data models, API client, odds/settlement logic, Celery schedule, and templates. Everything else comes from vinosports-core.
