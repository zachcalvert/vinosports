# Pre-Launch Plan

Everything that needs to happen before the first Fly.io deploy. Ordered by dependency chain — schema changes and feature work first, cleanup and infra last.

---

## Phase 1: Data & Bug Fixes

### 1a. ~~Fix NBA Score Updates~~ DONE
Root cause: sportsdata.io's free trial returns **scrambled data** (scores randomly fuzzed 5-20%). Additionally, a race condition in `get_live_scores()` meant final scores were missed when `AreAnyGamesInProgress` returned `False` after the last game ended.

**Resolution:** Migrated both NBA and EPL to **BallDontLie** (All-Star tier, $9.99/mo per sport). Real, unscrambled data with 60 req/min. All 1231 NBA games and 380 EPL matches re-seeded with correct scores. See `docs/0013-BALLDONTLIE_MIGRATION.md` for full details.

### 1b. Prune Bot Roster
There are too many homer bots in NBA and some EPL bots could be trimmed too. Goals:
- **NBA**: reduce homer bot count — identify which ones overlap in personality or back less-interesting teams, and deactivate or remove them
- **EPL**: review the 8 homer bots (ARS, CHE, LIV, MUN, MCI, TOT, NEW, EVE) and decide if all 8 are needed, or if some lower-engagement ones can be cut
- Pruned bots should be soft-deleted (set `is_active=False` on BotProfile) so their historical bets/comments are preserved

Do this before globalizing bot profiles (Phase 2) — easier to prune while the models are still per-league, and fewer records to migrate.

---

## Phase 2: Schema Changes (Bot Globalization)

All the model restructuring that changes the DB schema. Do this while there's no production database to worry about.

### 2a. Globalize Bot Profiles
Currently bot profiles are per-league (EPL `BotProfile` and NBA `BotProfile` are separate models/tables). Refactor so:
- **One BotProfile per bot, living in core** (or hub) rather than duplicated per league
- A bot can be **active in EPL, NBA, or both** — controlled by a M2M or flags on the profile
- A bot can have **favorite teams in both leagues** (e.g., homer for Arsenal in EPL and Celtics in NBA)
- A bot has **one strategy** — the strategy is cross-league (frontrunner, underdog, homer, etc.) and the league-specific strategy implementations adapt to sport-specific odds/markets
- Migration path: merge existing EPL + NBA bot profiles into unified records, preserve FKs from existing bets/comments

### 2b. Globalize Schedule Templates
Same treatment as bot profiles:
- **One set of schedule templates in core** (or hub), not per-league
- The window schema (`days`, `hours`, `bet_probability`, `comment_probability`, `max_bets`, `max_comments`) is already sport-neutral
- Each league's Celery tasks reference the same shared templates
- League-specific window overrides per bot — a bot gets one base template but leagues can override specific values (e.g., EPL bots go dormant in summer, NBA bots ramp up during playoffs)
- EPL-specific templates (match-day focused: Thu-Mon) and NBA-specific templates can coexist in the same table

### 2c. Port Schedule Templates to EPL
With global templates from 2b in place, this becomes: update EPL bot tasks to use the schedule system.
1. Copy `schedule.py` helpers (`get_active_window`, `is_bot_active_now`, `roll_action`) to EPL — they're sport-agnostic
2. Refactor EPL bot tasks (`run_bot_strategies`, `generate_prematch_comments`, `generate_postmatch_comments`) to check schedule templates per bot instead of fixed cron times
3. Switch EPL Celery beat to hourly dispatch (`:05` bet, `:15` prematch, `:30` postmatch)
4. Assign EPL bots to appropriate templates — match days are Thu-Mon, not every day like NBA

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

### 4a. Squash Migrations
Both EPL and NBA apps have accumulated dev migrations, plus the new migrations from Phase 2. Squash them all down to clean initial migrations before the first deploy creates a production database. This is the last step before infra — no more schema changes after this.

### 4b. CI Workflows
Define and implement the CI pipeline. Decisions needed:
- **Trigger**: on push to `main`? On PR? Both?
- **Steps**: lint (ruff), test (pytest across core/epl/nba), build Docker images
- **Deploy**: auto-deploy to Fly on merge to `main`, or manual promote?
- **Secrets**: `BDL_API_KEY`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, `REDIS_URL` — managed via Fly secrets
- **DB migrations**: run as a Fly release command on deploy

### 4c. Fly.io Configuration
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
