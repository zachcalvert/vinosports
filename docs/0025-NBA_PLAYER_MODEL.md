# 0025 — NBA Player Model & Profile Pages

**Date:** 2026-03-26

## Overview

The `PlayerBoxScore` model currently stores player identity fields (`player_external_id`, `player_name`, `player_position`) as denormalized columns — a deliberate decision made in doc 0018 to keep the box score feature simple. This works fine for displaying a stat line inside a game page, but it makes it impossible to build anything player-centric: a browsable roster, a profile page, career stat aggregation, or links from box scores to a dedicated player view.

This doc proposes adding a `Player` model to `nba/games/`, wiring it into the existing BallDontLie sync pipeline, and building a minimal player profile page at `/nba/games/players/<id_hash>/`. The existing `PlayerBoxScore` model gains an optional FK to `Player` so that box score rows can link to the new profile without breaking anything.

---

## Data Source

**Endpoint:** `GET /nba/v1/players`

Available on the BallDontLie All-Star tier (which we already subscribe to). Supports cursor-based pagination (same pattern as `/teams` and `/games`). Returns all current and historical NBA players.

**Sample response object:**

```json
{
  "id": 237,
  "first_name": "LeBron",
  "last_name": "James",
  "position": "F",
  "height": "6-9",
  "weight": "250",
  "jersey_number": "23",
  "college": "None",
  "country": "USA",
  "draft_year": 2003,
  "draft_round": 1,
  "draft_number": 1,
  "team": {
    "id": 14,
    "abbreviation": "LAL",
    "city": "Los Angeles",
    "conference": "West",
    "division": "Pacific",
    "full_name": "Los Angeles Lakers",
    "name": "Lakers"
  }
}
```

Fields of interest:
- `id` → `external_id` (unique, used as lookup key)
- `first_name`, `last_name`
- `position` — single character or short string ("G", "F", "C", "G-F", "F-C")
- `height` — "feet-inches" string (e.g. `"6-9"`)
- `weight` — string of pounds (e.g. `"250"`)
- `jersey_number` — string (some players have no number)
- `college` — string or `"None"`
- `country` — ISO country name
- `draft_year`, `draft_round`, `draft_number` — nullable integers
- `team` — nested team object (current team; `null` for free agents)

---

## Phase 1: Player Model

### 1a. New `Player` model in `nba/games/models.py`

```python
class Player(BaseModel):
    """NBA player — synced from BallDontLie /players endpoint."""

    external_id = models.IntegerField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    position = models.CharField(max_length=10, blank=True)
    height = models.CharField(max_length=10, blank=True)   # "6-9"
    weight = models.PositiveSmallIntegerField(null=True, blank=True)  # pounds
    jersey_number = models.CharField(max_length=5, blank=True)
    college = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    draft_year = models.PositiveSmallIntegerField(null=True, blank=True)
    draft_round = models.PositiveSmallIntegerField(null=True, blank=True)
    draft_number = models.PositiveSmallIntegerField(null=True, blank=True)
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="players",
    )
    headshot_url = models.URLField(blank=True)  # NBA CDN

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_absolute_url(self):
        return reverse("nba_games:player_detail", kwargs={"id_hash": self.id_hash})
```

**Headshot URL convention:** The NBA CDN serves player headshots at a predictable URL:
`https://cdn.nba.com/headshots/nba/latest/1040x760/<external_id>.png`

The `headshot_url` field is populated during sync using this template. BDL does not provide headshot URLs directly.

### 1b. FK on `PlayerBoxScore`

Add an optional FK to `Player` on the existing `PlayerBoxScore` model:

```python
class PlayerBoxScore(BaseModel):
    ...
    player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="box_scores",
    )
    ...
```

This is nullable so that box score rows for players who haven't been synced yet (or no longer appear in the BDL players list) still save without error. The `sync_box_score()` function is updated to resolve and populate this FK when a matching `Player` record exists.

---

## Phase 2: BallDontLie Integration

### 2a. `_normalize_player()` in `NBADataClient`

New private normalizer:

```python
def _normalize_player(self, p: dict) -> dict:
    team = p.get("team")
    weight_raw = p.get("weight") or ""
    try:
        weight = int(weight_raw) if weight_raw else None
    except ValueError:
        weight = None
    external_id = p["id"]
    return {
        "external_id": external_id,
        "first_name": p.get("first_name", ""),
        "last_name": p.get("last_name", ""),
        "position": p.get("position") or "",
        "height": p.get("height") or "",
        "weight": weight,
        "jersey_number": p.get("jersey_number") or "",
        "college": p.get("college") or "",
        "country": p.get("country") or "",
        "draft_year": p.get("draft_year"),
        "draft_round": p.get("draft_round"),
        "draft_number": p.get("draft_number"),
        "team_external_id": team["id"] if team else None,
        "headshot_url": (
            f"https://cdn.nba.com/headshots/nba/latest/1040x760/{external_id}.png"
        ),
    }
```

