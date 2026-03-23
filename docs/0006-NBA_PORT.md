# 0006: NBA Port Complete

**Date:** 2026-03-23

## What Was Done

Ported the NBA betting simulation from the standalone `nba-bets` repo into `apps/nba/` within the vinosports monorepo. The skeleton (models, migrations, Docker services) was already in place from the scaffolding phase. This port added all business logic, views, templates, tasks, and management commands needed to run a fully functional NBA site.

## Source Material

- **Original repo:** `/Users/zach/labs/nba-bets` (standalone Django project)
- **Reference implementation:** `apps/epl/` (already ported, used as pattern guide)
- **Shared package:** `packages/vinosports-core/` (concrete + abstract models)

## What Was Ported (7 phases)

### Phase 1: Services & Settlement
- `games/services.py` — `NBADataClient` wrapping SportsData.io v3 API, plus `sync_teams`, `sync_games`, `sync_standings`, `sync_live_scores`
- `betting/services.py` — `OddsClient` wrapping The Odds API v4, plus `sync_odds` with team name aliasing
- `betting/settlement.py` — Full settlement engine: moneyline, spread, total evaluation; parlay resolution (WON/LOST/VOID/mixed); bankruptcy detection; bailout granting
- `betting/balance.py` — Compatibility wrapper around vinosports-core's `log_transaction` (core takes locked `UserBalance`, original nba-bets took `User`)
- `betting/stats.py` — `record_bet_result()` for atomic UserStats updates
- `bots/strategies.py` — 9 strategies: Frontrunner, Underdog, SpreadShark, Parlay, TotalGuru, ChaosAgent, AllInAlice, Homer, AntiHomer
- `bots/services.py` — `place_bot_bets()` translating strategy output into real BetSlips/Parlays
- `bots/personas.py` — 35 bot personas extracted from seed command (homer bots for 20+ teams, archetype bots)
- Model change: added `ANTI_HOMER` to BotProfile.StrategyType, added `risk_multiplier` and `max_daily_bets` fields

### Phase 2: Settings & Celery Tasks
- Updated `config/settings.py`: added `django_htmx`, `BotScannerBlockMiddleware`, `HtmxMiddleware`, context processors, `CELERY_BEAT_SCHEDULE` (NBA-specific timing: daily games, 7pm-1am ET live window), API key settings, auth URLs
- `games/tasks.py` — fetch_teams, fetch_schedule, fetch_standings, fetch_live_scores (with `_current_season()` helper for NBA season year convention)
- `betting/tasks.py` — fetch_odds, settle_pending_bets
- `bots/tasks.py` — run_bot_strategies, execute_bot_strategy (staggered dispatch, auto-bailout)
- `discussions/tasks.py` — generate_pregame_comments, generate_postgame_comments (Claude API)
- `activity/tasks.py` — broadcast_next_activity_event, cleanup_old_activity_events
- `activity/services.py` — `queue_activity_event()` helper
- `challenges/tasks.py` — rotate_daily_challenges, rotate_weekly_challenges, expire_challenges

### Phase 3: Admin, Signals, Forms, Context Processors
- Admin registrations for all league-specific models (Team, Game, Standing, GameStats, Odds, BetSlip, Parlay, BotProfile, Comment, ActivityEvent)
- `betting/signals.py` — post_save on BetSlip for challenge progress tracking
- `betting/forms.py` — BetForm (market/selection/odds/line/stake), ParlayAddForm
- `website/forms.py` — LoginForm, SignupForm
- `discussions/forms.py` — CommentForm
- Context processors: bankruptcy check, parlay slip (session-based), activity toasts, hub_url, theme

### Phase 4: Management Commands
- `games/management/commands/seed_nba.py` — Calls sync_teams/games/standings, supports `--offline` mode with `games/static_data/teams.json`
- `bots/management/commands/seed_bots.py` — Creates 35 bot users from personas.py

### Phase 5: Views & URLs
- `website/` — DashboardView (today's games grouped by live/upcoming/final), LoginView, SignupView, LogoutView, AccountView
- `games/` — ScheduleView (date nav + conference filter), StandingsView (East/West tabs), GameDetailView (odds + bet form + comments)
- `betting/` — PlaceBetView, MyBetsView, BailoutView, parlay management (add/remove/clear/place)
- `discussions/` — CreateCommentView, DeleteCommentView
- `activity/` — ToggleToastsView
- `challenges/` — ChallengeListView
- `config/urls.py` — All route includes wired up

### Phase 6: Templates (28 HTML files)
Cloned from EPL design system and adapted for NBA:
- `base.html` with NBA branding (orange-red accent)
- Website: dashboard, login, signup, account, navbar, footer, avatar, toast, empty_state
- Games: schedule, standings (East/West tabs), game_detail, game_card, game_list, standings_table
- Betting: my_bets, bet_form, bet_confirmation, bet_list, parlay_slip, parlay_confirmation, bailout_overlay
- Discussions: comment, comment_form
- Challenges: challenge_list
- Activity: toast OOB partial

### Phase 7: WebSocket & Static
- Updated `activity/consumers.py` for structured event broadcasting
- `website/static/website/css/styles.css` — NBA color tokens, themed panels

## Key Adaptation Patterns

### Balance API Wrapper
The biggest porting challenge: vinosports-core's `log_transaction(user_balance, ...)` requires a pre-locked UserBalance, while nba-bets' version takes a `User` and locks internally. Created `betting/balance.py` as a compatibility wrapper to minimize changes across all service files.

### Import Remapping
| nba-bets import | vinosports import |
|---|---|
| `from betting.models import UserBalance, UserStats, ...` | `from vinosports.betting.models import UserBalance, UserStats, ...` |
| `from betting.models import BetStatus, TransactionType` | `from vinosports.betting.models import BetStatus, BalanceTransaction` (Type is `BalanceTransaction.Type`) |
| `from users.models import User` | `from django.contrib.auth import get_user_model` |
| `from betting.models import Odds` | `from games.models import Odds` (Odds lives in games app in vinosports) |

### NBA vs EPL Differences
- **Odds format:** American integers (+150, -110) vs decimal (2.50, 1.91)
- **Markets:** Moneyline/Spread/Total vs Home Win/Draw/Away Win
- **No draw:** NBA has no draw market
- **Data sources:** SportsData.io + The Odds API vs football-data.org + synthetic odds
- **Game structure:** Conferences, divisions, tip-off time vs matchdays, kickoff

## What's Not Ported

- **Board module** — Community prediction/results posts. Exists in original nba-bets but not in vinosports-core. Deliberately excluded.
- **Tests** — No test files ported. Factories and test suites need to be written fresh against the vinosports model structure.
- **Rewards views** — Reward list/mark-seen views not yet wired (core reward models exist but no NBA-specific views)

## Running It

```bash
make up                    # Rebuild containers
make shell-nba             # Enter NBA container
python manage.py makemigrations nba_bots  # ANTI_HOMER + risk_multiplier + max_daily_bets
python manage.py migrate
python manage.py seed_nba --offline
python manage.py seed_bots
# Browse localhost:8001
```

Live data pipeline requires `.env` keys: `SPORTSDATA_API_KEY`, `ODDS_API_KEY`, `ANTHROPIC_API_KEY`.
