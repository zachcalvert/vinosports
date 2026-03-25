# 0018 — NBA Box Scores

## Overview

Add box score data to the NBA game detail page for in-progress and completed games. Player stats (points, rebounds, assists, shooting splits, etc.) will be fetched from the BallDontLie `/v1/stats` endpoint (available at All-Star tier) and displayed in a tabbed, team-grouped table below the scoreboard.

---

## Data Source

**Endpoint:** `GET /v1/stats?game_ids[]=<external_id>`

Returns one row per player per game with fields: `min`, `pts`, `fgm`, `fga`, `fg_pct`, `fg3m`, `fg3a`, `fg3_pct`, `ftm`, `fta`, `ft_pct`, `oreb`, `dreb`, `reb`, `ast`, `stl`, `blk`, `turnover`, `pf`, `plus_minus`. Each row includes nested `player`, `team`, and `game` objects.

This is the raw stat-line endpoint — not the GOAT-tier `/v1/box_scores` endpoint. We group by team ourselves.

---

## Phase 1: Model + API Client

### 1a. PlayerBoxScore model

New model in `apps/nba/games/models.py`:

```python
class PlayerBoxScore(BaseModel):
    game = FK(Game, related_name="box_scores")
    team = FK(Team)

    # Player identity (denormalized from BDL — we don't maintain a Player table)
    player_external_id = IntegerField()
    player_name = CharField(max_length=100)
    player_position = CharField(max_length=10, blank=True)

    # Stats
    minutes = CharField(max_length=10, blank=True)  # BDL returns "MM:SS" string
    points = SmallIntegerField(default=0)
    fgm = SmallIntegerField(default=0)
    fga = SmallIntegerField(default=0)
    fg3m = SmallIntegerField(default=0)
    fg3a = SmallIntegerField(default=0)
    ftm = SmallIntegerField(default=0)
    fta = SmallIntegerField(default=0)
    oreb = SmallIntegerField(default=0)
    dreb = SmallIntegerField(default=0)
    reb = SmallIntegerField(default=0)
    ast = SmallIntegerField(default=0)
    stl = SmallIntegerField(default=0)
    blk = SmallIntegerField(default=0)
    turnovers = SmallIntegerField(default=0)
    pf = SmallIntegerField(default=0)
    plus_minus = SmallIntegerField(default=0)

    # Starter flag (derived from BDL, if available; else first 5 by minutes)
    starter = BooleanField(default=False)

    class Meta:
        unique_together = ("game", "player_external_id")
        ordering = ["-starter", "-points"]
```

**Why denormalize player info?** We don't need a full Player table — box scores are display-only. Storing `player_name` and `player_position` directly keeps things simple and avoids an extra table + sync pipeline.

### 1b. NBADataClient.get_game_stats()

New method on the existing `NBADataClient`:

```python
def get_game_stats(self, game_external_id: int) -> list[dict]:
    raw = self._get_all("/stats", params={"game_ids[]": game_external_id})
    return [self._normalize_player_stat(s) for s in raw]
```

Plus a `_normalize_player_stat()` method that extracts and flattens the nested player/team data into a dict matching `PlayerBoxScore` fields.

### 1c. sync_box_score() service function

New function in `services.py`:

```python
def sync_box_score(game: Game, client: NBADataClient | None = None) -> int:
    """Fetch and upsert player stats for a single game. Returns count."""
```

- Calls `client.get_game_stats(game.external_id)`
- Uses `update_or_create` keyed on `(game, player_external_id)`
- Resolves `team` FK via `Team.objects.get(external_id=...)`
- Infers `starter` flag: BDL doesn't reliably provide this, so mark the top 5 players per team by minutes as starters

---

## Phase 2: Fetching Strategy

Box scores need to be fetched at two different cadences:

### Live games (in-progress / halftime)

- **Trigger:** Piggyback on the existing `fetch_live_scores` Celery task
- **When:** After `sync_live_scores()` returns changed games, call `sync_box_score()` for each game that is still live
- **Frequency:** Same as live scores (~20-30s via Celery beat)
- **Optimization:** Only fetch if the game's score actually changed (already tracked by `_broadcast_score_updates`)

