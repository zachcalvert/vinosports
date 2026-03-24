# 0010 — NBA Test Suite with Coverage Reporting

## Goal

Stand up a pytest test suite for `apps/nba/` with coverage reporting, using factory-based fixtures. Pattern-match off the existing project conventions (pytest config in `pyproject.toml`, Docker-based test runner via `make test-nba`).

---

## 1. Dependencies

Add to the NBA container (and/or `vinosports-core` dev extras):

- `pytest-django` — Django test integration
- `pytest-cov` — coverage plugin (wraps `coverage.py`)
- `factory-boy` — model factories

Install in the Dockerfile or as dev dependencies in `pyproject.toml`.

## 2. Pytest & Coverage Config

**`apps/nba/pyproject.toml`** — extend existing config:

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
python_files = ["tests.py", "test_*.py"]
addopts = "--cov=. --cov-report=term-missing --cov-report=html:htmlcov --cov-config=pyproject.toml"

[tool.coverage.run]
source = ["."]
omit = [
    "*/migrations/*",
    "*/tests/*",
    "config/*",
    "manage.py",
    "static/*",
    "templates/*",
]

[tool.coverage.report]
fail_under = 50
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ ==",
]
```

Start with `fail_under = 50` and ratchet up as coverage grows.

## 3. conftest.py

**`apps/nba/conftest.py`** — shared fixtures:

```python
import pytest
from django.test import override_settings

# Force sync Celery in tests
@pytest.fixture(autouse=True)
def celery_eager(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

@pytest.fixture
def api_client():
    from django.test import Client
    return Client()
```

## 4. Factories

**`apps/nba/tests/factories.py`**:

| Factory | Model | Key defaults |
|---------|-------|-------------|
| `UserFactory` | `User` | `email=LazyAttribute`, `display_name=Faker`, `is_bot=False` |
| `BotUserFactory` | `User` | inherits UserFactory, `is_bot=True` |
| `TeamFactory` | `games.Team` | `name=Sequence`, `abbreviation=Sequence`, `conference="East"` |
| `GameFactory` | `games.Game` | `home_team=SubFactory(TeamFactory)`, `away_team=SubFactory(TeamFactory)`, `status=SCHEDULED`, `game_date=today` |
| `OddsFactory` | `games.Odds` | `game=SubFactory(GameFactory)`, sensible American odds defaults |
| `BotProfileFactory` | `bots.BotProfile` | `user=SubFactory(BotUserFactory)`, `strategy_type=FRONTRUNNER`, `is_active=True` |
| `ScheduleTemplateFactory` | `bots.ScheduleTemplate` | `name=Sequence`, default 24/7 window |
| `BetSlipFactory` | `betting.BetSlip` | `user=SubFactory(UserFactory)`, `game=SubFactory(GameFactory)`, `market=MONEYLINE` |
| `CommentFactory` | `discussions.Comment` | `user=SubFactory(UserFactory)`, `game=SubFactory(GameFactory)`, `body=Faker` |
| `UserBalanceFactory` | `UserBalance` | `user=SubFactory(UserFactory)`, `balance=1000.00` |

## 5. Test File Structure

```
apps/nba/
├── conftest.py
├── tests/
│   ├── __init__.py
│   ├── factories.py
│   ├── test_models.py          # Model validation, constraints, properties
│   ├── test_strategies.py      # Strategy.pick_bets() for each of 9 types
│   ├── test_services.py        # place_bot_bets(), balance deduction, parlay placement
│   ├── test_tasks.py           # run_bot_strategies(), execute_bot_strategy() orchestration
│   ├── test_schedule.py        # get_active_window(), is_bot_active_now(), roll_action()
│   ├── test_settlement.py      # Bet settlement logic (if exists)
│   └── test_discussion_tasks.py  # generate_pregame_comments(), generate_postgame_comments()
```

## 6. Priority Test Cases

### 6a. Models (`test_models.py`)
- Game `.is_live`, `.is_final`, `.winner` properties
- BotComment unique constraint `(user, game, trigger_type)`
- BetSlip / Parlay field validation
- Team string representation

### 6b. Strategies (`test_strategies.py`)
- Each of the 9 strategies returns correct `BetInstruction` types
- Stake calculation respects `risk_multiplier` and balance caps
- ParlayStrategy returns `ParlayInstruction` with ≥2 legs
- HomerStrategy only picks `favorite_team` games
- ChaosAgentStrategy doesn't crash on random inputs
- Strategies return empty list when no eligible games

### 6c. Services (`test_services.py`)
- `place_bot_bets` deducts balance via `log_transaction`
- Insufficient balance skips bet (doesn't raise)
- Parlay combined odds calculated correctly
- Parlay max payout cap ($10,000) enforced
- ActivityEvent created for each placed bet

### 6d. Tasks (`test_tasks.py`)
- `run_bot_strategies` skips inactive bots
- `run_bot_strategies` respects schedule windows
- `execute_bot_strategy` grants bailout when bankrupt
- `execute_bot_strategy` respects daily bet limit
- Mock `strategy.pick_bets()` to avoid coupling

### 6e. Schedule (`test_schedule.py`)
- `get_active_window` returns correct window for day/hour
- Returns `DEFAULT_WINDOW` for bots without template
- Date range filtering (`active_from` / `active_to`)
- `roll_action(0.0)` always False, `roll_action(1.0)` always True

### 6f. Discussion Tasks (`test_discussion_tasks.py`)
- Mock Claude API (`anthropic.Anthropic`) to avoid real calls
- Pregame: creates comments for SCHEDULED games
- Postgame: creates comments for FINAL games
- Skips bots that already commented on a game
- Respects `max_comments` window cap

## 7. Makefile Updates

Already defined — no changes needed:
```makefile
test-nba:
    docker compose run --rm nba-web python -m pytest
```

Optionally add a coverage-only target:
```makefile
coverage-nba:
    docker compose run --rm nba-web python -m pytest --cov-report=html:htmlcov
```

## 8. .gitignore

Add `htmlcov/` and `.coverage` to root `.gitignore` (if not already present).

## 9. Implementation Order

1. Add `pytest-django`, `pytest-cov`, `factory-boy` to NBA container deps
2. Extend `pyproject.toml` with coverage config
3. Create `conftest.py` and `tests/factories.py`
4. Write `test_models.py` and `test_schedule.py` (no mocking needed, fast)
5. Write `test_strategies.py` (pure logic, no DB)
6. Write `test_services.py` and `test_tasks.py` (DB + mocked Celery)
7. Write `test_discussion_tasks.py` (mock Claude API)
8. Verify `make test-nba` passes with coverage report
9. Ratchet `fail_under` as coverage grows
