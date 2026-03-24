# Pre-Launch Plan

Everything that needs to happen before the first Fly.io deploy. Items are grouped by theme, not priority or order.

---

## 1. Infrastructure & CI

### 1a. Squash Migrations
Both EPL and NBA apps have accumulated dev migrations. Squash them down to clean initial migrations before the first deploy creates a production database.

### 1b. CI Workflows
Define and document the desired CI pipeline. Decisions needed:
- **Trigger**: on push to `main`? On PR? Both?
- **Steps**: lint (ruff), test (pytest across core/epl/nba), build Docker images
- **Deploy**: auto-deploy to Fly on merge to `main`, or manual promote?
- **Secrets**: `FOOTBALL_DATA_API_KEY`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, `REDIS_URL` — managed via Fly secrets
- **Docker**: single multi-service Fly app or separate apps per service (hub, epl, nba, worker, beat)?
- **DB migrations**: run automatically on deploy or as a separate release command?

---

## 2. Bot Overhaul

### 2a. Prune Bot Roster
There are too many homer bots in NBA and some EPL bots could be trimmed too. Goals:
- **NBA**: reduce homer bot count — identify which ones overlap in personality or back less-interesting teams, and deactivate or remove them
- **EPL**: review the 8 homer bots (ARS, CHE, LIV, MUN, MCI, TOT, NEW, EVE) and decide if all 8 are needed, or if some lower-engagement ones can be cut
- Pruned bots should be soft-deleted (set `is_active=False` on BotProfile) so their historical bets/comments are preserved

### 2b. Globalize Bot Profiles
Currently bot profiles are per-league (EPL `BotProfile` and NBA `BotProfile` are separate models/tables). Refactor so:
- **One BotProfile per bot, living in core** (or hub) rather than duplicated per league
- A bot can be **active in EPL, NBA, or both** — controlled by a M2M or flags on the profile
- A bot can have **favorite teams in both leagues** (e.g., homer for Arsenal in EPL and Celtics in NBA)
- A bot has **one strategy** — the strategy is cross-league (frontrunner, underdog, homer, etc.) and the league-specific strategy implementations adapt to sport-specific odds/markets
- Migration path: merge existing EPL + NBA bot profiles into unified records, preserve FKs from existing bets/comments

### 2c. Globalize Schedule Templates
Same treatment as bot profiles:
- **One set of schedule templates in core** (or hub), not per-league
- The window schema (`days`, `hours`, `bet_probability`, `comment_probability`, `max_bets`, `max_comments`) is already sport-neutral
- Each league's Celery tasks reference the same shared templates
- EPL-specific templates (match-day focused: Thu-Mon) and NBA-specific templates can coexist in the same table — bots pick up the right one via their profile assignment

### 2d. Port Schedule Templates to EPL
Currently EPL bots fire at fixed times (Thu/Fri/Sat 8am for betting, every 2h for comments). Port the NBA schedule template system:
1. Create concrete `ScheduleTemplate` model in EPL (or use the new global one from 2c)
2. Add `schedule_template` FK to EPL `BotProfile`
3. Copy `schedule.py` helpers (`get_active_window`, `is_bot_active_now`, `roll_action`) — they're sport-agnostic
4. Refactor EPL bot tasks to check schedule templates per bot instead of fixed cron times
5. Switch EPL Celery beat to hourly dispatch (`:05` bet, `:15` prematch, `:30` postmatch)
6. Define EPL-appropriate templates — match days are Thu-Mon, not every day like NBA

> **Note**: If 2c (globalize templates) happens first, this becomes "assign EPL bots to shared templates and update EPL tasks to use the schedule system" rather than creating EPL-specific models.

---

## 3. Data & Scores

### 3a. Fix NBA Score Updates
There are finished games in the local DB with partial/stale scores (e.g., 47-32 for a completed game). Investigate:
- Is the score update task failing silently or stopping mid-game?
- Is the API returning partial data that we're treating as final?
- Are games being marked `FINISHED` before the final score is fetched?
- Fix the root cause, then backfill correct final scores for affected games

---

## 4. UI & Navigation

### 4a. Global Navbar from Hub
Add a shared top-level navbar served from the hub app that appears on all three apps (hub, EPL, NBA):
- Hub branding / home link at top level
- League links (EPL, NBA) as top-level nav items
- Each league app's existing navigation nests underneath its league section
- Since apps run on separate ports locally, the navbar links use absolute URLs (`localhost:7999`, `localhost:8000`, `localhost:8001` in dev, proper domains in prod)
- Implementation options: shared Django template include (fetched via context processor or template tag), or an iframe/SSI approach. Simplest is probably a shared template partial in the core package that each app includes

---

## 5. Out of Scope

### 5a. NFL
No NFL work before launch. NFL can be added as a third league post-launch following the same pattern as NBA.

---

## Open Questions

- **Deploy topology**: One Fly app with multiple processes, or separate Fly apps for hub/epl/nba? Separate apps means separate domains and real cross-origin auth concerns
- **Domain structure**: `vinosports.com` with subpaths (`/epl/`, `/nba/`) vs. subdomains (`epl.vinosports.com`) vs. separate domains? This affects shared sessions and the global navbar
- **Bot globalization order**: Should 2b/2c (globalize profiles + templates) happen before or after the first deploy? It's a significant migration. Could deploy with per-league bots first and unify later
- **Schedule template granularity**: With global templates, should there be league-specific window overrides, or do bots just get one set of windows that applies to all leagues they're active in?