### 2b. `get_players()` in `NBADataClient`

```python
def get_players(self) -> list[dict]:
    """Return all players (active + historical), normalized."""
    raw = self._get_all("/players", params={"per_page": 100})
    return [self._normalize_player(p) for p in raw]
```

The `/players` endpoint on the All-Star tier returns all players — both currently rostered and historically retired. This gives us a complete lookup table for resolving box score rows to profiles.

### 2c. `sync_players()` service function

New function in `nba/games/services.py`:

```python
def sync_players(client: NBADataClient | None = None) -> int:
    """Upsert all players from BDL. Returns count of players synced."""
    with client or NBADataClient() as c:
        players = c.get_players()

    # Build team lookup once
    team_ext_ids = {p["team_external_id"] for p in players if p["team_external_id"]}
    teams_by_ext = {
        t.external_id: t
        for t in Team.objects.filter(external_id__in=team_ext_ids)
    }

    count = 0
    for p in players:
        team_ext_id = p.pop("team_external_id")
        p["team"] = teams_by_ext.get(team_ext_id)  # None for free agents / unknowns
        Player.objects.update_or_create(
            external_id=p.pop("external_id"),
            defaults=p,
        )
        count += 1

    logger.info("sync_players: synced %d players", count)
    return count
```

### 2d. Update `sync_box_score()` to resolve the `player` FK

After creating/updating each `PlayerBoxScore`, resolve the `player` FK from the `player_external_id` already stored on the row:

```python
def sync_box_score(game: Game, client: NBADataClient | None = None) -> int:
    ...
    # After building all box score rows, bulk-resolve Player FKs
    ext_ids = [s["player_external_id"] for s in stats]
    players_by_ext = {
        p.external_id: p
        for p in Player.objects.filter(external_id__in=ext_ids)
    }
    for s in stats:
        ext_id = s["player_external_id"]
        if ext_id in players_by_ext:
            PlayerBoxScore.objects.filter(
                game=game, player_external_id=ext_id
            ).update(player=players_by_ext[ext_id])
    ...
```

This is done as a separate pass after the main upsert loop so that box scores written before `sync_players()` has run can still be back-filled on the next `sync_box_score()` call.

---

## Phase 3: Celery Task & Seed Command

### 3a. New `fetch_players` task in `nba/games/tasks.py`

```python
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_players(self):
    """Sync all NBA players from BallDontLie."""
    try:
        count = sync_players()
        return {"synced": count}
    except Exception as exc:
        logger.error("fetch_players failed: %s", exc)
        raise self.retry(exc=exc)
```

**Scheduling:** Player rosters change via trades and free-agent signings throughout the season. Run `fetch_players` once daily via Celery beat (e.g., 4 AM ET, after `fetch_standings` completes). This is sufficient — player biographical data rarely changes; the main field that updates is `team`.

### 3b. Update `seed_nba.py` management command

Add a `fetch_players()` call to the seed sequence, after `fetch_teams()` (teams must exist before players can resolve their `team` FK):

```python
# seed_nba.py
fetch_teams()
fetch_players()   # new step
fetch_schedule(season=current_season)
fetch_standings(season=current_season)
```

---

## Phase 4: Player Profile Page

### 4a. Views in `nba/games/views.py`

**`PlayerListView`** — Browsable roster with optional filters:

```python
class PlayerListView(LoginRequiredMixin, View):
    def get(self, request):
        team_abbr = request.GET.get("team")
        position = request.GET.get("position")

        players = (
            Player.objects.select_related("team")
            .exclude(team__isnull=True)  # current roster only by default
            .order_by("team__short_name", "last_name")
        )

        if team_abbr:
            players = players.filter(team__abbreviation=team_abbr)
        if position:
            players = players.filter(position__icontains=position)

        teams = Team.objects.order_by("short_name")

        ctx = {
            "players": players,
            "teams": teams,
            "selected_team": team_abbr,
            "selected_position": position,
        }
        return render(request, "games/player_list.html", ctx)
```

**`PlayerDetailView`** — Individual player profile:

```python
class PlayerDetailView(LoginRequiredMixin, View):
    def get(self, request, id_hash):
        player = get_object_or_404(
            Player.objects.select_related("team"),
            id_hash=id_hash,
        )

        # Recent box scores (last 10 games)
        recent_box_scores = (
            player.box_scores
            .select_related("game__home_team", "game__away_team")
            .order_by("-game__game_date")[:10]
        )

        # Season averages (current season, regular season only)
        from nba.games.tasks import _current_season
        from django.db.models import Avg, Sum, Count

        season = _current_season()
        season_games = player.box_scores.filter(
            game__season=season,
            game__postseason=False,
            game__status=GameStatus.FINAL,
        )
        averages = season_games.aggregate(
            games_played=Count("id"),
            ppg=Avg("points"),
            rpg=Avg("reb"),
            apg=Avg("ast"),
            spg=Avg("stl"),
            bpg=Avg("blk"),
            topg=Avg("turnovers"),
            fgm_avg=Avg("fgm"),
            fga_avg=Avg("fga"),
            fg3m_avg=Avg("fg3m"),
            fg3a_avg=Avg("fg3a"),
            ftm_avg=Avg("ftm"),
            fta_avg=Avg("fta"),
        )

        ctx = {
            "player": player,
            "recent_box_scores": recent_box_scores,
            "averages": averages,
            "season": season,
        }
        return render(request, "games/player_detail.html", ctx)
```

### 4b. URL patterns in `nba/games/urls.py`

Add two new routes (before the catch-all `<str:id_hash>/` game detail pattern):

```python
from nba.games.views import (
    GameDetailView, PlayerDetailView, PlayerListView,
    ScheduleView, StandingsView,
)

urlpatterns = [
    path("schedule/", ScheduleView.as_view(), name="schedule"),
    path("standings/", StandingsView.as_view(), name="standings"),
    path("players/", PlayerListView.as_view(), name="player_list"),
    path("players/<str:id_hash>/", PlayerDetailView.as_view(), name="player_detail"),
    path("<str:id_hash>/", GameDetailView.as_view(), name="game_detail"),
]
```

The `players/` prefix ensures these routes don't conflict with the existing game detail wildcard.

### 4c. Templates

**`nba/games/templates/games/player_list.html`**

Extends `nba_website/base.html`. Displays:
- Page heading: "NBA Rosters"
- Team filter dropdown + position filter (`G`, `F`, `C`) — HTMX-free, standard form GET
- Player cards in a responsive grid (3–4 columns on desktop):
  - Headshot (`{% if player.headshot_url %}`) with fallback initials avatar
  - Name (bold), position badge, jersey number
  - Team name with logo
  - Link to player detail page

**`nba/games/templates/games/player_detail.html`**

Extends `nba_website/base.html`. Sections:

1. **Hero header**
   - Player headshot (large, left-aligned) with fallback avatar
   - Name, position, jersey number, team name + logo
   - Bio row: height, weight, country, college, draft info

2. **Season averages card**
   - Stat grid: GP, PPG, RPG, APG, SPG, BPG, TO, FG%, 3P%, FT%
   - FG%, 3P%, FT% computed from `fgm_avg/fga_avg`, etc. in template
   - Shows "No stats for current season" when `averages["games_played"] == 0`

