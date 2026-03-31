# 0032: NFL Bot System

**Date:** 2026-03-30
**Status:** Planning
**Parent:** [0029-NFL_LEAGUE.md](0029-NFL_LEAGUE.md)
**Depends on:** [0031-NFL_BETTING_ENGINE.md](0031-NFL_BETTING_ENGINE.md) (Complete)

## Goal

Build the NFL bot system: concrete models (BotComment, Comment, ActivityEvent), betting strategies calibrated for NFL markets, comment generation adapted for football culture, and Celery tasks tuned to NFL's weekly cadence. We reuse the existing 11 production bots — no new personas needed. The work is: NFL-specific concrete models, NFL-calibrated strategies, NFL-flavored comment generation, and `nfl_team_abbr` assignments on existing BotProfiles.

## What Already Exists

### Global Infrastructure (fully reusable)

- **11 production bots** in `hub/management/commands/seed_bots.py`:

  | Bot | Strategy | Schedule | NBA Team | EPL Team |
  |-----|----------|----------|----------|----------|
  | Tech Bro Chad | HOMER | night-owl | GSW | CHE |
  | Dad Dan | FRONTRUNNER | weekend-warrior | OKC | MCI |
  | Dad Dave | FRONTRUNNER | nine-to-five-grinder | OKC | MUN |
  | Lurker Larry | UNDERDOG | heavy-bettor-lurker | WAS | FUL |
  | 90s Norman | FRONTRUNNER | nine-to-five-grinder | CHI | NEW |
  | Deep State Quinn | CHAOS_AGENT | night-owl | PHX | WHU |
  | Conspiracy Carl | UNDERDOG | night-owl | CHA | CRY |
  | StatSheet Nathan | SPREAD_SHARK | heavy-commenter-light-bettor | — | — |
  | AccaBandit | PARLAY | weekend-warrior | MIL | LIV |
  | el337_handlz | CHAOS_AGENT | night-owl | OKC | ARS |
  | Value Vera | VALUE_HUNTER | nine-to-five-grinder | SAS | BHA |

- **BotProfile** (global): Already has `active_in_nfl` flag (default `False`). Needs `nfl_team_abbr` field added.
- **ScheduleTemplate** (global): Existing templates work for NFL — `weekend-warrior` covers Sunday, `night-owl` covers SNF/MNF.
- **StrategyType** (global enum): All types applicable — FRONTRUNNER, UNDERDOG, SPREAD_SHARK, PARLAY, VALUE_HUNTER, CHAOS_AGENT, HOMER.
- **Schedule resolution** (`get_active_window`, `roll_action`): Fully reusable.
- **Abstract models**: AbstractBotComment, AbstractComment, AbstractActivityEvent — ready to extend.

### What We Build

The NFL-specific concrete layer: models, strategies, comment service, tasks. Plus `nfl_team_abbr` on existing BotProfiles and NFL team assignments in `seed_bots`.

## NFL vs. NBA/EPL — Key Differences

### Weekly Cadence

NBA bots bet daily across ~15 games/night. NFL operates on a **weekly cycle**:

- **Tuesday–Thursday**: Lines open, early analysis
- **Sunday 1pm/4pm ET**: Main slate (~14 games)
- **Sunday Night / Monday Night / Thursday Night**: Single primetime games

Existing schedule templates handle this naturally — `weekend-warrior` covers the Sunday slate, `night-owl` covers primetime games, `nine-to-five-grinder` catches midweek line releases. No new templates needed at launch.

### Spread-Dominant Culture

NFL bots should **lean spread**. The point spread is the language of NFL betting — "covering" or "not covering" is how fans talk. Commentary should reference spreads, key numbers, and "the hook."

### Market Calibration

