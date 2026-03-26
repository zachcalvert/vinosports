# 0022: ParlayBuilder — Sponsored Bot Parlays

**Date:** 2026-03-25

## Overview

A shared `ParlayBuilder` class that encapsulates the logic for constructing "sponsored" parlays for bots, replacing the inline parlay construction currently embedded in each league's bot task code.

## What Exists

### Current Bot Parlay Flow
- **EPL** (`epl/bots/tasks.py` → `execute_bot_strategy()`): picks matches based on strategy, builds parlays inline with decimal odds, places via betting service
- **NBA** (`nba/bots/tasks.py` → `execute_bot_strategy()`): similar flow but with American odds, moneyline/spread/total markets

### Key Differences Between Leagues
| | EPL | NBA |
|---|---|---|
| Odds format | Decimal (1.50, 2.00) | American (-150, +130) |
| Markets | 1X2 (Home/Draw/Away) | Moneyline, Spread, Total |
| Combined odds | Multiply decimals | Convert each to decimal, multiply, convert back |
| Leg model | `ParlayLeg(match, selection, odds_at_placement)` | `ParlayLeg(game, market, selection, odds_at_placement, line)` |

### Bot Strategy Types
FRONTRUNNER, UNDERDOG, SPREAD_SHARK, PARLAY, TOTAL_GURU, DRAW_SPECIALIST, VALUE_HUNTER, CHAOS_AGENT, ALL_IN_ALICE, HOMER, ANTI_HOMER

## What to Build

### ParlayBuilder Interface
```python
class ParlayBuilder:
    """Builds sponsored parlays for a bot based on its strategy."""

    def __init__(self, bot_profile, league):
        ...

    def select_legs(self, available_matches, max_legs=4):
        """Pick legs based on strategy. Delegates to league-specific leg picker."""
        ...

    def build(self, stake):
        """Construct and save the Parlay + ParlayLegs."""
        ...
```

### Design Decisions
- **Where it lives:** `packages/vinosports-core/src/vinosports/bots/parlay_builder.py` (core package) or each league provides its own builder subclass
- **Leg selection interface:** Each league registers a `LegPicker` that understands its odds format and markets. The builder calls the picker, then handles stake/payout calculation
- **"Sponsored" display:** Parlays built by the builder get flagged (e.g., `is_sponsored=True`) so the frontend can feature them differently
- **Featured parlays:** Could surface bot-built parlays as "today's picks" on league dashboards

## Key Files
- `epl/bots/tasks.py` — current inline parlay construction (EPL)
- `nba/bots/tasks.py` — current inline parlay construction (NBA)
- `packages/vinosports-core/src/vinosports/bots/models.py` — BotProfile, strategy_type
- `epl/betting/models.py` — EPL Parlay/ParlayLeg
- `nba/betting/models.py` — NBA Parlay/ParlayLeg
