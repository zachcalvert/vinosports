# Pre-Launch Plan

Everything that needs to happen before the first Fly.io deploy. Ordered by dependency chain — schema changes and feature work first, cleanup and infra last.

---

## Phase 1: Data & Bug Fixes

### 1a. ~~Fix NBA Score Updates~~ DONE
Root cause: sportsdata.io's free trial returns **scrambled data** (scores randomly fuzzed 5-20%). Additionally, a race condition in `get_live_scores()` meant final scores were missed when `AreAnyGamesInProgress` returned `False` after the last game ended.

**Resolution:** Migrated both NBA and EPL to **BallDontLie** (All-Star tier, $9.99/mo per sport). Real, unscrambled data with 60 req/min. All 1231 NBA games and 380 EPL matches re-seeded with correct scores. See `docs/0013-BALLDONTLIE_MIGRATION.md` for full details.

### ~~1b. Prune Bot Roster~~ DONE
Pruned from ~56 league-specific bots (41 NBA + 15 EPL) down to 8 global personality-first bots. Superseded by bot globalization (Phase 2) which replaced the per-league rosters entirely.

---

## ~~Phase 2: Schema Changes (Bot Globalization)~~ DONE

### ~~2a. Globalize Bot Profiles~~ DONE
Concrete `BotProfile` and `ScheduleTemplate` models now live in `vinosports.bots` (core package, app label `global_bots`). One profile per bot, shared across all leagues.

**Key decisions:**
- **Boolean flags** (`active_in_epl`, `active_in_nba`, `active_in_nfl`) instead of M2M — simpler, and only 2-3 leagues in scope
- **CharField team affiliations** (`nba_team_abbr`, `epl_team_tla`) instead of FKs — keeps core independent of league apps, and team changes are just a string edit in admin
- **Personality-only persona prompts** — no team references in the prompt. Team context is injected at comment-generation time by each league's tasks, so reassigning a bot's team is a single field change
- **Unified `StrategyType`** — superset of NBA + EPL strategies (frontrunner, underdog, spread_shark, parlay, total_guru, draw_specialist, value_hunter, chaos_agent, all_in_alice, homer, anti_homer)
- League apps keep only `BotComment` (concrete, FK to league-specific Game/Match + Comment models)

**The 8 authoritative bots:**

| Bot | NBA | EPL | Strategy |
|-----|-----|-----|----------|
| Tech Bro Chad | GSW | Chelsea | Homer |
| Dad Dan | OKC | Man City | Frontrunner |
| Dad Dave | OKC | Man United | Frontrunner |
| Lurker Larry | WAS | Fulham | Underdog |
| 90s Norman | CHI | Newcastle | Frontrunner |
| Deep State Quinn | PHX | West Ham | Chaos Agent |
| Conspiracy Carl | CHA | Crystal Palace | Underdog |
| StatSheet Nathan | — | Man United | Spread Shark |

Seeded via `docker compose exec hub-web python manage.py seed_bots`.

### ~~2b. Globalize Schedule Templates~~ DONE
6 schedule templates live in the global `ScheduleTemplate` model alongside `BotProfile`. Sport-agnostic schedule helpers (`get_active_window`, `is_bot_active_now`, `roll_action`) moved from NBA to `vinosports.bots.schedule` in the core package.

### ~~2c. Port Schedule Templates to EPL~~ DONE
With global templates from 2b in place, EPL bot tasks now use the schedule system:
1. ~~Copy `schedule.py` helpers to EPL~~ — helpers now live in core (`vinosports.bots.schedule`), already importable from EPL
2. ~~Refactor EPL bot tasks~~ — `run_bot_strategies`, `generate_prematch_comments`, and `generate_postmatch_comments` now check `get_active_window()` and `roll_action()` per bot before dispatching, matching the NBA pattern
3. ~~Switch EPL Celery beat to hourly dispatch~~ — `:05` bet, `:15` prematch, `:30` postmatch (was fixed cron on Thu-Sat/matchdays). Schedule templates now control which days/hours bots are active
4. ~~Assign EPL bots to appropriate templates~~ — all 8 bots have `schedule_template` set from the global `seed_bots` command

---

## Phase 3: UI

### 3a. Global Navbar from Hub
Add a shared top-level navbar served from the hub app that appears on all three apps (hub, EPL, NBA):
- Hub branding / home link at top level
- League links (EPL, NBA) as top-level nav items
- Each league app's existing navigation nests underneath its league section
- With subpath routing (`vinosports.com/epl/`, `vinosports.com/nba/`), navbar links are just relative paths in prod. In dev (separate ports), use absolute URLs via a settings-driven base URL
- Implementation: shared template partial in the core package that each app includes via template tag or base template inheritance

---

## Phase 4: Cleanup & Infrastructure

Everything here depends on the schema changes being done first.

### 4a. Add EPL Test Suite
The EPL app currently has no tests. The legacy `epl-bets` repo has a test suite that can be ported:
- Port relevant test modules (services, tasks, settlement, models) from `epl-bets`
- Update imports and factories to match the current EPL app structure
- Ensure pytest + factories are in EPL's dev dependencies
- Target the same patterns used in the NBA test suite (mock API clients, factory-based fixtures, behavior-focused assertions)

### 4b. Squash Migrations
Both EPL and NBA apps have accumulated dev migrations, plus the new migrations from Phase 2. Squash them all down to clean initial migrations before the first deploy creates a production database. This is the last step before infra — no more schema changes after this.

### 4c. CI Workflows
Define and implement the CI pipeline. Decisions needed:
- **Trigger**: on push to `main`? On PR? Both?
- **Steps**: lint (ruff), test (pytest across core/epl/nba), build Docker images
- **Deploy**: auto-deploy to Fly on merge to `main`, or manual promote?
- **Secrets**: `BDL_API_KEY`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, `REDIS_URL` — managed via Fly secrets
- **DB migrations**: run as a Fly release command on deploy

### 4d. Fly.io Configuration
Set up the single Fly app with multiple processes:
- `fly.toml` with `[processes]` for hub-web, epl-web, nba-web, epl-worker, epl-beat, nba-worker, nba-beat
- Reverse proxy (nginx or Caddy) as the entrypoint to route subpaths to the right process
- Shared PostgreSQL and Redis as Fly-managed or attached services
- Environment-aware settings (dev ports vs. prod subpaths)

---

## Out of Scope

### NFL
No NFL work before launch. NFL can be added as a third league post-launch following the same pattern as NBA.

---

## Decisions

- **Deploy topology**: One Fly app with multiple processes. Each Django project (hub, epl, nba) and each background service (workers, beat schedulers) runs as a separate process within the single app. This keeps shared sessions simple (one DB, one cookie domain) while still allowing `epl-web`, `nba-beat`, etc. as distinct process types in `fly.toml`
- **Domain structure**: `vinosports.com` with subpaths (`/epl/`, `/nba/`). Simplest option — one domain means shared cookies work naturally, no CORS issues, and the global navbar links are just relative paths. Likely needs a reverse proxy (Fly's built-in routing or nginx) to fan out subpaths to the right process
- **Bot globalization order**: Before first deploy. No rush on deploying, so do the migration to global bot profiles and templates cleanly before there's a production DB to worry about
- **Schedule template granularity**: League-specific window overrides. A bot gets one base set of windows from its template, but leagues can override specific values (e.g., EPL bots go dormant in summer, NBA bots ramp up during playoffs). This keeps the common case simple while handling seasonal differences