### Final games

- **Trigger:** When a game transitions to `FINAL` status during `sync_live_scores()`
- **When:** One final fetch to capture the complete box score
- **After that:** No more fetches needed — stats are frozen

### On-demand (game detail page load)

- **Trigger:** User opens a game detail page for a live or final game that has no box score data yet
- **When:** Inline in the view (or kicked off as a quick background task)
- **Guard:** Skip if `PlayerBoxScore.objects.filter(game=game).exists()` and game is FINAL

---

## Phase 3: Template + Display

### 3a. Box score partial

New template: `games/partials/box_score.html`

**Layout:**
- Two tabs: Away team | Home team (HTMX tab switching, no page reload)
- Each tab contains a stat table:

| Player | MIN | PTS | REB | AST | STL | BLK | TO | FG | 3PT | FT | +/- |
|--------|-----|-----|-----|-----|-----|-----|----|----|-----|----|-----|
| **Starters** |
| J. Tatum | 36:21 | 28 | 7 | 5 | 2 | 1 | 3 | 10-18 | 4-8 | 4-5 | +12 |
| ... |
| **Bench** |
| P. Pritchard | 22:14 | 12 | 2 | 4 | 1 | 0 | 1 | 4-9 | 3-6 | 1-1 | +8 |
| ... |
| **Totals** | | 112 | 44 | 28 | 8 | 5 | 12 | 42-88 | 14-32 | 14-18 | |

- Shooting splits displayed as `made-attempted` (e.g., `10-18`) to save horizontal space
- Starters grouped above bench, separated by a subtle divider
- Team totals row at the bottom
- Responsive: on mobile, horizontally scrollable table with sticky player name column

### 3b. Integration into game detail page

- Insert box score section between the scoreboard and the hype/recap card
- Show for `IN_PROGRESS`, `HALFTIME`, and `FINAL` games only
- For `SCHEDULED` games, show nothing (no box score data exists yet)

### 3c. OOB swap for live updates

- Add a `box_score_oob.html` partial (like the existing `scoreboard_oob.html`)
- The WebSocket consumer renders and sends the box score partial alongside the scoreboard update
- HTMX swaps `#box-score` via OOB when new data arrives

---

## Phase 4: Tests

- **Model tests:** `PlayerBoxScore` creation, unique constraint, ordering
- **Service tests:** `sync_box_score()` with mocked BDL responses, starter inference logic
- **View tests:** Box score context present for live/final games, absent for scheduled
- **Consumer tests:** OOB swap includes box score partial when data exists

---

## Migration Plan

1. Generate migration for `PlayerBoxScore` model
2. No data migration needed — box scores populate on first fetch
3. Deploy model + migration first, then enable fetching

## File Changes Summary

| File | Change |
|------|--------|
| `apps/nba/games/models.py` | Add `PlayerBoxScore` model |
| `apps/nba/games/services.py` | Add `get_game_stats()`, `_normalize_player_stat()`, `sync_box_score()` |
| `apps/nba/games/tasks.py` | Hook `sync_box_score` into `fetch_live_scores` |
| `apps/nba/games/views.py` | Add box score context to `GameDetailView` |
| `apps/nba/games/consumers.py` | Add box score OOB rendering to `game_score_update()` |
| `apps/nba/games/templates/games/partials/box_score.html` | New — tabbed box score display |
| `apps/nba/games/templates/games/partials/box_score_oob.html` | New — OOB swap wrapper |
| `apps/nba/games/templates/games/game_detail.html` | Include box score section |
| `apps/nba/games/admin.py` | Register `PlayerBoxScore` |
| `apps/nba/tests/test_box_score.py` | New — model, service, view, consumer tests |

## API Rate Limit Considerations

- All-Star tier: 600 requests/minute
- Each box score fetch = 1 request per game (stats endpoint paginated but a single game rarely exceeds 100 rows)
- With ~15 concurrent live games at peak, fetching every 30s = ~30 req/min for box scores — well within limits
- Final games fetched once and cached in DB — no repeated calls
