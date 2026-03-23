# 0008: NBA Algorithmic Odds Engine

**Date:** 2026-03-23

## Motivation

The NBA app was ported with an `OddsClient` that fetched from The Odds API (external, paid). We replaced this with a local algorithmic engine that generates House odds from standings data — no API key needed, runs every 10 minutes via Celery Beat, and seeds automatically with `manage.py seed_nba`.

EPL already had this pattern (`epl/betting/odds_engine.py`) for 1X2 decimal odds. The NBA engine follows the same structure but produces three distinct American-format markets: moneyline, spread, and totals.

## Algorithm

### Team Strength

Each team gets a strength score (0.0–1.0) blended from two inputs:

| Input | Weight | Source |
|-------|--------|--------|
| Win percentage | 60% | `Standing.win_pct` |
| Conference rank (normalized) | 40% | `(16 - conference_rank) / 15` |

When home/away record splits are available (e.g. `"25-10"`), they're blended in at 30% weight — so a team's home strength uses 70% overall + 30% home record.

### Win Probability

Home-court advantage adds **+0.03** to the home team's strength before converting to probability. The resulting home-win probability is clamped to `[0.05, 0.95]`.

### Three Markets

**Moneyline** — Probability → American odds with 5% overround (vig). Clamped to `[-800, +800]`.

**Spread** — `(p_home - 0.5) × 30` gives point spread, rounded to nearest 0.5. Both sides get standard `-110` juice. A team with 60% win probability gets a ~3.0 point spread.

**Totals (Over/Under)** — Base of 222.0 (league average) adjusted ±15 points based on combined team strength. Rounded to nearest 0.5, clamped to `[195, 250]`. Both sides at `-110`.

### Constants

```
HOME_COURT_ADVANTAGE = 0.03
MARGIN             = 0.05       # 5% bookmaker vig
BASE_TOTAL         = 222.0
TOTAL_SWING        = 15.0       # max adjustment from base
SPREAD_FACTOR      = 30.0       # prob differential → points
STANDARD_JUICE     = -110
```

## Data Flow

```
Standing (win_pct, conference_rank, home_record, away_record)
    ↓
odds_engine.generate_game_odds(home_standing, away_standing)
    ↓
dict: home_moneyline, away_moneyline, spread_line, spread_home,
      spread_away, total_line, over_odds, under_odds
    ↓
Odds model (game FK, bookmaker="House", fetched_at=now)
    ↓
GameDetailView → best_odds = Odds.objects.filter(game=game).first()
    ↓
game_detail.html renders three affordances:
  ┌─────────────────────────────────────────┐
  │ MONEYLINE   home_ml  /  away_ml         │
  │ SPREAD      line (home_odds / away_odds) │
  │ TOTAL       line (over / under)          │
  └─────────────────────────────────────────┘
```

## Entry Points

### Celery Beat (every 10 minutes)

`betting.tasks.generate_odds` — bulk creates new `Odds` rows or bulk updates changed ones. Fires an activity event when new odds are created.

```python
# config/settings.py
"generate-odds-10m": {
    "task": "betting.tasks.generate_odds",
    "schedule": timedelta(minutes=10),
}
```

### Seed Command

```bash
manage.py seed_nba              # syncs teams, games, standings, then generates odds
manage.py seed_nba --skip-odds  # skip odds generation
```

## Files

| File | Role |
|------|------|
| `nba/betting/odds_engine.py` | Core algorithm — `generate_game_odds()`, `generate_all_upcoming_odds()` |
| `nba/betting/tasks.py` | Celery task `generate_odds` — bulk upsert pattern |
| `nba/games/models.py` | `Odds` model (moneyline, spread, totals in American format) |
| `nba/games/views.py` | `GameDetailView` — queries `best_odds` and `odds_list` |
| `nba/games/templates/games/game_detail.html` | Renders odds in three-market layout + odds history table |
| `nba/games/management/commands/seed_nba.py` | Calls `generate_all_upcoming_odds()` after standings sync |

## Comparison: NBA vs EPL Odds

| | EPL | NBA |
|--|-----|-----|
| Markets | 1X2 (home/draw/away) | Moneyline, Spread, Totals |
| Format | Decimal (e.g. 2.10) | American (e.g. -110, +150) |
| Draw market | Yes (baseline 0.27) | No |
| Strength inputs | PPG + league position | Win% + conference rank + home/away splits |
| Home advantage | 1.25× multiplier | +0.03 probability |
| Engine file | `epl/betting/odds_engine.py` | `nba/betting/odds_engine.py` |

## Future: Bringing NBA Treatment Back to EPL

The NBA game detail page shows odds more prominently than EPL — dedicated sections for each market type with clear visual affordances. To bring this back to EPL:

1. The EPL `Odds` model only stores `home_win`, `draw`, `away_win` (decimal). No spread or totals — this is correct for soccer (1X2 is the primary market). The display improvement is about layout, not data.
2. The NBA template's three-section layout (moneyline / spread / totals) could inspire a cleaner EPL layout: a prominent 1X2 odds card with the bet form integrated, rather than odds buried in a table.
3. The sticky sidebar pattern (odds + bet form pinned while scrolling discussion) works well and could be adopted by EPL's match detail page.
