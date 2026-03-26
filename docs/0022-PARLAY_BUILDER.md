# 0022: ParlayBuilder & Featured Parlays

**Date:** 2026-03-25

## Overview

A league-agnostic `ParlayBuilder` with an adapter pattern for sport-specific behavior, plus a "Featured Parlays" system that uses the builder to generate bot-curated parlay proposals displayed across the Hub, EPL, and NBA homepages. The builder consolidates parlay construction logic that was previously duplicated across EPL views, NBA views, EPL bot services, and NBA bot services.

---

## Part 1: ParlayBuilder

### The Problem

Parlay creation logic was copy-pasted across four places with subtle divergence:
- EPL views (`epl/betting/views.py`)
- NBA views (`nba/betting/views.py`)
- EPL bot tasks (`epl/bots/tasks.py`)
- NBA bot tasks (`nba/bots/tasks.py`)

Each copy handled validation, odds lookup, balance deduction, and model creation inline. Differences between leagues (odds format, markets, model fields) made a naive shared function impractical.

### Design

**Adapter pattern.** The builder lives in core and handles the shared workflow (validate → resolve → compute → place). Each league registers a `LeagueAdapter` that handles sport-specific concerns. All odds internal to the builder are **decimal** — adapters convert to/from native format only at the model boundary.

```
┌─────────────────────────────────────────────────┐
│  ParlayBuilder("epl")                           │
│    .add_leg(match_1, "HOME_WIN")                │
│    .add_leg(match_2, "DRAW")                    │
│    .place(user, stake=10)                       │
│                                                 │
│  Internal flow:                                 │
│  1. validate()  — leg count, duplicates         │
│  2. adapter.fetch_events()                      │
│  3. adapter.is_bettable() per event             │
│  4. adapter.resolve_odds() or use explicit odds │
│  5. Multiply decimal odds → combined            │
│  6. atomic { deduct balance, create Parlay,     │
│     bulk_create ParlayLegs }                    │
└─────────────────────────────────────────────────┘
```

**Fluent API.** Legs are added via chaining, then finalized with either `place()` (atomic bet placement) or `preview()` (no side effects, for featured parlays).

### Key Files

| File | Purpose |
|------|---------|
| `packages/vinosports-core/src/vinosports/betting/parlay_builder.py` | Builder class, adapter ABC, error hierarchy, data classes |
| `epl/betting/parlay_adapter.py` | EPL adapter — 1X2 decimal odds, `Min()` aggregate from `Odds` |
| `nba/betting/parlay_adapter.py` | NBA adapter — American odds, moneyline/spread/total markets |
| `epl/betting/apps.py` | Registers `EPLParlayAdapter` in `ready()` |
| `nba/betting/apps.py` | Registers `NBAParlayAdapter` in `ready()` |

### Adapter ABC

Each league implements six methods:

```python
class LeagueAdapter(ABC):
    def fetch_events(self, event_ids) -> dict[int, object]: ...
    def is_bettable(self, event) -> bool: ...
    def resolve_odds(self, event, selection, extras) -> Decimal: ...
    def create_parlay(self, user, stake, combined_decimal_odds, max_payout): ...
    def build_leg(self, parlay, event, leg, decimal_odds): ...
    def get_leg_model(self): ...
```

### Adapter Registration

Adapters register themselves during Django startup via `AppConfig.ready()`:

```python
# epl/betting/apps.py
class EplBettingConfig(AppConfig):
    def ready(self):
        from vinosports.betting.parlay_builder import register_adapter
        from epl.betting.parlay_adapter import EPLParlayAdapter
        register_adapter("epl", EPLParlayAdapter)
```

### League Differences

| | EPL | NBA |
|---|---|---|
| Odds format (native) | Decimal (1.50, 2.00) | American (-150, +130) |
| Odds format (internal) | Decimal (no conversion) | Decimal (convert at boundary) |
| Markets | 1X2 only (HOME_WIN, DRAW, AWAY_WIN) | Moneyline, Spread, Total |
| Odds resolution | `Min()` across bookmakers | `Max()` (least negative American) |
| Extra fields | None | `market`, `line` |

### Error Hierarchy

