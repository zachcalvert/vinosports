# 0016: NBA Challenge Templates

**Date:** 2026-03-24

## Goal

Create NBA-specific challenge template definitions and incorporate them into the existing `seed_challenge_templates` management command. The EPL app already has 14 templates (8 daily, 6 weekly) that work well — NBA needs its own set that reflects basketball-specific language and thresholds while using the same underlying `CriteriaType` system.

## Current State

- `ChallengeTemplate` is a concrete model in `vinosports.challenges` (core). One shared table across all leagues.
- EPL's seed command lives at `apps/epl/website/management/commands/seed_challenge_templates.py` and defines 14 templates inline.
- NBA has no seed command and no templates. The challenge rotation tasks (`website.challenge_tasks`) are wired up in Celery beat but will always skip because there are no templates to pick from.
- The challenge system is league-scoped — each league's rotation tasks create `Challenge` instances independently from the shared `ChallengeTemplate` pool.

## Design Decisions

### Shared vs. separate template pools

Templates have a `challenge_type` (DAILY/WEEKLY) and `criteria_type` (BET_COUNT, WIN_STREAK, etc.) but no league field. Both EPL and NBA rotation tasks query the same `ChallengeTemplate` table. This means:

- **Option A: Shared pool** — Both leagues draw from the same templates. A "Place 3 bets today" template works for either sport. Simple, but limits sport-specific flavor in titles/descriptions/icons.
- **Option B: Separate pools with a league field** — Add a `league` field (or tag) to `ChallengeTemplate` so each league only sees its own. More work, requires a migration.
- **Option C: Sport-flavored duplicates** — Create NBA-themed templates alongside EPL ones. Both exist in the same table. Each league's rotation tasks pick from all active templates (the criteria work identically across sports). Titles like "Triple Double" vs "Hat Trick" give personality without schema changes.

**Decision: Option C.** The criteria types are sport-agnostic (bet count, win streak, total staked, etc.). NBA templates just get basketball-flavored names and descriptions. If we later want strict separation, we can add a `league` tag and filter — but for now, having a shared pool with sport-flavored names works fine since each league's `Challenge` instances are created independently by their own Celery tasks.

### Template definitions

NBA templates should mirror the EPL set's structure (mix of easy daily challenges and harder weekly ones) but with basketball language:

#### Daily Challenges (8)

| Slug | Title | Description | Criteria | Target | Reward |
|------|-------|-------------|----------|--------|--------|
| `nba-daily-bet-3` | Triple Double | Place 3 bets today | BET_COUNT | 3 | 50 |
| `nba-daily-bet-5` | Starting Five | Place 5 bets today | BET_COUNT | 5 | 100 |
| `nba-daily-underdog` | Cinderella Story | Bet on an underdog (+150 or longer) | BET_ON_UNDERDOG | 1 | 75 |
| `nba-daily-win-2` | And One | Win 2 bets today | WIN_COUNT | 2 | 100 |
| `nba-daily-parlay` | Alley-Oop | Place a parlay bet | PARLAY_PLACED | 1 | 75 |
| `nba-daily-stake-500` | Shot Clock | Stake 500+ credits today | TOTAL_STAKED | 500 | 100 |
| `nba-daily-correct-3` | Sixth Man | Get 3 correct predictions today | CORRECT_PREDICTIONS | 3 | 150 |
| `nba-daily-win-1` | Free Throw | Win a bet today | WIN_COUNT | 1 | 50 |

#### Weekly Challenges (6)

| Slug | Title | Description | Criteria | Target | Reward |
|------|-------|-------------|----------|--------|--------|
| `nba-weekly-streak-3` | On Fire | Win 3 bets in a row this week | WIN_STREAK | 3 | 250 |
| `nba-weekly-bet-all` | Full Court Press | Bet on every game today | BET_ALL_MATCHES | 10 | 300 |
| `nba-weekly-parlay-win` | Buzzer Beater | Win a parlay this week | PARLAY_WON | 1 | 500 |
| `nba-weekly-win-5` | Playoff Mode | Win 5 bets this week | WIN_COUNT | 5 | 300 |
| `nba-weekly-correct-5` | Floor General | Get 5 correct predictions this week | CORRECT_PREDICTIONS | 5 | 350 |
| `nba-weekly-stake-2000` | Max Contract | Stake 2000+ credits this week | TOTAL_STAKED | 2000 | 250 |

**Notes:**
- NBA underdog threshold uses American odds format in the description (+150) but the `odds_min` param should store the decimal equivalent (`2.50`) since that's what the engine compares against.
- Icons use Phosphor icon names (basketball, fire, trophy, etc.).
- `BET_ALL_MATCHES` target of 10 is a placeholder — the weekly rotation task dynamically updates this to the actual game count for the day/week.

### Seed command changes

The EPL seed command at `apps/epl/website/management/commands/seed_challenge_templates.py` currently defines templates inline and seeds them via `update_or_create`. Two options:

- **Option A:** Create a separate `seed_challenge_templates` command in NBA's website app with NBA definitions.
- **Option B:** Move the definitions into a shared location and have one command seed both sets, or have each league's command seed only its own.

**Decision: Option A.** Each league keeps its own seed command with its own definitions. The EPL command already works. NBA gets a parallel command at `apps/nba/website/management/commands/seed_challenge_templates.py`. This matches the pattern used for other seed commands (`seed_epl` vs `seed_nba`). The `make seed` target can be updated to run both.

## Implementation Steps

1. Create `apps/nba/website/management/commands/` directory structure (add `__init__.py` files)
2. Create `seed_challenge_templates.py` with the NBA template definitions above
3. Test: `docker compose exec nba-web python manage.py seed_challenge_templates`
4. Verify rotation: `docker compose exec nba-web python manage.py shell -c "from website.challenge_tasks import rotate_daily_challenges; print(rotate_daily_challenges())"`
5. Update `Makefile` seed target to include NBA challenge templates

## Validation

- 14 NBA templates created in DB (8 daily, 6 weekly)
- `rotate_daily_challenges` picks from NBA templates and creates `Challenge` instances (when games exist)
- No collision with EPL templates (distinct slugs with `nba-` prefix)
- Existing EPL templates unaffected
