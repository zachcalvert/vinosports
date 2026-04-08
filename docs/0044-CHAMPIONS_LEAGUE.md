# 0044: UEFA Champions League

**Date:** 2026-04-08

> Status: **Implemented** (Phases 1-8 complete)


## Context

The UEFA Champions League (UCL) is a natural addition to vinosports. The 2024-25 season introduced a new 36-team "Swiss model" league phase (8 matchdays, single table) followed by a knockout playoff bracket through the final. This hybrid format sits between our existing EPL (pure league) and World Cup (pure tournament) implementations — the league phase resembles EPL standings, while the knockout rounds mirror the World Cup bracket.

- **Data source**: BallDontLie UCL v1 API (All-Star tier, 60 req/min)
- **Base URL**: `https://api.balldontlie.io/ucl/v1`
- **Auth**: Same `BDL_API_KEY` already used for EPL/NBA — no new key needed
- **URL**: vinosports.com/ucl/
- **Odds format**: Decimal 1X2 (same as EPL and World Cup — it's football)
- **Settlement rule**: Bets settle on 90-minute result only (standard 1X2 for football)
- **Season convention**: Start year (e.g., `2025` = 2025-26 season)
- **Historical data**: 2010-present


## API Availability (All-Star Tier)

| Endpoint | Notes |
|----------|-------|
| `GET /teams` | 36 teams per season. Returns id, name, short_name, abbreviation, location |
| `GET /matches` | Filterable by season, dates[], team_ids[]. Includes venue_name, venue_city, attendance, match name/short_name (useful for knockout round labels like "Semifinal 1") |
| `GET /standings` | group_name ("League Phase"), qualification notes, rank_change |
| `GET /match_events` | Goals, cards, substitutions with minute/period |
| `GET /match_lineups` | Starters, formation positions |
| `GET /players` | Player bios, citizenship |
| `GET /rosters` | Squad lists per team per season |

**Not available (GOAT tier only):** `/odds`, `/player_match_stats`, `/team_match_stats` — we generate our own odds, so this doesn't matter.

**Key API traits:**
- Response format is identical to EPL BDL — same pagination (`next_cursor`), same auth header, same `{"data": [...], "meta": {...}}` wrapper
- Match status strings are the same: `STATUS_FIRST_HALF`, `STATUS_HALFTIME`, `STATUS_EXTRA_TIME`, `STATUS_PENALTY`, etc. — the existing EPL status map works directly
- Team IDs are shared across BDL soccer APIs (Arsenal = id 2 in both EPL and UCL)
- UCL adds fields EPL lacks: `venue_name`, `venue_city`, `attendance`, match `name`/`short_name`


## UCL Tournament Structure (New Format, 2024-25 onward)

### League Phase (8 matchdays, Sep–Jan)
- 36 teams in a single league table (no groups)
- Each team plays 8 matches (4 home, 4 away) against 8 different opponents
- Standings determine seeding/qualification:
  - **Positions 1-8**: Advance directly to Round of 16
  - **Positions 9-24**: Enter knockout playoffs (two-legged ties)
  - **Positions 25-36**: Eliminated

### Knockout Phase (Feb–Jun)
- **Knockout Playoffs** (Round of 32): Positions 9-16 (seeded) vs 17-24 (unseeded), two legs
- **Round of 16**: 8 league phase winners + 8 playoff winners, two legs
- **Quarter-finals**: Two legs
- **Semi-finals**: Two legs
- **Final**: Single match at neutral venue

### Key differences from World Cup
- **Two-legged ties** in knockouts (home + away, aggregate score decides) — World Cup is single match
- **No groups** — single league table instead of 12 groups of 4
- **Away goals rule abolished** — ties go to extra time + penalties in the second leg
- **Club teams** not national teams — no confederations, but country/league of origin matters for context
- **Longer calendar** — spans Sep to Jun vs World Cup's 5-week window


## Phase 1: Package Skeleton + Core Models

Create `ucl/` at the repo root with prefixed sub-apps.

```
ucl/
  __init__.py
  urls.py
  matches/     (label: ucl_matches)
  betting/     (label: ucl_betting)
  bots/        (label: ucl_bots)
  discussions/ (label: ucl_discussions)
  activity/    (label: ucl_activity)
  rewards/     (label: ucl_rewards)
  website/     (label: ucl_website)
  tests/
```

### Models — `ucl/matches/models.py`

**Team**
- `external_id` (IntegerField, unique) — BDL team ID
- `name`, `short_name`, `tla` — Display names
- `crest_url`, `crest_image` — Team logos
- `country` (CharField) — Country of origin (e.g., "England", "Spain")
- `domestic_league` (CharField) — e.g., "Premier League", "La Liga" (useful for context/display)
- No `confederation` — all teams are UEFA members

**Stage**
- `name`, `stage_type` (unique choices), `order`
- Stage types: `LEAGUE_PHASE`, `KNOCKOUT_PLAYOFF`, `ROUND_OF_16`, `QUARTER`, `SEMI`, `FINAL`
- No THIRD_PLACE (UCL doesn't have one)

**Match**
- `external_id` (IntegerField, unique)
- `home_team`, `away_team` (FK to Team)
- `stage` (FK to Stage)
- `matchday` (IntegerField, nullable) — 1-8 for league phase, null for knockouts
- `leg` (IntegerField, nullable) — 1 or 2 for knockout ties, null for league phase and final
- `tie_id` (CharField, nullable) — Links two legs of same knockout tie (e.g., "QF-1" for quarter-final tie 1)
- Scoring:
  - `home_score`, `away_score` — 90-minute result
  - `home_score_et`, `away_score_et` — After extra time (cumulative, second leg only)
  - `home_score_penalties`, `away_score_penalties` — Penalty shootout (second leg only)
- `status` — Same choices as World Cup: SCHEDULED, TIMED, IN_PLAY, PAUSED, EXTRA_TIME, PENALTY_SHOOTOUT, FINISHED, POSTPONED, CANCELLED
- `kickoff` (DateTimeField)
- `venue_name`, `venue_city` — From BDL (unlike EPL where venue is on Team)
- `season` (CharField, e.g., "2025")
- `slug` (auto-generated, unique)
- Properties:
  - `is_knockout` — True if stage != LEAGUE_PHASE
  - `is_second_leg` — True if leg == 2
  - `winner` — Resolves via penalties > ET > 90-min (second leg considers aggregate)

**Standing** — League phase table
- `team` (FK), `season` — unique together
- `position`, `played`, `won`, `drawn`, `lost`, `goals_for`, `goals_against`, `goal_difference`, `points`
- `qualification_note` (CharField, nullable) — From BDL: "Round of 16", "Knockout playoffs", "Eliminated"

**Odds**
- Same as EPL/WC: match FK, bookmaker, home_win/draw/away_win decimal, fetched_at
- Unique together: (match, bookmaker)

### Config changes (8 files)

Per the [Adding a New League checklist](0043-ADDING_A_NEW_LEAGUE.md):
- `config/settings.py` — INSTALLED_APPS, context processors, LEAGUE_URLS, CELERY_TASK_ROUTES, CELERY_BEAT_SCHEDULE, UCL_CURRENT_SEASON, logging
- `config/urls.py` — `path("ucl/", include("ucl.urls"))`
- `config/middleware.py` — `elif path.startswith("/ucl/"): request.league = "ucl"`
- `config/asgi.py` — Import UCL WS routing, add `path("ucl/", URLRouter(...))`
- `config/celery.py` — autodiscover_tasks for all UCL sub-apps
- `docker-compose.yml` — Volume mounts for ucl/, worker queue
- `fly.toml` — Add `ucl` to worker queue
- `tailwind.config.js` — Add `./ucl/**/templates/**/*.html`
- `Makefile` — Seed commands, test coverage


## Phase 2: Data Client + Seed Command

### `ucl/matches/services.py`

**UCLDataClient** — mirrors `FootballDataClient` from EPL almost exactly:
- Base URL: `https://api.balldontlie.io/ucl/v1`
- Auth: `settings.BDL_API_KEY` (same key)
- Pagination: Same cursor-based `_get_all()` pattern
- Status normalization: Reuse the same status map from EPL (identical strings)
- Match normalization: Add `venue_name`, `venue_city`, `name` (match label), `short_name` fields

**Sync functions:**
- `sync_stages()` — Create 6 stages (LEAGUE_PHASE through FINAL)
- `sync_teams(season, offline=False)` — Upsert teams with country/domestic_league
- `sync_matches(season, offline=False)` — Upsert matches, assign stage from BDL match name/phase, derive `leg` and `tie_id` for knockout ties
- `sync_standings(season, offline=False)` — Upsert standings with qualification_note from BDL `note` field
- `poll_live_scores()` — Same pattern as WC: check IN_PLAY/PAUSED/EXTRA_TIME matches, broadcast WS updates, trigger settlement on FINISHED

**Seed command:** `ucl/website/management/commands/seed_ucl.py`
- Flags: `--season` (default: `UCL_CURRENT_SEASON`), `--offline`, `--skip-odds`
- Flow: stages → teams → matches → standings → odds

**Static data:** Bundle `ucl/matches/static_data/{teams,matches,standings}.json` for offline seeding (fetch once from BDL, commit to repo).


## Phase 3: Betting Models + Odds Engine

### `ucl/betting/models.py`

Mirror World Cup betting models — UCL is also 1X2 football:

- **BetSlip** — extends AbstractBetSlip. Selection: HOME_WIN / DRAW / AWAY_WIN. Settles on 90-minute result only (even in knockout second legs — a 1-1 draw after 90 is a DRAW bet win regardless of aggregate/ET/pens)
- **Parlay / ParlayLeg** — Same as WC/EPL
- **FuturesMarket** — MarketType: WINNER, FINALIST, LEAGUE_PHASE_TOP_8 (auto-qualify for R16)
- **FuturesOutcome / FuturesBet** — Same pattern

### `ucl/betting/odds_engine.py`

Adapted from EPL odds engine (both are football 1X2):
- Team strength from league phase standings (points, GD) + historical club coefficients
- Home advantage factor
- Margin ~8%, clamp to [1.10, 20.00]
- `generate_all_upcoming_odds()` for SCHEDULED/TIMED matches

### `ucl/betting/futures_odds_engine.py`

- **Winner odds**: Based on UEFA club coefficients + league phase standing
- **Finalist odds**: Winner odds / ~1.8
- **Top 8 odds**: Based on current league phase standing + coefficient
- Update weekly during league phase, daily during knockouts


## Phase 4: Discussions, Bots, Activity

Direct mirrors of World Cup sub-apps with UCL model FKs:

- **`ucl/discussions/`** — Comment(AbstractComment) with match FK. Same views/templates pattern as WC
- **`ucl/bots/`** — BotComment(AbstractBotComment) with match FK. UCL-specific prompt context (club rivalries, historical narratives, two-leg drama). Strategies reuse EPL/WC base classes (same 1X2 market). Add `active_in_ucl` BooleanField to core BotProfile
- **`ucl/activity/`** — ActivityEvent with UCL-specific event types (STAGE_ADVANCE, KNOCKOUT_ELIMINATION, AGGREGATE_RESULT)


## Phase 5: WebSocket Consumers + Live Scores

Consumers mirror WC pattern:
- **LiveUpdatesConsumer** at `ws/live/<scope>/` — Score broadcasts for in-progress matches
- **ActivityConsumer** at `ws/activity/` — Activity feed toasts
- **NotificationConsumer** at `ws/notifications/` — Rewards/badges

Routing registered in `config/asgi.py` under `path("ucl/", URLRouter(...))`.


## Phase 6: Templates + Views

### UCL-specific views (no direct EPL equivalent)
- **LeaguePhaseView** `/ucl/standings/` — 36-team single table with qualification zone highlighting (top 8 green, 9-24 yellow, 25+ red). Closest analog: WC Groups view but single table
- **BracketView** `/ucl/bracket/` — Knockout bracket (playoffs through final). Reuse WC bracket CSS grid pattern but adapt for two-legged ties showing aggregate scores

### Views mirroring EPL/WC
Dashboard, MatchDetail, Leaderboard, OddsBoard, PlaceBet, QuickBet, ParlaySlip, Futures, Activity — same patterns with UCL models.

### URL structure
```
/ucl/                              Dashboard (upcoming matchday, live matches)
/ucl/standings/                    League phase table (36 teams)
/ucl/bracket/                      Knockout bracket
/ucl/match/<slug>/                 Match detail
/ucl/leaderboard/                  Leaderboard
/ucl/odds/                         Odds board
/ucl/odds/place/<match_slug>/      Place bet
/ucl/parlay/...                    Parlay endpoints
/ucl/futures/                      Futures markets
/ucl/match/<slug>/comments/...     Discussion endpoints
/ucl/activity/                     Activity feed
```

### Templates
All prefixed `ucl_*`:
- `ucl_website/base.html` — UCL-themed layout (dark navy/starball aesthetic)
- `ucl_matches/` — dashboard, standings, bracket, match_detail, partials
- `ucl_betting/` — odds_board, bet_form, parlay_slip, futures
- `ucl_discussions/` — comment_list, comment_form
- `ucl_activity/` — activity_toast_oob


## Phase 7: Hub Integration + Polish

- **Hub live games strip** — Add UCL live match query to `_get_live_games()` in `hub/views.py`
- **Hub My Bets** — Import UCL BetSlip so bets appear in cross-league bet history
- **Hub templates** — Add UCL badge color/display in `my_bets.html`, `live_games_strip.html`
- **News integration** — Add "ucl" as valid league for weekly roundups and betting trends
- **Challenges** — "Bet on 3 league phase matches", "Win a knockout bet", "Build a 4-leg UCL parlay"
- **Admin** — Register all UCL models with appropriate list_display/filters


## Phase 8: Tests

- **Factories** — Team, Match, Standing, BetSlip, Parlay, FuturesBet
- **Model tests** — Creation, constraints, slug generation, winner resolution (including aggregate + ET + pens)
- **Betting tests** — Odds engine, bet placement, settlement, payout. Two-leg aggregate scenarios
- **View tests** — Dashboard, standings, bracket, odds board, bet placement
- **Discussion tests** — Comment CRUD, permissions
- Target: match existing league test coverage patterns


## Celery Beat Schedule

```python
# ===== UCL =====
# --- Data ingestion (matches Tue/Wed during league phase, midweek during knockouts) ---
"ucl-fetch-teams-monthly": weekly Monday 4:15 AM
"ucl-fetch-matches-daily": daily 4:45 AM
"ucl-fetch-standings-4h": every 4 hours (0,4,8,12,16,20) at :15
"ucl-fetch-live-scores-2m": every 2 min, 17:00-01:00 Tue/Wed (league phase), Tue/Wed/Thu (knockouts)
# --- Odds ---
"ucl-generate-odds-10m": every 10 minutes
"ucl-update-futures-odds-hourly": hourly at :55
# --- Bots ---
"ucl-run-bot-strategies-hourly": hourly at :12
"ucl-generate-prematch-comments-hourly": hourly at :22
"ucl-generate-postmatch-comments-hourly": hourly at :42
"ucl-generate-featured-parlays-daily": daily 9:30 AM
# --- Activity ---
"ucl-broadcast-activity-event-20s": every 20 seconds
"ucl-cleanup-old-activity-events-daily": daily 6:00 AM
```


## Verification

- [x] `make migrate` — no errors
- [x] `python manage.py seed_ucl --offline` — 36 teams, 184 matches, 36 standings, 6 odds
- [x] `python manage.py seed_ucl_futures` — 3 markets (WINNER, FINALIST, TOP_8), 108 outcomes
- [x] Visit http://vinosports.local/ucl/ — dashboard renders
- [x] Visit /ucl/standings/ — 36-team league phase table displays
- [x] Visit /ucl/bracket/ — knockout bracket renders
- [x] Place a bet on a league phase match — verify balance deducted
- [x] Settle a match — verify bet settled, balance updated
- [x] `make test` — 102 new UCL tests pass, no regressions across full suite
- [x] `make lint` — clean


## Implementation Summary

Implemented in a single feature branch (`feature/add-ucl-league`) across 8 phases:

| Phase | What | Key files |
|-------|------|-----------|
| 1 | Package skeleton + models | `ucl/` with 7 sub-apps, 6 migrations, 10 config file changes |
| 2 | Data client + seed commands | `services.py`, `seed_ucl`, `seed_ucl_futures`, odds engines, static JSON |
| 3 | Betting models + odds | Completed in phases 1+2 |
| 4 | Discussions, bots, activity | Strategies, comment service (Claude API), discussion CRUD, activity queue |
| 5 | WebSocket consumers | 3 consumers (live scores, activity, notifications), routing |
| 6 | Templates + views | 35 templates, all views/URLs, template tags, static CSS |
| 7 | Hub integration | Live games strip, My Bets, news filter |
| 8 | Tests | 102 tests (models, settlement, betting views, discussions, page smoke tests) |

**Total:** ~90 new files, ~12,000 lines of code + templates + static data.
