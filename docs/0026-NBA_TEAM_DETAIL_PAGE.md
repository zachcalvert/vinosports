# 0026 — NBA Team Detail Page

**Date:** 2026-03-26
**Status:** Planned

## Overview

Teams are a core entity in the NBA app but currently have no dedicated page. Users can see team names in standings and on player profiles, but there's no way to view a team's full profile — record, seed, roster, and recent/upcoming games — in one place.

This doc proposes adding a team detail page at `/nba/games/teams/<abbreviation>/` that serves as a hub for everything about a team.

---

## What Already Exists

All required data is already modeled — no schema changes or migrations needed.

| Model | Relevant Fields |
|-------|----------------|
| `Team` | `name`, `short_name`, `abbreviation`, `logo_url`, `conference`, `division` |
| `Standing` | `wins`, `losses`, `win_pct`, `conference_rank`, `streak`, `home_record`, `away_record` (FK to Team) |
| `Player` | Full bio fields, `team` FK (`related_name="players"`), `is_active` boolean |
| `Game` | `home_team`/`away_team` FKs, `game_date`, `tip_off`, `status`, scores |

---

## URL Design

```
/nba/games/teams/<abbreviation>/
```

Uses the team's `abbreviation` (lowercased) as the slug — human-readable and matches how sports sites typically structure team URLs (e.g. `/teams/lal/`, `/teams/bos/`). Case-insensitive lookup so `/teams/LAL/` and `/teams/lal/` both work.

Must be placed **before** the catch-all `<str:id_hash>/` game detail pattern in `urls.py`.

---

## Model Change

Add `get_absolute_url()` to the `Team` model:

```python
def get_absolute_url(self):
    return reverse("nba_games:team_detail", kwargs={"abbreviation": self.abbreviation.lower()})
```

No migration needed — method only.

---

## View

`TeamDetailView(LoginRequiredMixin, View)` with five queries:

1. **Team** — `get_object_or_404(Team, abbreviation__iexact=abbreviation)`
2. **Standing** — current season standing (record, seed, streak, home/away splits)
3. **Active roster** — `Player.objects.filter(team=team, is_active=True).order_by("last_name")`
4. **Last completed game** — most recent game with `status=FINAL` where team is home or away
5. **Next upcoming game** — earliest future game with `status=SCHEDULED` where team is home or away

---

## Template Layout

Three-section design following existing patterns from `player_detail.html` (accent bars, card styling, stat grid dividers).

### Hero Card (full width)

```
┌──────────────────────────────────────────────────┐
│  [logo 80x80]  TEAM FULL NAME                    │
│                 Conference · Division              │
│                                                    │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐      │
│  │Seed│ │ W  │ │ L  │ │PCT │ │Home│ │Away│       │
│  │ #3 │ │ 40 │ │ 20 │ │.667│ │25-5│ │15-15│     │
│  └────┘ └────┘ └────┘ └────┘ └────┘ └────┘      │
│                                        Streak     │
└──────────────────────────────────────────────────┘
```

### Bento Game Cards (2-col grid on md+)

```
┌──────────────────────┐ ┌──────────────────────┐
│  LAST GAME            │ │  NEXT GAME            │
│                        │ │                        │
│  OPP logo + abbr      │ │  OPP logo + abbr      │
│  Final score  W/L     │ │  Tip-off date/time    │
│  "View Game →"        │ │  "View Game →"        │
└──────────────────────┘ └──────────────────────┘
```

### Roster Table (full width)

```
┌──────────────────────────────────────────────────┐
│  ROSTER (N players)                               │
│  # │ Player (linked) │ Pos │ Ht │ Wt │ College  │
│  ──┼─────────────────┼─────┼────┼────┼────────  │
│  23│ LeBron James    │ F   │6-9 │250 │ n/a      │
│  ...                                              │
└──────────────────────────────────────────────────┘
```

### Empty States

- No standing: "No standings data for current season"
- No last game: hide the bento box (or muted message)
- No next game: hide the bento box (or muted message)
- Empty roster: "No active players found"

---

## Navigation Integration

Make team names clickable in three existing templates:

1. **Standings table** (`partials/_standings_body.html`) — wrap team name in link
2. **Player detail page** (`player_detail.html`) — make team name in hero clickable
3. **Player list page** (`player_list.html`) — make team column a link

No sidebar link needed yet — teams are discoverable from standings and player pages.

---

## Testing

New file: `nba/tests/test_team_views.py` (following `test_player_views.py` patterns).

| Test | Asserts |
|------|---------|
| `test_renders_team_page` | 200, correct template, team in context |
| `test_case_insensitive_abbreviation` | `/teams/lal/` resolves team with abbreviation "LAL" |
| `test_shows_standing_when_exists` | `context["standing"]` populated |
| `test_handles_no_standing_gracefully` | `context["standing"]` is None, page still renders |
| `test_shows_active_roster_only` | 2 active + 1 inactive → roster count == 2 |
| `test_shows_last_game` | Final game appears in context |
| `test_shows_next_game` | Scheduled future game appears in context |
| `test_404_for_unknown_abbreviation` | 404 response |
| `test_requires_login` | Anonymous user redirected to login |

---

## Implementation Order

1. Add `get_absolute_url` to Team model
2. Add `TeamDetailView` in `views.py`
3. Add URL pattern in `urls.py`
4. Create `team_detail.html` template
5. Update existing templates with team links
6. Write tests

---

## Future Considerations

- **Season stats aggregation**: average points scored/allowed per game, calculated from Game model
- **Full schedule tab**: paginated list of all games for the team this season
- **Head-to-head**: when viewing a team's next game, show season series record vs that opponent
- **Player stats on roster**: add season averages (PPG, RPG, APG) to roster rows via PlayerBoxScore aggregation
