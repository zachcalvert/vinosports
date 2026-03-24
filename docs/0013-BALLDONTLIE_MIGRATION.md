# 0013: BallDontLie Migration

**Date:** 2026-03-24

## Context

Both league apps were using free-tier sports data APIs with significant limitations:

- **NBA** used sportsdata.io's free trial, which returns **scrambled data** (scores randomly fuzzed 5-20%, non-deterministic between calls). Every finished game in the DB had partial/halftime-like scores (e.g., 47-32 for a completed game). Investigation revealed the `/Games/{season}` endpoint returned different scrambled values than `/GamesByDate/{date}`, and scores changed between API calls. Additionally, a race condition in `get_live_scores()` meant the `AreAnyGamesInProgress` guard would return `False` once the last game ended, causing us to miss final scores entirely.
- **EPL** used football-data.org's free tier, which works but is heavily rate-limited (10 req/min). H2H data fetches required 20-second sleeps between calls to avoid 429s.

Both were replaced with **BallDontLie** (BDL) at the All-Star tier ($9.99/mo per sport). This gives real, unscrambled data at 60 req/min for both NBA and EPL, with NFL available for post-launch expansion at the same price point.

## What Changed

### Settings & Environment

- `BDL_API_KEY` replaces both `SPORTSDATA_API_KEY` (NBA) and `FOOTBALL_DATA_API_KEY` (EPL)
- Single API key works across all BDL sport APIs
- Updated `.env.example`, `CLAUDE.md`, `README.md`

### NBA (`apps/nba/games/services.py`)

**NBADataClient** rewritten for BDL `/nba/v1/` endpoints:

| Aspect | Before (sportsdata.io) | After (BDL) |
|--------|------------------------|-------------|
| Base URL | `api.sportsdata.io/v3/nba/scores/JSON` | `api.balldontlie.io/nba/v1` |
| Auth | `Ocp-Apim-Subscription-Key` header | `Authorization` header (raw key) |
| Responses | Bare arrays | Wrapped in `{"data": [...], "meta": {...}}` |
| Pagination | None | Cursor-based, 100/page |
| Score fields | `HomeTeamScore` / `AwayTeamScore` | `home_team_score` / `visitor_team_score` |
| Status values | `"Scheduled"`, `"InProgress"`, `"Final"` | ISO timestamp (scheduled), quarter strings (live), `"Final"` |
| Season convention | End year (2026 for 2025-26) | Start year (2025 for 2025-26) |
| Live score guard | `AreAnyGamesInProgress` API call | Local DB check for IN_PROGRESS/HALFTIME games |

**Standings**: BDL's `/standings` endpoint returns 401 despite All-Star tier (may be GOAT-only or a BDL bug). Added `_compute_standings_from_games()` fallback that computes W-L records, win%, home/away splits, and conference rank from FINAL game results.

**Season convention change**: `_current_season()` in `tasks.py` and `seed_nba.py` updated — Oct-Dec returns current year (was year+1), Jan-Sep returns year-1 (was year).

### EPL (`apps/epl/matches/services.py`)

**FootballDataClient** rewritten for BDL `/epl/v2/` endpoints (class name kept for import compatibility):

| Aspect | Before (football-data.org) | After (BDL) |
|--------|----------------------------|-------------|
| Base URL | `api.football-data.org/v4/` | `api.balldontlie.io/epl/v2` |
| Auth | `X-Auth-Token` header | `Authorization` header |
| Score fields | `score.fullTime.home/away` | `home_score` / `away_score` |
| Team refs in matches | Nested objects (`homeTeam.id`) | Flat IDs (`home_team_id`) |
| Status values | `"SCHEDULED"`, `"IN_PLAY"`, `"FINISHED"` | `"STATUS_SCHEDULED"`, `"STATUS_FIRST_HALF"`, `"STATUS_FULL_TIME"` |
| H2H data | API endpoint (`/matches/{id}/head2head`) | Computed locally from DB |
| Matchday | Returned by API | Derived from date grouping (10 matches per round) |
| Rate limiting | 10 req/min, needed `time.sleep(20)` | 60 req/min, no sleeps needed |

**H2H now local**: `get_head_to_head(match)` queries the last 5 finished matches between the two teams from the local DB. This is faster and removes the football-data.org rate-limit bottleneck from `prefetch_upcoming_hype_data`.

**Matchday derivation**: BDL doesn't return matchday. `_assign_matchdays()` sorts all season matches by kickoff and assigns matchday 1, 2, 3... for each batch of 10 (20 teams = 10 matches per round). This is approximate for rescheduled matches but correct for the standard schedule.

### EPL Tasks (`apps/epl/matches/tasks.py`)

- `fetch_live_scores` now fetches by `game_date=date.today()` instead of `status="LIVE"` (BDL doesn't support status filtering)
- Removed `time.sleep(20)` from `prefetch_upcoming_hype_data` (H2H is local, no rate limiting concern)

### New Management Command

`apps/nba/games/management/commands/backfill_scores.py` — Finds FINAL games with suspiciously low combined scores, fetches correct scores per-date from the API, and updates them. Originally written to fix sportsdata.io's scrambled data; still useful as a general score-correction tool.

## Data Re-seed

BDL external IDs differ from both sportsdata.io and football-data.org. All existing game/match data was cleared and re-seeded:

```bash
# NBA: 30 teams, 1231 games (1076 final with real scores), 30 standings, 155 upcoming odds
docker compose exec nba-web python manage.py seed_nba

# EPL: 20 teams, 380 matches, 20 standings, 70 upcoming odds
docker compose exec epl-web python manage.py seed_epl
```

## Known Limitations

- **NBA standings API**: Returns 401 at All-Star tier. Standings are computed locally from game results, which works well but doesn't include games_behind or streak data.
- **Team logos**: BDL doesn't provide logo/crest URLs. Templates already guard with `{% if logo_url %}` so this degrades gracefully, but logos are missing from the UI.
- **EPL matchday**: Derived from date ordering, not from the league's official matchday assignments. Rescheduled matches may land in the wrong matchday bucket.
- **H2H limited to current season**: After re-seed, only 2025-26 matches exist in the DB. H2H data will be sparse until more historical data is imported.

## Future Improvements

- Import historical seasons for richer H2H data
- Add a static logo URL mapping (NBA: `cdn.nba.com`, EPL: public crest CDNs)
- Add NFL when ready for post-launch expansion (same BDL API, $9.99/mo)
- Revisit BDL standings endpoint if/when it becomes available at All-Star tier