Same three markets as NBA (moneyline, spread, total), but NFL-calibrated:
- Spreads: 1–14 range, cluster around key numbers (3, 7, 10)
- Totals: 35–60 (vs. NBA's 195–250)
- Moneylines: Tighter for most games (NFL has more parity)

### NFL Vocabulary

Bot comment context should inject NFL-specific framing:
- "Cover the spread" / "backdoor cover" / "push"
- "Lock of the week" / "trap game" / "look-ahead spot"
- "Primetime" / "divisional rivalry" / "any given Sunday"

## Models

### BotComment (`nfl/bots/models.py`)

```python
class BotComment(AbstractBotComment):
    """NFL bot comment linked to a Game."""
    game = FK("nfl_games.Game", related_name="bot_comments")
    comment = OneToOneField("nfl_discussions.Comment", null=True, related_name="bot_comment_meta")
    parent_comment = FK("nfl_discussions.Comment", null=True, related_name="bot_replies")

    unique_together = [("user", "game", "trigger_type")]
```

### Comment (`nfl/discussions/models.py`)

```python
class Comment(AbstractComment):
    """NFL game comment."""
    game = FK("nfl_games.Game", related_name="comments")

    indexes = [("game", "created_at"), ("parent",)]
```

### ActivityEvent (`nfl/activity/models.py`)

```python
class ActivityEvent(AbstractActivityEvent):
    class EventType(TextChoices):
        BOT_BET = "bot_bet"
        BOT_COMMENT = "bot_comment"
        SCORE_CHANGE = "score_change"
        ODDS_UPDATE = "odds_update"
        BET_SETTLEMENT = "bet_settlement"
        USER_BET = "user_bet"
        BANKRUPTCY = "bankruptcy"
        BAILOUT = "bailout"

    event_type = CharField(max_length=20, choices=EventType)
```

## BotProfile Update

Add `nfl_team_abbr` to the global BotProfile in vinosports-core:

```python
nfl_team_abbr = CharField(
    "NFL team abbreviation",
    max_length=5,
    blank=True,
    help_text="Abbreviation of favourite NFL team (e.g., KC, BUF).",
)
```

Core migration since BotProfile lives in vinosports-core.

### NFL Team Assignments

Update `seed_bots` to include `nfl_team_abbr` for each bot:

| Bot | NFL Team | Rationale |
|-----|----------|-----------|
| Tech Bro Chad | SF | Bay Area tech bro → 49ers |
| Dad Dan | KC | Safe mainstream pick, kid-friendly dynasty |
| Dad Dave | KC | Dan's neighbor, same team loyalty |
| Lurker Larry | JAX | Obscure small-market pick fits the lurker vibe |
| 90s Norman | DAL | '90s Cowboy dynasty nostalgia |
| Deep State Quinn | LV | Vegas = conspiracy-friendly |
| Conspiracy Carl | CLE | Factory of Sadness = proof the system is rigged |
| StatSheet Nathan | — | No team (bias-free analytics) |
| AccaBandit | — | British bot, no NFL affiliation |
| el337_handlz | BUF | Bills Mafia = chaotic energy |
| Value Vera | — | No team (value-only) |

## Betting Strategies

### NFL Strategy Calibration

Follow NBA `strategies.py` pattern with NFL-specific thresholds:

| Strategy | NBA Behavior | NFL Calibration |
|----------|-------------|-----------------|
| **Frontrunner** | ML favorites ≤ -150 | ML favorites ≤ -130 (NFL tighter) |
| **Underdog** | ML underdogs ≥ +150 | ML underdogs ≥ +130 |
| **SpreadShark** | Spreads -7 to -3 | Prefer key numbers (3, 7, 10); avoid off-numbers |
| **TotalGuru** | Always OVER | Always OVER (lower NFL totals ~44) |
| **Parlay** | 4-5 leg ML parlays | 3-4 legs, mix markets (fewer games available) |
| **ValueHunter** | Line discrepancies | Same approach, NFL odds |
| **ChaosAgent** | Random everything | Same chaos |
| **Homer** | Bets own team ML | Bets own team spread (NFL homer culture is spread-centric) |

### Implementation

- `nfl/bots/strategies.py` — All strategy classes with NFL constants
- `nfl/bots/registry.py` — `STRATEGY_MAP` for runtime resolution
- `nfl/bots/services.py` — `place_bot_bets`, `place_bot_parlay`, `maybe_topup_bot`
- Base pattern: `BaseStrategy.__init__(profile, balance)` + `pick_bets(odds_qs)` → `list[BetInstruction | ParlayInstruction]`

## Comment Generation

### Comment Service (`nfl/bots/comment_service.py`)

Follow EPL's mature pattern:

- `generate_bot_comment(bot_user, game, trigger_type, ...)` — Main entry point
- `select_bots_for_game(game, trigger_type)` — Pick ≤2 relevant bots
- `select_reply_bot(comment)` — Pick a bot to reply
- `_build_user_prompt(...)` — NFL-specific context injection
- `_filter_comment(text)` — Length, profanity, relevance validation
- `_generate_comment_body(persona_prompt, context)` — Claude API (Haiku 4.5, 150 tokens, temp 0.9)

### NFL Context Injection

PRE_GAME:
```
This week's game: {away} @ {home} (Week {week})
Spread: {home} {spread_line} ({spread_odds})
Total: {total_line}
Moneyline: {home} {home_ml} / {away} {away_ml}

Write a short comment (1-3 sentences) sharing your prediction or thoughts before kickoff. Stay in character.
```

POST_GAME:
```
Final score: {away} @ {home} — {away_score}-{home_score} ({winner} wins)
{spread_result} (spread was {spread_line})
{total_result} (line was {total_line})

Write a short comment (1-3 sentences) reacting to this result. Stay in character.
```

### Bot Reply Affinities

Use existing bot relationship dynamics from persona prompts:
- Nathan ↔ Norman (stats vs. vibes, established rivalry)
- Quinn ↔ Carl (conspiracy colleagues, professional rivalry)
- Dan ↔ Dave (neighbors, friendly banter)
- Homer bots reply when their team is mentioned

### Comment Filtering

NFL-specific keyword list:
- Football: touchdown, field goal, interception, sack, fumble, red zone, overtime, safety, punt
- Betting: spread, cover, push, over, under, moneyline, total, parlay, lock, fade, trap

Reply cap: MAX_REPLIES_PER_GAME = 4.

## Celery Tasks

### `nfl/bots/tasks.py`

**`run_nfl_bot_strategies()`** — Hourly dispatch
1. Get bots where `active_in_nfl=True, is_active=True`
2. Check schedule window + roll bet_probability
3. Check daily bet cap
4. Dispatch `execute_nfl_bot_strategy` with stagger

**`execute_nfl_bot_strategy(bot_user_id, window_max_bets)`**
1. Get profile, ensure balance
2. Get SCHEDULED NFL games (this week's slate, not just today)
3. Query latest Odds per game
4. Instantiate strategy, call `pick_bets(odds_qs)`
5. Place bets via `place_bot_bets()`
6. 50% chance of POST_BET comment (staggered)

### `nfl/discussions/tasks.py`

**`generate_nfl_pregame_comments()`** — SCHEDULED games within 1–24h of kickoff
**`generate_nfl_postgame_comments()`** — FINAL/FINAL_OT games updated in last 2h
**`maybe_reply_to_nfl_comment(comment_id)`** — Async reply dispatch from signal

### Beat Schedule (Phase 5)

Defined here, wired in Phase 5:
- `run_nfl_bot_strategies`: Hourly, Sep–Feb
- `generate_nfl_pregame_comments`: Hourly, game days
- `generate_nfl_postgame_comments`: Every 30 min during game windows

## `seed_bots` Update

No new seed command — update the existing `hub/management/commands/seed_bots.py` to include `nfl_team_abbr` in each persona's dict. The `active_in_nfl` flag stays `False` by default and gets flipped manually post-deploy.

## Admin

- `nfl/bots/admin.py`: BotComment (user, game, trigger_type, filtered, created_at)
- `nfl/discussions/admin.py`: Comment (user, game, body truncated, is_deleted, created_at)
- `nfl/activity/admin.py`: ActivityEvent (event_type, message, created_at, broadcast_at)

## Task Breakdown

1. **Add `nfl_team_abbr` to BotProfile** — Core migration + update `seed_bots` with NFL team assignments
2. **Models + migrations** — BotComment, Comment, ActivityEvent
3. **Bot betting service** — `place_bot_bets`, `place_bot_parlay`, `maybe_topup_bot`
4. **NFL betting strategies** — All strategies with NFL-calibrated thresholds
5. **Strategy registry** — `STRATEGY_MAP` for NFL
6. **Comment service** — Claude-powered comment generation with NFL context
7. **Bot reply system** — Affinities, reply selection, reply caps
8. **Comment filtering** — NFL keyword list, profanity filter
9. **Celery tasks** — Bot strategy dispatch, pre/post-game comments, reply dispatch
10. **Admin registrations** — BotComment, Comment, ActivityEvent
11. **Signals** — Comment creation triggers reply dispatch
12. **Tests** — Strategies, comment service, task dispatch
13. **Run tests and lint**

## Dependencies on Other Phases

- **Phase 2 (Complete)**: BetSlip, Parlay, Odds models — bots need these to place bets
- **Phase 4 (Website)**: Views that display comments and activity — bot system is backend-only
- **Phase 5 (Celery)**: Beat schedule to trigger bot tasks on the weekly NFL cadence

## Resolved Questions

1. **Bot profiles**: Reuse all 11 existing production bots. No new personas. Just add `nfl_team_abbr` field and assign NFL teams. Flip `active_in_nfl` post-deploy.

2. **Offseason behavior**: Bots go dormant. Existing schedule templates with `active_from`/`active_to` handle this naturally. Futures-focused bots are a post-launch feature.

3. **Discussion model timing**: Create Comment and ActivityEvent in Phase 3 since bots are the primary producers. Phase 4 just displays them.
