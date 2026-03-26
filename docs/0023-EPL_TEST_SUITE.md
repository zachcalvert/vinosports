# 0023: EPL Test Suite

**Date:** 2026-03-25

## Overview

Build a comprehensive test suite for the EPL app, mirroring the structure and coverage of the NBA test suite.

## NBA Test Suite (Reference)

Located at `nba/tests/`, the NBA suite includes ~18 test files:

| File | Coverage |
|------|----------|
| `factories.py` | 17 factories (User, Team, Game, Standing, Odds, BetSlip, Parlay, ParlayLeg, BotProfile, Comment, ActivityEvent) |
| `test_models.py` | Model validation (Team ordering, Game is_live/is_final/winner, Standing, Odds) |
| `test_betting_views.py` | OddsBoard, PlaceBet, MyBets, ParlayBuilder views + forms |
| `test_betting_tasks.py` | Bet settlement, balance updates, activity events |
| `test_challenges_tasks.py` | Challenge progress evaluation + reward crediting |
| `test_discussion_views.py` | Comment creation, pagination, soft delete |
| `test_views.py` | Dashboard, account, theme toggle |
| `test_games_services.py` | Game sync, odds generation, standing updates |
| `test_games_tasks.py` | fetch_live_scores, settle_games |
| `test_odds_engine.py` | American odds generation from spreads/totals |
| `test_consumers.py` | WebSocket consumers |
| `test_context_processors.py` | League context, theme |
| `test_forms.py` | Form validation |
| `test_settlement.py` | Payout calculation, balance updates |
| `test_schedule.py` | Schedule views with filtering |
| `test_game_detail_view.py` | Game detail page rendering |

Uses pytest with factory_boy, `@pytest.mark.django_db`, atomic transactions.

## EPL Equivalents to Build

| NBA File | EPL Equivalent | Key Differences |
|----------|---------------|-----------------|
| `factories.py` | `factories.py` | Match (not Game), decimal odds (not American), 1X2 market (not moneyline/spread/total) |
| `test_models.py` | `test_models.py` | Match, Team, Standing, Odds model validation |
| `test_betting_views.py` | `test_betting_views.py` | Odds board, place bet (1X2 selection), my bets, parlay views |
| `test_betting_tasks.py` | `test_betting_tasks.py` | Settlement with decimal odds payout |
| `test_challenges_tasks.py` | `test_challenges_tasks.py` | All 9 evaluators (EPL has more than NBA) |
| `test_discussion_views.py` | `test_discussion_views.py` | Comment CRUD, pagination |
| `test_views.py` | `test_views.py` | Dashboard (matchday-based), league table |
| `test_matches_services.py` | New | Match sync, odds generation, standings |
| `test_settlement.py` | `test_settlement.py` | Decimal odds payout calculation |
| `test_consumers.py` | `test_consumers.py` | WebSocket consumers |
| `test_context_processors.py` | `test_context_processors.py` | EPL context processors |
| `test_forms.py` | `test_forms.py` | Bet placement forms |
| `test_challenge_engine.py` | New (EPL-specific) | All 9 evaluators in challenge_engine.py |

## Key Differences from NBA
- **Odds:** Decimal (multiply stake * odds for payout) vs. American (conversion formula)
- **Markets:** Single market (1X2) vs. three markets (moneyline, spread, total)
- **Fixtures:** Matchday-based schedule vs. date-based schedule
- **Standings:** League table (20 teams, points/GD) vs. conference standings (wins/losses/pct)
- **Challenges:** EPL has full engine with 9 evaluators; tests should cover all of them

## Key Files
- `nba/tests/` — full reference test suite
- `epl/matches/` — Match, Team, Standing, Odds models
- `epl/betting/` — BetSlip, Parlay, ParlayLeg, settlement
- `epl/website/challenge_engine.py` — 9 challenge evaluators
- `epl/discussions/` — Comment model and views
- `epl/bots/` — BotComment, strategies