3. **Recent game log table**
   - Columns: Date, Opponent (linked to game detail), MIN, PTS, REB, AST, STL, BLK, FG, 3PT, FT, +/-
   - Opponent name built from game context (was the player's team home or away?)
   - Starter indicator (★) in a subtle left column
   - Rows link to individual game detail pages
   - Shows "No recent games" when `recent_box_scores` is empty

### 4d. Link from box score to player profile

In the existing `games/partials/box_score.html` template, wrap the player name in a link when `row.player` is not None:

```html
{% if row.player %}
  <a href="{{ row.player.get_absolute_url }}" class="hover:underline">
    {{ row.player_name }}
  </a>
{% else %}
  {{ row.player_name }}
{% endif %}
```

---

## Phase 5: Admin

Register `Player` in `nba/games/admin.py`:

```python
@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = [
        "full_name", "position", "jersey_number", "team",
        "country", "draft_year",
    ]
    list_filter = ["position", "team__conference", "team"]
    search_fields = ["first_name", "last_name"]
    raw_id_fields = ["team"]
```

---

## Phase 6: Tests

### Model tests (`nba/tests/test_models.py`)

- `TestPlayer.test_str` — `__str__` returns `full_name`
- `TestPlayer.test_full_name_property` — concatenates first + last
- `TestPlayer.test_get_absolute_url` — produces `/nba/games/players/<id_hash>/`
- `TestPlayer.test_unique_external_id` — duplicate `external_id` raises `IntegrityError`
- `TestPlayer.test_team_fk_nullable` — free-agent player saves without `team`

### Service tests (`nba/tests/test_games_services.py`)

New class `TestSyncPlayers`:

- `test_sync_players_creates_records` — mock `get_players()`, assert `Player.objects.count()`
- `test_sync_players_upserts_on_repeat` — call twice with same data, count stays constant
- `test_sync_players_sets_team_fk` — player with known team resolves FK correctly
- `test_sync_players_handles_free_agent` — player with `team: null` sets `team=None`
- `test_sync_players_builds_headshot_url` — URL uses NBA CDN template with `external_id`

New normalizer tests:

- `TestNBADataClientNormalizers.test_normalize_player_extracts_fields`
- `TestNBADataClientNormalizers.test_normalize_player_handles_null_team`
- `TestNBADataClientNormalizers.test_normalize_player_converts_weight_to_int`
- `TestNBADataClientNormalizers.test_normalize_player_handles_invalid_weight`

### Task tests (`nba/tests/test_games_tasks.py`)

- `TestFetchPlayers.test_fetch_players_calls_sync` — mock `sync_players`, assert called
- `TestFetchPlayers.test_fetch_players_retries_on_error` — exception triggers Celery retry

### View tests (`nba/tests/test_views.py` or new `test_player_views.py`)

`TestPlayerListView`:

- `test_renders_all_rostered_players` — GET `/nba/games/players/` returns 200, players in context
- `test_filters_by_team` — `?team=LAL` returns only Lakers players
- `test_filters_by_position` — `?position=G` returns only guards
- `test_excludes_teamless_players_by_default` — free agents not shown unless explicitly filtered

`TestPlayerDetailView`:

- `test_renders_player_profile` — GET with valid `id_hash` returns 200
- `test_shows_season_averages_when_box_scores_exist`
- `test_shows_empty_state_when_no_box_scores`
- `test_404_for_unknown_id_hash`
- `test_requires_login_redirects_anonymous`

---

## Migration Plan

1. Generate and apply migration for the new `Player` model
2. Generate and apply migration for the new `PlayerBoxScore.player` FK (nullable, no data migration needed)
3. Run `fetch_players()` once (via `seed_nba.py` or manual task invocation) to populate the player table
4. Existing `PlayerBoxScore` rows get back-filled with `player` FKs on the next `sync_box_score()` run

No destructive changes — the denormalized `player_name` / `player_position` / `player_external_id` columns on `PlayerBoxScore` are retained as-is. The new `player` FK is purely additive.

---

## File Changes Summary

| File | Change |
|------|--------|
| `nba/games/models.py` | Add `Player` model; add nullable `player` FK to `PlayerBoxScore` |
| `nba/games/services.py` | Add `NBADataClient._normalize_player()`, `NBADataClient.get_players()` (instance methods); add `sync_players()` module-level function; update `sync_box_score()` to resolve `player` FK |
| `nba/games/tasks.py` | Add `fetch_players` Celery task |
| `nba/games/views.py` | Add `PlayerListView`, `PlayerDetailView` |
| `nba/games/urls.py` | Add `players/` and `players/<id_hash>/` routes |
| `nba/games/admin.py` | Register `PlayerAdmin` |
| `nba/games/templates/games/player_list.html` | New — browsable roster page |
| `nba/games/templates/games/player_detail.html` | New — player profile page |
| `nba/games/templates/games/partials/box_score.html` | Wrap player name in link when `row.player` set |
| `nba/games/management/commands/seed_nba.py` | Add `fetch_players()` call after `fetch_teams()` |
| `nba/tests/test_models.py` | Add `TestPlayer` tests |
| `nba/tests/test_games_services.py` | Add `TestSyncPlayers` + normalizer tests |
| `nba/tests/test_games_tasks.py` | Add `TestFetchPlayers` tests |
| `nba/tests/test_player_views.py` | New — player list + detail view tests |
| `nba/tests/factories.py` | Add `PlayerFactory` |

---

## Future Work

1. **Career averages** — aggregate `PlayerBoxScore` across all seasons for a multi-season stat view. Requires no new API calls, just a broader queryset aggregation.

2. **Top performers widget** — a sidebar widget on the schedule page showing the day's leading scorer / rebounder / assists leader. Uses `PlayerBoxScore.objects.filter(game__game_date=today).order_by("-points")[:3]`.

3. **Player search** — a quick-search input (HTMX `hx-get`) on the player list page that filters by name as you type, using a `?q=` param on `PlayerListView`.

4. **Injured / inactive flag** — BDL doesn't expose injury data on the All-Star tier, but a manual `is_active` boolean field on `Player` could be admin-toggled to hide inactive players from the roster view.
