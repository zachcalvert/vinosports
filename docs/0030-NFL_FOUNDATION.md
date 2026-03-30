# 0030: NFL Foundation — Models, Data Client, Seeding

**Date:** 2026-03-30
**Status:** Complete
**Parent:** [0029-NFL_LEAGUE.md](0029-NFL_LEAGUE.md)
**API Tier:** Free ($0, 5 req/min)

## Goal

Stand up the `nfl/` package with core models, a BDL data client, sync helpers, and seed commands. At the end of this phase we should be able to run `make seed` and have 32 NFL teams, a full season schedule with scores, and a player roster in the database — without paying for an API tier upgrade.

## Package Structure

```
nfl/
  __init__.py
  urls.py                          # Will combine all sub-app URL includes (Phase 4)
  games/
    __init__.py
    apps.py                        # label: nfl_games
    models.py                      # Team, Game, Standing, GameStats, Player
    services.py                    # NFLDataClient + sync helpers
    admin.py
    tasks.py                       # Stubbed (populated in Phase 5)
    static_data/
      teams.json                   # Offline fixture
    management/
      commands/
        seed_nfl.py
  betting/
    __init__.py
    apps.py                        # label: nfl_betting
    models.py                      # Stubbed (populated in Phase 2)
  bots/
    __init__.py
    apps.py                        # label: nfl_bots
    models.py                      # Stubbed (populated in Phase 3)
  discussions/
    __init__.py
    apps.py                        # label: nfl_discussions
    models.py                      # Stubbed (populated in Phase 3)
  activity/
    __init__.py
    apps.py                        # label: nfl_activity
    models.py                      # Stubbed (populated in Phase 4)
  challenges/
    __init__.py
    apps.py                        # label: nfl_challenges
    models.py                      # Stubbed (populated in Phase 7)
  website/
    __init__.py
    apps.py                        # label: nfl_website
  tests/
    __init__.py
    factories.py
    test_games_models.py
    test_games_services.py
```

"Stubbed" apps get an `apps.py` with the correct label and an empty `models.py` so they can be added to `INSTALLED_APPS` now. This avoids a second round of config changes later.

## Models

### Team

Follow the NBA `Team` pattern. NFL-specific additions: none needed — the NBA model already has `conference` and `division` fields.

```python
class Conference(models.TextChoices):
    AFC = "AFC", "AFC"
    NFC = "NFC", "NFC"

class Division(models.TextChoices):
    AFC_EAST = "AFC_EAST", "AFC East"
    AFC_NORTH = "AFC_NORTH", "AFC North"
    AFC_SOUTH = "AFC_SOUTH", "AFC South"
    AFC_WEST = "AFC_WEST", "AFC West"
    NFC_EAST = "NFC_EAST", "NFC East"
    NFC_NORTH = "NFC_NORTH", "NFC North"
    NFC_SOUTH = "NFC_SOUTH", "NFC South"
    NFC_WEST = "NFC_WEST", "NFC West"

class Team(BaseModel):
    external_id       IntegerField(unique=True)
    name              CharField(100)          # "Kansas City Chiefs"
    short_name        CharField(100)          # "Chiefs"
    abbreviation      CharField(5)            # "KC"
    logo_url          URLField(blank=True)
    conference        CharField(choices=Conference)
    division          CharField(choices=Division)
```

**Why `Division` as a TextChoices enum instead of a free CharField?** NBA uses a free `division` CharField because NBA divisions are less structurally important. NFL divisions define the schedule (6 divisional games/year), standings hierarchy, and playoff seeding. An enum prevents typos and makes filtering reliable.

### Game

NFL games differ from NBA in two key ways: **week numbers** and **quarter-by-quarter scoring**.

```python
class GameStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    HALFTIME = "HALFTIME", "Halftime"
    FINAL = "FINAL", "Final"
    FINAL_OT = "FINAL_OT", "Final (OT)"
    POSTPONED = "POSTPONED", "Postponed"
    CANCELLED = "CANCELLED", "Cancelled"

class Game(BaseModel):
    external_id       IntegerField(unique=True)
    home_team         FK(Team, related_name="home_games")
    away_team         FK(Team, related_name="away_games")
    home_score        IntegerField(null=True)
    away_score        IntegerField(null=True)
    status            CharField(choices=GameStatus, default=SCHEDULED)
    game_date         DateField()
    kickoff           DateTimeField(null=True)       # EPL calls this "kickoff" too
    season            IntegerField()                  # BDL start-year convention (2026 season = 2026)
    week              IntegerField(null=True)         # 1-18 regular, 19+ postseason
    postseason        BooleanField(default=False)
    venue             CharField(200, blank=True)

    # Quarter scores — NFL-specific
    home_q1           SmallIntegerField(null=True)
    home_q2           SmallIntegerField(null=True)
    home_q3           SmallIntegerField(null=True)
    home_q4           SmallIntegerField(null=True)
    home_ot           SmallIntegerField(null=True)
    away_q1           SmallIntegerField(null=True)
    away_q2           SmallIntegerField(null=True)
    away_q3           SmallIntegerField(null=True)
    away_q4           SmallIntegerField(null=True)
    away_ot           SmallIntegerField(null=True)
```