```python
ParlayError                     # Base
├── ParlayValidationError       # Leg count, duplicates, missing events/odds
└── InsufficientBalanceError    # Balance < stake
```

`ParlayValidationError` carries a list of error strings (`e.errors`) so multiple issues can be surfaced at once.

### Data Classes

| Class | Role |
|-------|------|
| `LegData` | Input: `event_id`, `selection`, optional `odds`, optional `extras` dict |
| `ResolvedLeg` | After validation: original `LegData` + fetched `event` + `decimal_odds` |
| `ParlayPreview` | Output of `preview()`: legs, combined odds, potential payout, league |

### Usage

```python
# Place a real bet (deducts balance, creates models)
parlay = (
    ParlayBuilder("epl")
    .add_leg(match_1.pk, "HOME_WIN")
    .add_leg(match_2.pk, "DRAW")
    .add_leg(match_3.pk, "AWAY_WIN")
    .place(user, stake=Decimal("10.00"))
)

# Preview without side effects (for featured parlays)
preview = (
    ParlayBuilder("nba")
    .add_leg(game_1.pk, "HOME", market="MONEYLINE")
    .add_leg(game_2.pk, "AWAY", market="MONEYLINE")
    .preview(stake=Decimal("10.00"))
)
# preview.combined_odds, preview.potential_payout, preview.legs

# Explicit odds (skip adapter resolution)
builder = ParlayBuilder("nba")
builder.add_leg(game.pk, "HOME", odds=Decimal("1.67"), market="MONEYLINE")
```

### Test Coverage

- `epl/tests/test_parlay_builder.py` — 23 tests across 3 classes (validation, preview, place)
- `nba/tests/test_parlay_builder.py` — 18 tests across 3 classes
- Tests use factories, mock nothing except database state
- Covers: leg count validation, duplicate events, missing events, unbettable events, balance deduction, payout cap, odds resolution, American↔decimal conversion rounding

---

## Part 2: Featured Parlays

### The Concept

Bots automatically curate parlay proposals ("sponsored picks") that appear on league dashboards and the Hub homepage. These are **proposals only** — no balance is deducted, no real bet is placed. They're generated using `ParlayBuilder.preview()` and persisted as denormalized snapshots.

### Data Model

Lives in core since it's shared across leagues:

```
packages/vinosports-core/src/vinosports/betting/featured.py
```

**FeaturedParlay**

| Field | Type | Description |
|-------|------|-------------|
| `league` | CharField(10) | `"epl"` or `"nba"` |
| `sponsor` | FK → User | Bot user who sponsors the pick |
| `title` | CharField(120) | Generated by Claude (e.g. "Weekend Chalk") |
| `description` | TextField | One-liner generated by Claude |
| `status` | CharField(10) | `ACTIVE`, `EXPIRED`, or `CANCELLED` |
| `expires_at` | DateTimeField | Auto-expire after last event kicks off |
| `combined_odds` | Decimal(12,2) | Snapshot at creation |
| `potential_payout` | Decimal(12,2) | At `reference_stake` |
| `reference_stake` | Decimal(10,2) | Default $10.00 |

Indexed on `(league, status)` for the common homepage query.

**FeaturedParlayLeg**

| Field | Type | Description |
|-------|------|-------------|
| `featured_parlay` | FK → FeaturedParlay | Parent |
| `event_id` | IntegerField | PK of match/game (not a FK — keeps this in core) |
| `event_label` | CharField(200) | e.g. "Arsenal vs Chelsea" (denormalized) |
| `selection` | CharField(20) | Raw value: `HOME_WIN`, `OVER`, etc. |
| `selection_label` | CharField(60) | Human-readable: "Home Win", "Over 222.5" |
| `odds_snapshot` | Decimal(10,2) | Decimal odds at creation |
| `extras_json` | JSONField | League-specific: `{"market": "SPREAD", "line": -3.5}` |

**Why denormalized?** Legs store human-readable labels and odds snapshots rather than FKs to league-specific models. This means: (1) no cross-app FK dependency from core to EPL/NBA, (2) data remains readable after events finish or odds change, (3) the card template can render without any extra queries.

### Generation Pipeline

```
Celery Beat → generate_featured_parlays() → ParlayBuilder.preview() → Claude API → FeaturedParlay + legs
```

