# 0012 — NBA Test Coverage Status & Path to 80%

## Current State

**165 tests passing**, **44.9% coverage** (threshold: 44%).

Implemented 2026-03-23 following the plan in `0010-NBA_TEST_SUITE.md`.

### Infrastructure

| Item | Status |
|------|--------|
| `pytest-django`, `pytest-cov`, `factory-boy` | Installed in Dockerfile |
| `pyproject.toml` coverage config | `fail_under = 44`, HTML + terminal reports |
| `conftest.py` | `celery_eager` autouse fixture, `api_client` fixture |
| `tests/factories.py` | 14 factories covering all NBA models |
| `make test-nba` | Runs full suite with coverage |
| `make coverage-nba` | Same + HTML report in `htmlcov/` |
| `.gitignore` | `htmlcov/`, `.coverage` already covered |

### Test Files

| File | Tests | What it covers |
|------|-------|----------------|
| `test_models.py` | 21 | `__str__`, properties, `calculate_payout`, unique constraints |
| `test_schedule.py` | 12 | `get_active_window`, `is_bot_active_now`, `roll_action`, date ranges |
| `test_settlement.py` | 19 | `_evaluate_bet_outcome` (all markets), odds conversion, `settle_game_bets`, parlays, `grant_bailout` |
| `test_strategies.py` | 28 | All 9 strategies, stake calculation, `STRATEGY_MAP` completeness |
| `test_services.py` | 8 | `place_bot_bets`, single/parlay placement, balance deduction, payout cap |
| `test_tasks.py` | 10 | `run_bot_strategies` orchestration, `execute_bot_strategy` edge cases |
| `test_discussion_tasks.py` | 11 | Pregame/postgame comment generation, Claude API mocking, cap enforcement |
| `test_odds_engine.py` | 22 | `_parse_record`, `_team_strength`, `_win_probability`, odds generation |
| **Total** | **131** | *34 additional tests are from non-DB strategy/schedule/odds tests* |

### Module-Level Coverage

**Well-covered (core business logic):**

| Module | Coverage | Notes |
|--------|----------|-------|
| `games/models.py` | 99% | Only `GameStats.__str__` uncovered |
| `betting/models.py` | 98% | `ParlayLeg.__str__` uncovered |
| `betting/odds_engine.py` | 95% | `_parse_record` fallback edge cases |
| `betting/settlement.py` | 87% | Parlay void+reduced branches, `_check_bankruptcy` no-balance path |
| `betting/balance.py` | 100% | Fully covered |
| `betting/stats.py` | 100% | Fully covered |
| `bots/strategies.py` | 93% | ChaosAgent fallback branches |
| `bots/services.py` | 95% | ActivityEvent message formatting edge case |
| `bots/tasks.py` | 93% | Low-balance skip path, unknown strategy |
| `bots/schedule.py` | 96% | `timezone.localtime()` default path |
| `discussions/tasks.py` | 88% | `_generate_comment_body` (mocked), some inner branches |
| `bots/models.py` | 94% | `__str__` methods |

**Uncovered (0% — not yet tested):**

| Module | Lines | Category |
|--------|-------|----------|
| `website/views.py` | 121 | Views |
| `games/services.py` | 147 | Data ingestion (API clients) |
| `betting/services.py` | 78 | User-facing bet placement |
| `betting/views.py` | 127 | Views |
| `challenges/tasks.py` | 76 | Challenge rotation |
| `games/tasks.py` | 46 | Celery data fetch tasks |
| `betting/tasks.py` | 70 | Celery betting tasks |
| `betting/context_processors.py` | 47 | Template context |
| `betting/forms.py` | 31 | Django forms |
| `games/management/commands/seed_nba.py` | 69 | Seed command |
| `bots/management/commands/seed_bots.py` | 52 | Seed command |
| `activity/tasks.py` | 27 | Broadcast/cleanup tasks |
| `website/forms.py` | 22 | Forms |
| Other views/urls/routing | ~80 | Thin glue |

---

## Path to 80%

Current: **~45% (1,016 lines covered / 2,263 total)**
Target: **80% (1,810 lines covered)**
Gap: **~794 lines** to cover.

### Phase 1 → 55%: Low-Hanging Fruit (no mocking needed)

**Est. +220 lines covered**