**Why store quarter scores as flat fields instead of JSONField?** We'll query and display these constantly (box score headers, game cards). Flat fields are easier to aggregate, filter, and template-render. 10 nullable SmallIntegerFields is cheap.

**Week number**: The BDL games endpoint supports filtering by `week` and returns it in the response. This is the primary navigation axis for NFL (not dates like NBA).

**`FINAL_OT` status**: NFL overtime is significant — it affects betting (some markets exclude OT). Worth tracking as a distinct status.

### Standing

Standings are All-Star tier, so we **cannot** sync them from the API on free tier. Two options:

**Option A: Compute locally from game results** (like the NBA fallback does today).
- Pros: No API cost. We control the logic.
- Cons: Need to handle tiebreakers (NFL tiebreakers are notoriously complex — head-to-head, division record, common opponents, strength of victory, etc.).

**Option B: Defer standings entirely to Phase 2** when we upgrade to All-Star.
- Pros: Simpler Phase 1. Correct tiebreakers from day one.
- Cons: Can't show standings in Phase 4 (website) without the data.

**Recommendation: Option A with simplified tiebreakers.** Compute W-L-T, win%, division record, and conference record from game results. Use simple win% ordering. Flag in a comment that full NFL tiebreakers are deferred to All-Star sync. This gives us enough for a usable standings page while keeping Phase 1 free.

```python
class Standing(BaseModel):
    team              FK(Team, related_name="standings")
    season            IntegerField()
    conference        CharField(choices=Conference)
    division          CharField(choices=Division)
    wins              IntegerField(default=0)
    losses            IntegerField(default=0)
    ties              IntegerField(default=0)         # NFL still has ties
    win_pct           FloatField(default=0.0)
    division_wins     IntegerField(default=0)
    division_losses   IntegerField(default=0)
    conference_wins   IntegerField(default=0)
    conference_losses IntegerField(default=0)
    points_for        IntegerField(default=0)
    points_against    IntegerField(default=0)
    streak            CharField(10, blank=True)
    division_rank     IntegerField(null=True)

    unique_together = [("team", "season")]
    ordering = ["division", "division_rank"]
```

**Why `ties`?** NFL games can end in ties (rare but real — ~1/season). NBA and EPL don't have this.

### Player

Available on free tier. Include now so we have rosters seeded, even though player stats come in Phase 2.

```python
class Player(BaseModel):
    external_id       IntegerField(unique=True)
    first_name        CharField(100)
    last_name         CharField(100)
    position          CharField(10, blank=True)       # QB, RB, WR, TE, K, etc.
    height            CharField(10, blank=True)       # "6-4"
    weight            PositiveSmallIntegerField(null=True)
    jersey_number     CharField(20, blank=True)
    college           CharField(100, blank=True)
    team              FK(Team, null=True, related_name="players")
    is_active         BooleanField(default=False)

    # NFL-specific
    experience        PositiveSmallIntegerField(null=True)  # years in league
    depth_chart_order IntegerField(null=True)               # if available from API
```

### GameStats (stub)

Same pattern as NBA — a JSONField cache for hype data (H2H, form). Stubbed now, populated when we build game detail views in Phase 4.

```python
class GameStats(BaseModel):
    game              OneToOneField(Game, related_name="stats")
    h2h               JSONField(default=dict)
    form              JSONField(default=dict)
    injuries          JSONField(default=dict)
    fetched_at        DateTimeField(null=True)
```

## Data Client — `NFLDataClient`

Follow the `NBADataClient` pattern exactly: thin httpx wrapper, `_get()` with pagination, public methods returning normalized dicts.

```
Base URL: https://api.balldontlie.io/nfl/v1
Auth: Authorization header with BDL_API_KEY
Timeout: 15s
Pagination: cursor-based, 100 per page
```

### Methods (free tier)

| Method | Endpoint | Returns |
|--------|----------|---------|
| `get_teams()` | `GET /teams` | List of team dicts |
| `get_games(season, week=None, game_date=None)` | `GET /games` | Paginated game dicts |
| `get_game(game_id)` | `GET /games/<ID>` | Single game dict |
| `get_players(search=None, team_id=None)` | `GET /players` | Paginated player dicts |
| `get_player(player_id)` | `GET /players/<ID>` | Single player dict |

### Status Normalization

Need to discover BDL's exact NFL status strings. Expected mapping (to be verified against live API responses):

