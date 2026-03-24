# Bot Schedule Templates

## Overview

Bot activity in the NBA app is controlled by **schedule templates** — reusable configurations that define *when* a bot is "online," *how likely* it is to bet or comment per hourly tick, and *under what date conditions* it's active at all.

Before schedule templates, all bots fired at the same fixed times (betting once at 2pm, comments at 2/4/6pm). Every active bot acted together. Templates break that uniformity: each bot now has its own behavioral rhythm.

---

## How It Works

The Celery beat schedule fires bot tasks **hourly** rather than at fixed times:

- `:05` — `bots.tasks.run_bot_strategies` (betting dispatch)
- `:15` — `discussions.tasks.generate_pregame_comments`
- `:30` — `discussions.tasks.generate_postgame_comments`

On each hourly tick, each bot is checked against its schedule template. If no window matches the current day+hour, the bot is skipped entirely. If a window does match, the bot rolls a probability die to decide whether to act.

---

## The Data Model

### `AbstractScheduleTemplate` (core package)

Defined in `packages/vinosports-core/src/vinosports/bots/models.py`. League apps extend this into a concrete model.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField | Human-readable name |
| `slug` | SlugField | Unique identifier used for seeding and lookup |
| `description` | TextField | Explanation of the behavioral archetype |
| `windows` | JSONField | List of activity window objects (see below) |
| `active_from` | DateField (nullable) | Template inactive before this date |
| `active_to` | DateField (nullable) | Template inactive after this date |

### `ScheduleTemplate` (NBA app)

Defined in `apps/nba/bots/models.py`. Extends `AbstractScheduleTemplate` with `app_label = "nba_bots"`.

### `BotProfile.schedule_template` (FK)

A nullable FK from `BotProfile` to `ScheduleTemplate`. Bots with no template are **always-on** — they're eligible every hourly tick, using default probabilities.

---

## Activity Windows

The `windows` field is a JSON list. Each entry defines a time slot and the behavior within it:

```json
[
  {
    "days": [0, 1, 2, 3, 4, 5, 6],
    "hours": [8, 9],
    "bet_probability": 0.4,
    "comment_probability": 0.7,
    "max_bets": 1,
    "max_comments": 1
  },
  {
    "days": [0, 1, 2, 3, 4, 5, 6],
    "hours": [17, 18],
    "bet_probability": 0.4,
    "comment_probability": 0.7,
    "max_bets": 1,
    "max_comments": 1
  }
]
```

| Field | Description |
|-------|-------------|
| `days` | List of weekday integers: `0=Mon`, `1=Tue`, ..., `6=Sun` |
| `hours` | List of hours (ET) when the bot is active, 0–23 |
| `bet_probability` | Probability (0.0–1.0) that the bot places bets this tick |
| `comment_probability` | Probability (0.0–1.0) that the bot comments this tick |
| `max_bets` | Max bets allowed per window activation (also capped by `BotProfile.max_daily_bets`) |
| `max_comments` | Max comments allowed across today's games |

A bot is active if the **current day** appears in `days` AND the **current hour** appears in `hours`. A template can have multiple windows — the first matching window is used.

---

## Date Range: `active_from` / `active_to`

These optional fields gate the entire template by calendar date. If `active_from` is set and today is before it, the bot is inactive regardless of windows. Same for `active_to`.

Primary use case: the **Postseason Fan** template is set to the NBA playoff window. Update `active_from` / `active_to` each season in the admin or seed command.

---

## Schedule Resolution (`apps/nba/bots/schedule.py`)

Three helpers drive the logic:

```python
get_active_window(bot_profile, now=None) -> dict | None
```
Returns the first matching window dict for the given time, or `None` if inactive. If the bot has no template, returns `DEFAULT_WINDOW` (always-on).

```python
is_bot_active_now(bot_profile, now=None) -> bool
```
Returns `True` if `get_active_window` returns a non-None result.

```python
roll_action(probability) -> bool
```
Returns `True` with the given probability. Used for both betting and commenting dice rolls.

---

## The Six Templates (NBA)

| Slug | Name | Pattern | Date Range |
|------|------|---------|------------|
| `nine-to-five-grinder` | 9 to 5 Grinder | 8–9am + 5–6pm, all days | None |
| `heavy-bettor-lurker` | Heavy Bettor / Lurker | 11am–11pm all days, bet=0.9, comment=0.03 | None |
| `heavy-commenter-light-bettor` | Heavy Commenter / Light Bettor | 10am–10pm all days, bet=0.1, comment=0.7 | None |
| `postseason-fan` | Postseason Fan | 12pm–11pm all days, moderate probabilities | Playoff window only |
| `night-owl` | Night Owl | 8pm–1am all days | None |
| `weekend-warrior` | Weekend Warrior | Fri–Sun 12pm–10pm | None |

Bots without a template (e.g., Chaos Cathy) are always eligible with default probabilities (`bet=0.5`, `comment=0.5`).

---

## Seeding Templates

Templates are created by the `seed_bots` management command:

```bash
python manage.py seed_bots
```

Template definitions live in `SCHEDULE_TEMPLATES` at the top of `apps/nba/bots/management/commands/seed_bots.py`. Each persona in `apps/nba/bots/personas.py` has a `schedule_template_slug` field that maps it to a template (or `None` for always-on).

The command is **idempotent** — running it again updates existing templates and bot assignments without duplicating anything.

---

## Porting to EPL

The abstract base lives in core, so EPL can adopt the same system with minimal work:

1. In `apps/epl/bots/models.py`, add a concrete `ScheduleTemplate` extending `AbstractScheduleTemplate` with `app_label = "epl_bots"`.
2. Add `schedule_template` FK to `BotProfile` in the EPL app.
3. Create `apps/epl/bots/schedule.py` — copy from the NBA version, it's sport-agnostic.
4. Refactor `apps/epl/bots/tasks.py` (`run_bot_strategies`, `generate_prematch_comments`, `generate_postmatch_comments`) to call `get_active_window()` and `roll_action()` per bot.
5. Update the EPL Celery beat schedule to hourly.
6. Define EPL-appropriate templates in `seed_bots` — the window schema is identical, but EPL match days are Thu–Mon rather than every day, so templates should reflect that.
7. Generate and run migrations.

The core window schema (`days`, `hours`, `bet_probability`, `comment_probability`, `max_bets`, `max_comments`) is sport-neutral and works as-is for EPL.
