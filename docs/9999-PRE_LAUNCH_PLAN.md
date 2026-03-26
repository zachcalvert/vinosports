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

## ~~Phase 3: UI~~ DONE

### ~~3a. Global Navbar from Hub~~ DONE
Added a two-tier navigation system. See `docs/0015-GLOBAL_NAVBAR.md` for full details.

**Tier 1 — Global navbar:** Shared template partial in `vinosports-core` (`vinosports/components/global_navbar.html`). Logo, league tabs with active indicator, user auth dropdown. Appears on all three apps.

**Tier 2 — League sidebar:** Left sidebar on league apps (EPL/NBA) with page-specific links (Dashboard, Leaderboard, Odds, etc.). Sticky on desktop, slide-in drawer on mobile. Hub has no sidebar.

**Key implementation details:**
- Shared `vinosports.context_processors.global_nav` provides `leagues`, `hub_url`, `current_league` to all apps
- Each app has `CURRENT_LEAGUE` and `LEAGUE_URLS` in settings
- Auth URLs respect the cross-port CSRF constraint (login/signup to hub, logout/theme to current app)
- Template discovery uses Docker volume mount path with site-packages fallback

---

## Phase 4: Cleanup & Infrastructure

Everything here depends on the schema changes being done first.

### ~~4a. Test Infrastructure & Baseline Coverage~~ DONE
Established test coverage across the entire monorepo — 616 tests passing at 53% baseline coverage. Scope expanded well beyond the original EPL-only plan:
- **vinosports-core** (79 tests, new) — models, users, betting, bots, challenges, rewards, middleware
- **hub** (47 tests, new) — models, forms, views, template tags
- **EPL** (41 tests, new) — odds engine, settlement, models, views
- **NBA** (449 tests, fixed) — all 113 failures from unified project migration resolved

Also found and fixed a **production bug**: EPL settlement code referenced nonexistent `BetSlip.Status` inner class (should be standalone `BetStatus` enum) across 6 source files — would have crashed on any bet settlement.

See `docs/0027-TEST_INFRASTRUCTURE.md` for full details.

### 4b–4d → Moved to Phase 5
Squash migrations, CI, and Fly.io moved to Phase 5 — more models expected before we lock down the schema.

---

## Phase 5: Deploy Prep

Everything here depends on the schema being finalized. No more model changes after this phase starts.

### 5a. Squash Migrations
Both EPL and NBA apps have accumulated dev migrations, plus the new migrations from Phase 2. Squash them all down to clean initial migrations before the first deploy creates a production database. This is the last step before infra — no more schema changes after this.

### 5b. CI Workflows
Define and implement the CI pipeline. Decisions needed:
- **Trigger**: on push to `main`? On PR? Both?
- **Steps**: lint (ruff), test (pytest across core/epl/nba), build Docker images
- **Deploy**: auto-deploy to Fly on merge to `main`, or manual promote?
- **Secrets**: `BDL_API_KEY`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, `REDIS_URL` — managed via Fly secrets
- **DB migrations**: run as a Fly release command on deploy

### 5c. Fly.io Configuration
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
