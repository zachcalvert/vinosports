# 0033 — NBA Odds Board

## Summary

Add a dedicated Odds page to the NBA app at `/nba/odds/`, modeled after the EPL odds board. Displays the next two days of scheduled games with current odds across all three markets (Moneyline, Spread, Total), with inline quick-bet forms and one-click parlay building.

## Motivation

The EPL app has a dedicated odds board that lets users scan all upcoming matches and place bets or build parlays without navigating into individual match pages. The NBA app currently lacks this — users must visit individual game detail pages to see odds. An odds board gives bettors a fast, scannable view of the full slate and makes parlay construction much easier.

## Existing Infrastructure (no changes needed)

The NBA betting app already has all the backend plumbing:

- **Models**: `Game`, `Odds` (with `home_moneyline`, `away_moneyline`, `spread_line`, `spread_home`, `spread_away`, `total_line`, `over_odds`, `under_odds`), `BetSlip`, `Parlay`, `ParlayLeg`
- **Parlay session flow**: `AddToParlayView`, `RemoveFromParlayView`, `ClearParlayView`, `PlaceParlayView` — all session-based, accepting `game_id`, `market`, `selection`, `odds`, `line`
- **Quick bet form**: `QuickBetFormView` handles all three market types via query params (`market`, `selection`, `container`)
- **Context processor**: Parlay slip context processor already injects slip data into all NBA templates
- **Parlay slip template**: `nba_betting/partials/parlay_slip.html` already renders the floating slip panel

## Design

### URL Routing

| URL | View | Name | Purpose |
|-----|------|------|---------|
| `/nba/odds/` | `OddsBoardView` | `nba_betting:odds` | Full page |
| `/nba/odds/partial/` | `OddsBoardPartialView` | `nba_betting:odds_partial` | HTMX polling body |

Both routes are already under the `nba/betting/urls.py` URL conf which is mounted at `odds/` in `nba/urls.py`.

### View Logic

`OddsBoardView(TemplateView)`:
- Queries games for next 2 days: `Game.objects.filter(game_date__range=[today_et(), today_et() + timedelta(days=1)], status=GameStatus.SCHEDULED)`
- Select-related `home_team`, `away_team`
- Fetches latest odds per game via `Prefetch` or post-query attachment
- Groups games by `game_date` for date header rendering (Today / Tomorrow)
- Passes `last_odds_refresh` timestamp and `rendered_at`

`OddsBoardPartialView(OddsBoardView)`:
- Inherits query logic, overrides `template_name` to the body partial for HTMX swap

### Template Layout

**Desktop**: Table with columns for all three NBA markets:

| Tip-off | Away | Home | ML Away | ML Home | Spread Away | Spread Home | Over | Under |

Each odds cell contains:
1. A clickable odds button (`hx-get` to `QuickBetFormView`) that opens an inline bet form
2. A small "+ parlay" button (`hx-post` to `AddToParlayView`) for one-click parlay leg addition

Spread cells show the line alongside odds (e.g., "-3.5 (-110)").
Total cells show O/U label with line (e.g., "O 224.5 (-110)").

**Mobile**: Card layout with three market sections per game, each containing two selection buttons.

### Odds Format

NBA uses American odds (integers). Display with +/- prefix:
- Negative (favorites): `-110`
- Positive (underdogs): `+150`

No template tag needed — handled inline with `{% if odds > 0 %}+{% endif %}{{ odds }}`.

### HTMX Interactions

- **Polling**: Odds board body refreshes every 30 seconds via `hx-get` / `hx-trigger="every 30s"`
- **Quick bet**: Clicking an odds value loads inline bet form via `hx-get` to `nba_betting:quick_bet_form`
- **Parlay add**: "+ parlay" buttons `hx-post` to `nba_betting:parlay_add` with `game_id`, `market`, `selection`, `odds`, `line` in `hx-vals`
- **Parlay slip**: Updates via `hx-target="#parlay-slip-panel"` / `hx-swap="outerHTML"` (existing pattern)

### Two-Day Window

Uses `today_et()` from `nba.games.services` to get the current date in Eastern Time (how `game_date` is stored). Shows today's and tomorrow's games only, keeping the board focused and scannable.

## Files to Create

| File | Purpose |
|------|---------|
| `nba/betting/templates/nba_betting/odds_board.html` | Main page template |
| `nba/betting/templates/nba_betting/partials/odds_board_body.html` | Polling body partial |

## Files to Modify

| File | Change |
|------|--------|
| `nba/betting/views.py` | Add `OddsBoardView`, `OddsBoardPartialView` |
| `nba/betting/urls.py` | Add `""` and `"partial/"` routes |
| `nba/templates/nba_website/components/sidebar.html` | Add "Odds" nav link |

## Out of Scope

- Odds history / line movement charts
- Market-specific filtering or sorting
- Odds comparison across bookmakers (NBA uses single source)
- Custom date range selection
