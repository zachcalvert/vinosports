# Test Infrastructure & Baseline Coverage

Established comprehensive test infrastructure across all four codebases in the monorepo. Created test suites from scratch for vinosports-core, hub, and EPL; fixed all broken NBA tests after the unified Django project migration.

## Results

| Suite | Tests | Status |
|-------|-------|--------|
| vinosports-core | 79 | ✅ New |
| hub | 47 | ✅ New |
| EPL | 41 | ✅ New |
| NBA | 449 | ✅ Fixed |
| **Total** | **616** | **All passing** |

**Baseline coverage: 53%** across the full codebase.

## What Was Done

### pytest-cov Configuration
Added coverage tooling to `pyproject.toml`:
- `--cov` flags for all four source trees (`vinosports`, `hub`, `nba`, `epl`)
- Coverage source paths pointing to both `/app` (league apps) and `/packages` (core package)
- Sensible omissions: migrations, test files, admin, apps.py
- Skip-covered output to reduce noise

### Docker Integration
- Volume-mounted `pyproject.toml` into the web container so pytest config stays in sync with the host
- Added `/packages/vinosports-core/src/tests` to `testpaths` so pytest discovers core tests from the `/app` working directory

### vinosports-core Test Suite (79 tests, new)
Tests for the shared backbone package that all leagues depend on:
- **core models** — `generate_short_id` (length, charset, uniqueness)
- **users** — `UserManager` (create_user, create_superuser, validation), User model (id_hash, slug generation, slug updates on display_name change)
- **betting** — `log_transaction` (credit/debit/string amounts), `UserStats` (win_rate), `mask_email`, `get_public_identity`, leaderboard (ordering, filtering, caching, `get_user_rank`)
- **bots** — `get_active_window` (default, matching, no match, date range), `is_bot_active_now`, `roll_action`, BotProfile model defaults
- **challenges** — ChallengeTemplate, Challenge target property, UserChallenge progress_percent
- **rewards** — `Reward.distribute_to_users` (credits balance, creates transaction, skips duplicates, creates balance if missing, multiple users), `RewardRule.clean` validation
- **middleware** — `BotScannerBlockMiddleware` (blocks wp-admin, .env, .php; allows normal paths), `CanonicalHostMiddleware` (www redirect, POST as 302, no redirect for canonical/debug)

### Hub Test Suite (47 tests, new)
- **models** — SiteSettings singleton (load, save forces pk=1)
- **forms** — SignupForm (valid, password mismatch/too short, duplicate email, email lowercased, promo code validation), DisplayNameForm (valid, duplicate rejected, empty returns None, own name allowed)
- **views** — HomeView, SignupView (form render, auth redirect, successful signup, promo code bonus, registration closed, invalid form), LoginView, LogoutView, AccountView (requires login, renders, update display name), StandingsView (renders, board type)
- **template tags** — format_currency (USD/GBP/EUR/rounded/unknown fallback), get_currency_symbol, currency filter, currency_rounded filter

### EPL Test Suite (41 tests, new)
- **odds engine** — `_team_strength` (top/bottom/mid), `_clamp`, `generate_match_odds` (three outcomes, positive odds, strong home lower odds, fallback no standings, clamped, even teams close)
- **settlement** — `settle_match_bets` (home win, losing bet, draw, cancelled voids, no settlement for scheduled, missing match), `settle_parlay_legs` (winning/losing/void legs, parlay won when all legs won, parlay lost when any leg lost)
- **models** — Team str, Match (slug auto-generated, contains TLAs, str with/without score, get_absolute_url), Standing (str, unique constraint), BetSlip (selection choices, str, default status)
- **views** — DashboardView, OddsBoard, MatchDetailView, LeaderboardView, LeagueTableView

### NBA Test Suite (449 tests, fixed)
All 113 failures caused by the unified Django project migration (`docs/0019-UNIFIED_DJANGO_PROJECT.md`):
- **URL prefixes** — All test URLs updated from `/odds/...` to `/nba/odds/...`, etc.
- **Hub migration** — Deleted 5 admin test classes that tested views now owned by hub
- **Context processors** — Added `request.league = "nba"` where LeagueMiddleware wasn't active
- **Patch paths** — Updated `_current_season` and other patch targets for new module locations
- **WebSocket tests** — Added `@pytest.mark.django_db`, updated assertions
- **Template names** — Updated for `featured_game`/`remaining_games` split

## Production Bug Found

While writing EPL tests, discovered that **EPL settlement code would crash at runtime**. Six source files referenced `BetSlip.Status`, `Parlay.Status`, and `ParlayLeg.Status` — but these inner classes don't exist. The abstract models in core use a standalone `BetStatus` enum, and the EPL concrete models inherit from those abstracts without defining a `Status` inner class.

Fixed in:
- `epl/betting/tasks.py`
- `epl/betting/views.py`
- `epl/bots/tasks.py`
- `epl/bots/services.py`
- `epl/bots/comment_service.py`
- `epl/betting/badges.py`

This would have caused `AttributeError` on any EPL bet settlement in production.

## Factories

Each test suite has its own `factories.py` using `factory.django.DjangoModelFactory`:

- **Core**: UserFactory, BotUserFactory, UserBalanceFactory, UserStatsFactory, BadgeFactory, ScheduleTemplateFactory, BotProfileFactory, ChallengeTemplateFactory, ChallengeFactory, UserChallengeFactory, RewardFactory
- **Hub**: UserFactory, UserBalanceFactory
- **EPL**: UserFactory, UserBalanceFactory, UserStatsFactory, TeamFactory, MatchFactory, StandingFactory, OddsFactory, BetSlipFactory, ParlayFactory, ParlayLegFactory, CommentFactory

NBA factories were already in place.

## Running Tests

```bash
# All suites
make test

# Specific suite
docker compose exec web python -m pytest hub/tests/ -q
docker compose exec web python -m pytest epl/tests/ -q
docker compose exec web python -m pytest nba/tests/ -q
docker compose exec web python -m pytest /packages/vinosports-core/src/tests/ -q
```