```python
"Final"       → GameStatus.FINAL
"Final/OT"    → GameStatus.FINAL_OT
"Halftime"    → GameStatus.HALFTIME
"1st Quarter"  → GameStatus.IN_PROGRESS
"2nd Quarter"  → GameStatus.IN_PROGRESS
"3rd Quarter"  → GameStatus.IN_PROGRESS
"4th Quarter"  → GameStatus.IN_PROGRESS
"Overtime"    → GameStatus.IN_PROGRESS
# ISO timestamp or "Scheduled" → GameStatus.SCHEDULED
```

### Season Convention

BDL uses start year for NBA (2025-26 season = `2025`). **Need to verify for NFL.** NFL seasons don't span calendar years the same way — the 2026 NFL season starts Sep 2026 and ends Feb 2027. Likely `2026` = the 2026 season, but confirm.

```python
def _current_season() -> int:
    """NFL: season = the year the season starts in."""
    today = timezone.now().date()
    # NFL runs Sep–Feb. Mar–Aug = previous season (or offseason).
    return today.year if today.month >= 9 else today.year - 1
```

## Sync Helpers

Follow the NBA pattern — standalone functions that call the client and upsert models:

- `sync_teams()` → Upsert 32 teams, return count
- `sync_games(season, week=None)` → Upsert games for season/week, return count
- `sync_players(page_delay=0)` → Paginated upsert of all players, return count
- `compute_standings(season)` → Query FINAL games, compute W-L-T, upsert standings, return count

## Management Command — `seed_nfl`

```
python manage.py seed_nfl              # live API
python manage.py seed_nfl --offline    # static fixtures
python manage.py seed_nfl --season 2025
python manage.py seed_nfl --teams-only
python manage.py seed_nfl --skip-players
```

Steps:
1. Sync teams (or load from `static_data/teams.json` if offline)
2. Sync games for season (skip if `--teams-only`)
3. Sync players (skip if `--teams-only` or `--skip-players`)
4. Compute standings from game results (skip if `--teams-only`)
5. Set team logo URLs from hardcoded map

The `seed` Makefile target should be updated to call `seed_nfl` alongside `seed_epl` and `seed_nba`.

## Config Changes

### `config/settings.py`

- Add all NFL apps to `INSTALLED_APPS`:
  ```python
  "nfl.games",
  "nfl.betting",
  "nfl.bots",
  "nfl.discussions",
  "nfl.activity",
  "nfl.challenges",
  "nfl.website",
  ```
- Add `"nfl"` to Celery autodiscover list (even though tasks are stubbed)
- No new context processors yet (Phase 4)
- No new URL includes yet (Phase 4)

### `config/urls.py`

- Add `path("nfl/", include("nfl.urls"))` — the `nfl/urls.py` can be empty/minimal for now

### `config/asgi.py`

- No changes yet (Phase 6)

### `Makefile`

- Update `seed` target to include `seed_nfl`

## Admin

Register Team, Game, Standing, Player, GameStats in `nfl/games/admin.py`. Follow NBA patterns:
- Team: list display = name, abbreviation, conference, division
- Game: list display = matchup, week, game_date, status, score; filters = season, week, status, postseason
- Standing: list display = team, season, record, division, rank
- Player: list display = name, position, team, is_active; filters = position, team, is_active

## Tests

Target: basic model and service coverage matching what NBA/EPL had at their foundation phase.

- **Factories** (`tests/factories.py`): TeamFactory, GameFactory, StandingFactory, PlayerFactory
- **Model tests**: Team str, Game str/is_live/is_final/winner, Standing ordering
- **Service tests**: NFLDataClient response normalization, status mapping, sync_teams/sync_games upsert logic
- **Command tests**: seed_nfl --offline mode

Mock all HTTP calls with `respx` (same as NBA/EPL test suites).

## Task Breakdown

1. **Scaffold `nfl/` package** — all sub-apps with `apps.py` and empty `models.py`
2. **Models + migrations** — Team, Game, Standing, Player, GameStats in `nfl/games/models.py`
3. **Config integration** — INSTALLED_APPS, urls.py, Makefile
4. **NFLDataClient** — httpx wrapper with free-tier methods
5. **Sync helpers** — sync_teams, sync_games, sync_players, compute_standings
6. **Admin** — registrations for all nfl_games models
7. **seed_nfl command** — live + offline modes
8. **Static fixtures** — `teams.json` for offline seeding
9. **Tests** — factories, model tests, service tests, command tests

## Open Questions for Implementation

1. **BDL NFL response shapes**: We need to hit the API once for teams + games to see exact field names and status strings. Should we do a quick exploratory script first?
2. **Logo URLs**: BDL probably doesn't return logos. We'll need to source a logo map for 32 teams (same pattern as NBA's `TEAM_LOGOS` dict).
3. **Player sync timing**: With ~1,800 active NFL players and 5 req/min on free tier, a full player sync could take a while with pagination. Should we defer full player sync to All-Star tier and only seed a `teams.json` fixture for offline mode?