| New test file | Target module | Lines to cover | Approach |
|---------------|---------------|----------------|----------|
| `test_betting_services.py` | `betting/services.py` (78 lines) | ~60 | Test `place_bet()`, `place_parlay()` for human users — same pattern as bot services but through the user-facing API |
| `test_betting_tasks.py` | `betting/tasks.py` (70 lines) | ~50 | Test `generate_odds` task (calls `generate_all_upcoming_odds`), `settle_pending_bets` task (calls `settle_game_bets` for FINAL games) |
| `test_context_processors.py` | `betting/context_processors.py` (47 lines) | ~35 | Use `RequestFactory` to test parlay slip, balance, bankruptcy context |
| `test_forms.py` | `betting/forms.py` + `website/forms.py` (53 lines) | ~40 | Form validation tests (valid/invalid data) |
| `test_signals.py` | `betting/signals.py` (35 lines) | ~25 | Test signup bonus creation, balance initialization |
| Expand `test_settlement.py` | `betting/settlement.py` remaining (21 lines) | ~15 | Cover parlay void-all-legs, reduced-odds, `_check_bankruptcy` no-balance edge |

**Ratchet `fail_under` to 55 after this phase.**

### Phase 2 → 65%: Views & Data Ingestion

**Est. +230 lines covered**

| New test file | Target module | Lines to cover | Approach |
|---------------|---------------|----------------|----------|
| `test_views.py` | `website/views.py` (121 lines) | ~80 | Use `api_client` fixture. Test dashboard, leaderboard, game detail. Assert status codes + template names |
| `test_betting_views.py` | `betting/views.py` (127 lines) | ~70 | Test bet placement form POST, parlay slip HTMX partials, odds display |
| `test_games_services.py` | `games/services.py` (147 lines) | ~50 | Mock `httpx` responses. Test `fetch_teams`, `fetch_schedule`, `sync_standings` parsing |
| `test_activity_tasks.py` | `activity/tasks.py` (27 lines) | ~20 | Test `broadcast_activity_event`, `cleanup_old_events` |
| `test_discussion_views.py` | `discussions/views.py` (30 lines) | ~20 | Test comment creation POST, game thread rendering |

**Ratchet `fail_under` to 65 after this phase.**

### Phase 3 → 75%: Celery Tasks & Management Commands

**Est. +180 lines covered**

| New test file | Target module | Lines to cover | Approach |
|---------------|---------------|----------------|----------|
| `test_games_tasks.py` | `games/tasks.py` (46 lines) | ~35 | Mock service functions, test task dispatch and error handling |
| `test_challenges_tasks.py` | `challenges/tasks.py` (76 lines) | ~50 | Test `rotate_daily_challenges`, `rotate_weekly`, `expire_challenges` |
| `test_seed_commands.py` | Both seed commands (121 lines) | ~60 | Use `--dry-run` or mock API, verify objects created |
| `test_templatetags.py` | `currency_tags.py` (26 lines) | ~20 | Test `format_currency`, `format_odds` template filters |
| `test_theme.py` | `website/theme.py` (12 lines) | ~10 | Test theme resolution |

**Ratchet `fail_under` to 75 after this phase.**

### Phase 4 → 80%: WebSocket & Edge Cases

**Est. +160 lines covered**

| New test file | Target module | Lines to cover | Approach |
|---------------|---------------|----------------|----------|
| `test_consumers.py` | `games/consumers.py` + `activity/consumers.py` (34 lines) | ~25 | Use `channels.testing.WebsocketCommunicator` |
| `test_odds_client.py` | `betting/odds_engine.py` OddsClient (87 lines) | ~50 | Mock `httpx`, test `sync_odds` parsing, team alias resolution |
| `test_admin.py` | All `admin.py` files (98 lines) | ~50 | Test admin list/detail pages render, custom actions |
| Expand existing tests | Various edge cases | ~35 | ChaosAgent fallbacks, BotComment edge cases, parlay reduced-odds path |

**Ratchet `fail_under` to 80 after this phase.**

---

## Priorities

1. **Phase 1 first** — it covers the most important untested business logic and requires no new test patterns
2. **Phase 2 next** — views are the largest untested surface area and catch regressions in template rendering
3. **Phases 3–4 can be interleaved** — lower priority, but needed for the 80% target

## Guidelines

- Test behavior, not implementation
- Use factories from `tests/factories.py`, never JSON fixtures
- Mock external APIs (Claude, sportsdata.io, the-odds-api.com) — never make real HTTP calls
- Keep Celery eager via the `celery_eager` autouse fixture
- Each phase should raise `fail_under` to lock in gains
