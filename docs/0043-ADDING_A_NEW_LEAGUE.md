# 0043: Adding a New League

**Date:** 2026-04-08

## Overview

Step-by-step checklist for adding a new league to the vinosports monorepo. This was most recently done for the 2026 World Cup in [PR #46](https://github.com/zachcalvert/vinosports/pull/46), with a follow-up import fix in [bcababd](https://github.com/zachcalvert/vinosports/commit/bcababdf1dcef363de5e3f146f0fead4a3726788). Use that PR as the canonical reference — it added a full league in a single PR.

Throughout this guide, `<league>` refers to the new league's directory name (e.g., `worldcup`, `nfl`).


## Checklist

### 1. Create the league package

Create `<league>/` at the repo root with the standard sub-apps:

```
<league>/
  __init__.py
  urls.py                  # Top-level URL includes for all sub-apps
  matches/ (or games/)     # Core domain: teams, matches/games, standings
  betting/                 # BetSlip, Parlay, odds engine, futures
  bots/                    # Bot comments, personas, strategies
  discussions/             # User + bot comments on matches
  activity/                # Activity events, WebSocket toasts
  rewards/                 # Reward consumers, context processors
  website/                 # Base template, theme, challenges, seed command
  tests/                   # conftest, factories, test modules
```

Each sub-app needs an `apps.py` with a **prefixed label** to avoid collisions:

```python
# <league>/matches/apps.py
class MatchesConfig(AppConfig):
    name = "<league>.matches"
    default_auto_field = "django.db.models.BigAutoField"
    label = "<league>_matches"  # Required — prevents clash with other leagues
```

Repeat for all sub-apps: `<league>_betting`, `<league>_bots`, `<league>_discussions`, `<league>_activity`, `<league>_rewards`, `<league>_website`.

### 2. Define models

- [ ] **Domain models** in `<league>/matches/models.py` (or `games/`) — Teams, Matches/Games, Standings, Odds. Adapt from the closest existing league
- [ ] **Betting models** in `<league>/betting/models.py` — Extend `AbstractBetSlip`, `AbstractParlay` from `vinosports.betting`. Add sport-specific fields. Define `FuturesMarket`, `FuturesOutcome`, `FuturesBet` if needed
- [ ] **Discussion models** in `<league>/discussions/models.py` — Extend `AbstractComment` from `vinosports.discussions` with match FK
- [ ] **Bot models** in `<league>/bots/models.py` — Extend `AbstractBotComment` from `vinosports.bots` with match FK
- [ ] **Activity models** in `<league>/activity/models.py` — Extend `AbstractActivityEvent` from `vinosports.activity`
- [ ] Use prefixed FK strings everywhere: `"<league>_matches.Match"`, `"<league>_betting.BetSlip"`, etc.

### 3. Register in config (8 files)

#### `config/settings.py`
- [ ] Add all sub-apps to `INSTALLED_APPS`:
  ```python
  # <League>
  "<league>.matches",
  "<league>.betting",
  "<league>.bots",
  "<league>.discussions",
  "<league>.activity",
  "<league>.rewards",
  "<league>.website",
  ```
- [ ] Add context processors for each sub-app that provides one (betting, matches, website, activity, rewards)
- [ ] Add league-specific Celery beat schedules if needed

#### `config/urls.py`
- [ ] Add URL include: `path("<league>/", include("<league>.urls"))`

#### `config/middleware.py`
- [ ] Add path detection to `LeagueMiddleware`:
  ```python
  elif path.startswith("/<league>/"):
      request.league = "<league>"
  ```

#### `config/asgi.py`
- [ ] Import WebSocket routing modules from the new league
- [ ] Add a `path("<league>/", URLRouter(...))` entry to the WebSocket URLRouter

> **Note:** Imports in `asgi.py` must come *after* `get_asgi_application()` is called, since routing modules import models. See the `# ruff: noqa` pattern at the top of the file. This was the cause of the [follow-up fix](https://github.com/zachcalvert/vinosports/commit/bcababdf1dcef363de5e3f146f0fead4a3726788).

#### `config/celery.py`
- [ ] Add all sub-apps to `autodiscover_tasks`:
  ```python
  "<league>.matches",
  "<league>.betting",
  "<league>.bots",
  "<league>.discussions",
  "<league>.activity",
  "<league>.website",
  ```
- [ ] If the league has challenges, add to the `challenge_tasks` autodiscovery list

### 4. Docker and infrastructure

#### `docker-compose.yml`
- [ ] Add `<league>` volume mount to the `web`, `tailwind`, and `worker` services:
  ```yaml
  - ./<league>:/app/<league>
  ```
- [ ] Add league queue to the worker command: `-Q epl,nba,nfl,<league>`

#### `fly.toml`
- [ ] Add league queue to the production worker process command

#### `tailwind.config.js`
- [ ] Add template content path: `./<league>/**/templates/**/*.html`

#### `Makefile`
- [ ] Add seed commands to the `seed` target
- [ ] Add `--cov=<league>` to the `test-ci` target

### 5. Data layer

- [ ] **Data client** in `<league>/matches/services.py` — API client for the league's data source (scores, standings, schedules)
- [ ] **Seed command** in `<league>/website/management/commands/seed_<league>.py` — Populates teams, matches, standings, generates odds
- [ ] **Futures seed command** if applicable — `seed_<league>_futures.py`
- [ ] **Static data** for offline seeding — JSON files in `<league>/matches/static_data/` or similar
- [ ] **Odds engine** in `<league>/betting/odds_engine.py` — Adapted from closest existing league
- [ ] **Futures odds engine** if applicable — `<league>/betting/futures_odds_engine.py`

### 6. Views and templates

- [ ] **Template directories** must be prefixed: `<league>_matches/`, `<league>_betting/`, `<league>_website/`, etc.
- [ ] **Static directories** must be prefixed: `<league>_website/css/`, `<league>_website/js/`
- [ ] **URL namespaces** must be prefixed in each sub-app's `urls.py`: `app_name = "<league>_matches"`
- [ ] **Base template** in `<league>/website/templates/<league>_website/base.html` — League-specific theme, sidebar, footer
- [ ] **Theme** in `<league>/website/theme.py` — CSS custom properties (colors, accent)
- [ ] **Context processors** — Guard with `if getattr(request, 'league', None) != '<league>': return {}`

### 7. WebSocket consumers

- [ ] **Live updates consumer** — Score broadcasts for in-progress matches
- [ ] **Activity consumer** — Activity feed toasts
- [ ] **Rewards consumer** — Badge/reward notifications (if rewards are enabled)
- [ ] **Routing modules** in each sub-app's `routing.py` — Define `websocket_urlpatterns`

### 8. Bots

- [ ] **Personas** in `<league>/bots/personas.py` — Bot personality definitions
- [ ] **Strategies** in `<league>/bots/strategies.py` — Comment generation strategies
- [ ] **Comment service** in `<league>/bots/comment_service.py` — Orchestrates bot commentary
- [ ] **Celery tasks** in `<league>/bots/tasks.py` — Scheduled/triggered bot comment generation
- [ ] Add `active_in_<league>` field to core `BotProfile` model (migration in `vinosports-core`), or reuse an existing flag if the sport type is similar

### 9. Hub integration

The hub serves as the cross-league homepage. These files aggregate data across all leagues and need updating:

- [ ] **`hub/views.py` — `_get_live_games()`** — Add the new league's live match query so games appear in the live scores strip
- [ ] **`hub/views.py` — My Bets views** — Import the new league's `BetSlip` (and `FuturesBet`/`Parlay` if applicable) so bets appear in the user's bet history
- [ ] **`hub/templates/hub/my_bets.html`** — Add league badge color and display logic for the new league's bets
- [ ] **`hub/templates/hub/partials/live_games_strip.html`** — Add league badge for live games

### 10. Admin

- [ ] Register all new models in each sub-app's `admin.py`
- [ ] Use meaningful `list_display`, `list_filter`, `search_fields`
- [ ] Core shared models (UserBalance, Badge, etc.) are registered in EPL's admin only — do not duplicate

### 11. Tests

- [ ] **Factories** in `<league>/tests/factories.py` — Team, Match, BetSlip, User factories
- [ ] **`conftest.py`** — Shared fixtures (authenticated client, seeded data)
- [ ] **Model tests** — Creation, constraints, properties
- [ ] **Betting tests** — Odds engine, bet placement, settlement, payout
- [ ] **View tests** — Key pages render, forms submit, permissions enforced
- [ ] **Discussion tests** — Comment creation, listing, permissions

### 12. Final verification

- [ ] `make migrate` — No errors
- [ ] Seed commands run successfully
- [ ] `make test` — All tests pass, no regressions
- [ ] `make lint` — Clean
- [ ] Visit `http://vinosports.local/<league>/` — Dashboard renders
- [ ] Place a bet — Balance deducted correctly
- [ ] Settle a match — Bet settled, balance updated
- [ ] Bot comments generate without errors
- [ ] WebSocket connections work (live scores, activity toasts)
- [ ] Hub "My Bets" page shows bets from the new league
- [ ] Live games strip shows in-progress matches from the new league


## Reference

- **World Cup PR (canonical example):** [zachcalvert/vinosports#46](https://github.com/zachcalvert/vinosports/pull/46)
- **Follow-up import fix:** [bcababd](https://github.com/zachcalvert/vinosports/commit/bcababdf1dcef363de5e3f146f0fead4a3726788) — ASGI import ordering must initialize Django before importing routing modules
- **World Cup design doc:** [0042-2026_WORLD_CUP.md](0042-2026_WORLD_CUP.md)
- **Architecture overview:** See `CLAUDE.md` at repo root for full structural documentation
