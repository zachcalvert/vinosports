# 0002: Data Population Plan

## Overview

The EPL project needs data from [football-data.org](https://www.football-data.org/) to function. This plan covers the initial data load and ongoing sync.

## Prerequisites

- A football-data.org API key (free tier provides 10 requests/minute, sufficient for our needs)
- The API key set as `FOOTBALL_DATA_API_KEY` in the environment

### Setting the API Key

Add to `docker-compose.yml` under the `x-epl-env` anchor, or create an `.env` file:

```bash
# .env
FOOTBALL_DATA_API_KEY=your-key-here
```

## Initial Data Load

Run these tasks in order via the Django shell or management commands. Each task is idempotent (safe to re-run).

### Step 1: Fetch Teams

```bash
docker compose run --rm epl-web python manage.py shell -c "
from matches.tasks import fetch_teams
fetch_teams()
"
```

This calls `sync_teams("2025")` which hits the football-data.org `/competitions/PL/teams` endpoint and creates/updates all 20 Premier League teams with: name, short_name, tla (three-letter abbreviation), crest_url, and venue.

### Step 2: Fetch Fixtures

```bash
docker compose run --rm epl-web python manage.py shell -c "
from matches.tasks import fetch_fixtures
fetch_fixtures()
"
```

This calls `sync_matches("2025")` which fetches all 380 matches for the current season from `/competitions/PL/matches`. Creates Match records with: external_id, home/away teams, matchday, kickoff time, status, and scores (if played).

### Step 3: Fetch Standings

```bash
docker compose run --rm epl-web python manage.py shell -c "
from matches.tasks import fetch_standings
fetch_standings()
"
```

This calls `sync_standings("2025")` which fetches the current table from `/competitions/PL/standings`. Creates/updates Standing records with: position, played, won, drawn, lost, GF, GA, GD, points.

### Step 4: Generate Odds

```bash
docker compose run --rm epl-web python manage.py shell -c "
from betting.tasks import generate_odds
generate_odds()
"
```

This runs the algorithmic odds engine which generates house odds for upcoming matches based on standings data (team strength, home advantage, form). Creates Odds records for each upcoming match.

### Step 5: Prefetch Hype Data (Optional)

```bash
docker compose run --rm epl-web python manage.py shell -c "
from matches.tasks import prefetch_upcoming_hype_data
prefetch_upcoming_hype_data()
"
```

Fetches head-to-head history and recent form for matches in the next 48 hours. This data powers the match detail page's "hype" section and is used in bot comment prompts.

## Ongoing Sync

Once the initial load is complete, the Celery beat scheduler handles everything automatically:

| Task | Schedule | What It Does |
|------|----------|--------------|
| `fetch_teams` | 1st of each month, 3am | Picks up mid-season team changes |
| `fetch_fixtures` | Daily, 3am | Catches rescheduled matches |
| `fetch_standings` | 3am midweek; every 3h on match days | Keeps table current |
| `fetch_live_scores` | Every 15min, Fri-Mon 11am-11pm | Live score updates during matches |
| `generate_odds` | Every 10 minutes | Refreshes algorithmic odds |
| `prefetch_upcoming_hype_data` | Every 6 hours | Pre-caches H2H and form data |
| `settle_match_bets` | Triggered on match completion | Settles pending bets and parlays |

## Verification

After running the initial load, verify in the Django admin (`localhost:8000/admin/`):

- **Teams:** 20 teams with crests
- **Matches:** ~380 matches across 38 matchdays
- **Standings:** 20 rows with current points
- **Odds:** Odds records for upcoming matches

The dashboard at `localhost:8000/` should now show upcoming fixtures with odds.

## API Rate Limits

football-data.org free tier: 10 requests/minute. The initial load makes roughly:
- fetch_teams: 1 request
- fetch_fixtures: 1 request
- fetch_standings: 1 request
- generate_odds: 0 requests (computed locally)
- prefetch_hype_data: 2 requests per match (H2H + form), throttled with 20s sleep

For the initial load, wait ~10 seconds between steps to stay within limits.