**EPL** (`epl/bots/tasks.py`):
- Runs weekly, Friday 8am
- Fetches up to 20 upcoming matches with odds
- Builds 2-3 themed parlays:
  - **Favorites**: lowest odds selections (chalk picks)
  - **Underdogs**: highest odds selections
  - **Value**: draws in the 2.5–4.0 odds range
- Expires 2 hours after the last match kicks off

**NBA** (`nba/bots/tasks.py`):
- Runs daily at 10am
- Fetches today's scheduled games (ET timezone-aware)
- Builds 1-2 themed parlays:
  - **Favorites**: home moneyline for the shortest-priced favorites
  - **Value**: spread picks where the line is tight (±5)
- Expires 4 hours after the last tip-off

**Expiration** (`vinosports.betting.tasks`):
- Runs every 30 minutes
- Sets ACTIVE → EXPIRED where `expires_at < now()`

### Claude Copy Generation

```
packages/vinosports-core/src/vinosports/betting/featured_utils.py
```

Each themed parlay gets a title and description from Claude Haiku:

```python
generate_parlay_copy(
    legs_summary=[{"event": "Arsenal vs Chelsea", "selection": "Home Win", "odds": "2.10"}, ...],
    league="epl",
    theme="favorites"
) → {"title": "Weekend Chalk", "description": "Riding the favorites across Saturday's slate."}
```

- Model: `claude-haiku-4-5-20251001` (cheap, fast)
- Temperature: 0.9 (creative copy)
- Max tokens: 150
- System prompt enforces JSON output, character limits, tone matching per theme
- **Graceful fallback**: if `ANTHROPIC_API_KEY` is missing or the call fails, returns a hardcoded title/description per league+theme combination

### UI

Featured parlays appear in three places, rendered via a **shared card partial**:

```
packages/vinosports-core/src/vinosports/templates/vinosports/betting/featured_parlay_card.html
```

| Location | Query | Max Cards |
|----------|-------|-----------|
| Hub homepage (`hub/views.py`) | All leagues, ACTIVE status | 4 |
| EPL dashboard (`epl/matches/views.py`) | `league="epl"`, ACTIVE | 2 |
| NBA dashboard (`nba/website/views.py`) | `league="nba"`, ACTIVE | 2 |

Card layout:
1. **Header**: Sponsor bot avatar + name, league badge
2. **Title + description**: Claude-generated copy
3. **Legs list**: Event label, selection label, odds per leg
4. **Footer**: Combined odds + potential payout at reference stake

### Celery Beat Schedule

```python
# config/settings.py
CELERY_BEAT_SCHEDULE = {
    ...
    "epl-generate-featured-parlays-weekly": {
        "task": "epl.bots.tasks.generate_featured_parlays",
        "schedule": crontab(day_of_week="friday", hour=8, minute=0),
    },
    "nba-generate-featured-parlays-daily": {
        "task": "nba.bots.tasks.generate_featured_parlays",
        "schedule": crontab(hour=10, minute=0),
    },
    "expire-featured-parlays-30m": {
        "task": "vinosports.betting.tasks.expire_featured_parlays",
        "schedule": crontab(minute="*/30"),
    },
}
```

### Admin

`FeaturedParlay` is registered in `epl/betting/admin.py` (following the existing deduplication convention — shared core models go in EPL admin only) with `FeaturedParlayLegInline`.

### Test Coverage

- `epl/tests/test_featured_parlays.py` — 11 tests (model creation, expiration task, Claude copy generation, EPL generation task)
- `nba/tests/test_featured_parlays.py` — 4 tests (NBA generation task with mocked `today_et` and `generate_parlay_copy`)
- All tests mock the Claude API and use factories

---

## Future Considerations

- **User-created featured parlays.** The `sponsor` FK is on User, not BotProfile, so real users could eventually create and share their own featured parlays
- **"Tail this parlay" action.** Add a CTA button that pre-fills ParlayBuilder with the featured parlay's legs so a user can place it with one click
- **Performance tracking.** After events settle, grade featured parlays (won/lost) and display a bot's pick accuracy over time
- **Additional themes.** Per-league strategies can be expanded (e.g., NBA player props, EPL both-teams-to-score) as new markets are added
