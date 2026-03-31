# 0029: NFL League — Master Plan

**Date:** 2026-03-30
**Status:** Planning

## Overview

Add the NFL as the third supported league in vinosports. This follows the same architecture established by EPL and NBA: concrete shared models in `vinosports-core`, league-specific apps under `nfl/`, prefixed app labels and template/static directories, and integration into the unified Django project.

The NFL is fundamentally different from EPL and NBA in ways that will shape the implementation. This document is the parent plan — each phase will get its own child doc with detailed specs once we're ready to execute.

## NFL vs. Existing Leagues — Key Differences

### Schedule & Cadence
- **17-week regular season** (Sep–Jan) vs. EPL's 38 matchweeks or NBA's 82-game season
- **Fewer games, higher stakes**: 272 regular season games vs. NBA's 1,230 or EPL's 380
- **Weekly rhythm**: Most games Sun 1pm/4pm ET, SNF, MNF, TNF — concentrated windows, not daily
- **Playoffs**: Single elimination (Wild Card → Divisional → Conference Championship → Super Bowl)
- **Bye weeks**: Each team has one bye week during the regular season
- **Offseason is long**: ~7 months with no games (Feb–Sep), though draft/free agency generate interest

### Betting Markets
- **Spread-dominant**: NFL betting culture centers on the point spread more than any other sport
- **Props are massive**: Player props (passing yards, TDs, receptions) are a huge part of NFL betting
- **Game props**: First team to score, will there be a safety, overtime yes/no, etc.
- **Weekly structure**: Lines open early in the week and move through game day — line movement is a big part of NFL culture
- **Teasers**: A distinctive NFL bet type (modified spread parlay) — worth considering
- **Survivor pools / Pick'em**: Popular social betting formats unique to football's weekly cadence

### Data Model
- **Conferences & Divisions**: AFC/NFC, 4 divisions each (8 total) — more granular than EPL (single table) or NBA (2 conferences, 6 divisions)
- **Player positions are highly differentiated**: QB, RB, WR, TE, K, DEF — matters for props/fantasy
- **Box scores are complex**: Passing, rushing, receiving, defensive, special teams stats per player
- **Injury reports**: Official injury designations (Questionable/Doubtful/Out) released weekly — major betting factor
- **Depth charts**: Starter/backup status matters significantly more than in NBA/EPL

### Community & Bots
- **Weekly discussion cadence**: Pregame threads mid-week, game day threads, postgame analysis
- **Power rankings**: A staple of NFL culture — weekly rankings with commentary
- **Trash talk peaks around rivalries**: Divisional matchups 2x/year create natural narratives

## Data Source — BallDontLie NFL API

**Confirmed**: BDL covers NFL at `https://api.balldontlie.io/nfl/v1`. Same auth pattern, same cursor-based pagination, same response wrapper (`{"data": [...], "meta": {...}}`) as our NBA and EPL clients. Data available from 2002 to present.

### Tier Breakdown

| Tier | Cost | Rate Limit | Endpoints |
|------|------|------------|-----------|
| **Free** | $0 | 5 req/min | Teams, Players, Games |
| **All-Star** | $9.99/mo | 60 req/min | + Standings, Stats, Season Stats, Team Stats, Injuries, Active Players |
| **GOAT** | $39.99/mo | 600 req/min | + Roster/Depth Charts, Advanced Stats (rushing/passing/receiving), Play-by-Play, Betting Odds, Player Props |

**Important**: Tiers are per-sport. Our existing NBA All-Star subscription does not cover NFL.

### Strategy

**Phase 1 (now)**: Build on **free tier**. Teams, players, and games are enough to stand up the full foundation — models, migrations, data client, seed commands, admin. The 5 req/min limit is fine for seeding and dev; we're not polling live.

**Phase 2+ (closer to Sep 2026)**: Upgrade to **All-Star** ($9.99/mo) when we need standings, player stats, and team stats for the betting engine and game detail views.

**Phase 3+ (if needed)**: GOAT ($39.99/mo) only if we want BDL-sourced betting odds or player props. We may generate house odds internally (like NBA) and skip this tier entirely.

### Free Tier Endpoints (Phase 1 scope)

| Endpoint | Path | Returns |
|----------|------|---------|
| All Teams | `GET /nfl/v1/teams` | 32 teams with conference/division |
| Single Team | `GET /nfl/v1/teams/<ID>` | Team detail |
| All Players | `GET /nfl/v1/players` | Roster with search/filter |
| Single Player | `GET /nfl/v1/players/<ID>` | Player detail |
| All Games | `GET /nfl/v1/games` | Schedule/scores, filterable by date/season/week |
| Single Game | `GET /nfl/v1/games/<ID>` | Game detail with quarter-by-quarter scores |

### All-Star Endpoints (Phase 2 scope)

| Endpoint | Path | Returns |
|----------|------|---------|
| Standings | `GET /nfl/v1/standings` | Regular season standings by season |
| Player Stats | `GET /nfl/v1/stats` | Real-time player game stats |
| Season Stats | `GET /nfl/v1/season_stats` | Cumulative season stats |
| Team Stats | `GET /nfl/v1/team_stats` | Team offensive/defensive game stats |
| Team Season Stats | `GET /nfl/v1/team_season_stats` | Seasonal team metrics |
| Injuries | `GET /nfl/v1/player_injuries` | Current injury reports |
| Active Players | `GET /nfl/v1/players/active` | Active roster players |

### GOAT Endpoints (deferred)

| Endpoint | Path | Returns |
|----------|------|---------|
| Team Roster | `GET /nfl/v1/teams/<ID>/roster` | Depth chart (2025+ data) |
| Advanced Rushing | `GET /nfl/v1/advanced_stats/rushing` | Expected yards, efficiency |
| Advanced Passing | `GET /nfl/v1/advanced_stats/passing` | Air yards, completion %, time to throw |
| Advanced Receiving | `GET /nfl/v1/advanced_stats/receiving` | Separation, catch %, YAC |
| Play-by-Play | `GET /nfl/v1/plays` | Down/distance, play descriptions |
| Betting Odds | `GET /nfl/v1/odds` | Live odds from multiple sportsbooks |
| Player Props | `GET /nfl/v1/odds/player_props` | Player prop lines by vendor |

## Phased Rollout

### Phase 1: Foundation — Models, Data, Seeding
_Child doc: [0030-NFL_FOUNDATION.md](0030-NFL_FOUNDATION.md)_

- `nfl/` package structure with all sub-apps
- Models: Team (with conference/division), Game (with week number + quarter scores), Player
- `NFLDataClient` hitting free-tier endpoints (teams, players, games)
- Sync helpers and `seed_nfl` management command (live + offline modes)
- Standings computed locally from game results (free tier has no standings endpoint)
- Admin registrations, migrations
- Static data fixtures for offline seeding

### Phase 2: Betting Engine
_Child doc: [0031-NFL_BETTING_ENGINE.md](0031-NFL_BETTING_ENGINE.md)_

- Concrete models: BetSlip (moneyline/spread/total), Parlay, ParlayLeg, Odds (all American format)
- Settlement engine: same moneyline/spread/total evaluation as NBA, with NFL tie handling
- House odds engine: algorithmic generation from standings + point differential
- Futures: Super Bowl, AFC/NFC Champion, Division Winner markets (NFL-specific division markets)
- Parlay adapter for core ParlayBuilder
- Props, teasers, game props deferred to post-launch

### Phase 3: Bot System
_Child doc: [0032-NFL_BOT_SYSTEM.md](0032-NFL_BOT_SYSTEM.md)_

- Bot personas (~20 at launch: 8 archetype + 12 team homer bots)
- Betting strategies calibrated for NFL (spread-dominant, key number awareness, weekly cadence)
- Commentary generation (pregame, postgame) with NFL-specific context (spreads, totals, weekly rhythm)
- NFL-specific personality traits (the spread whisperer, the lock-of-the-week guy, the analytics nerd)
- Comment/Discussion/ActivityEvent models for NFL
- Schedule templates tuned to NFL's weekly game windows (Sunday slate, TNF, SNF, MNF)

### Phase 4: Website & Views
_Child doc: TBD_

- Dashboard (this week's games, live scores)
- Schedule (week-by-week navigation, not date-based)
- Standings (division-centric, playoff picture)
- Game detail (odds, bet form, box score, comments)
- My Bets, Bailout, Challenges
- Templates cloned from NBA/EPL design system, adapted for NFL

### Phase 5: Celery Tasks & Scheduling
_Child doc: TBD_

- NFL-specific timing: weekly data sync, Sunday/Monday/Thursday game windows
- Live score polling during active game windows only
- Bot betting timed to weekly cadence (not daily like NBA)
- Discussion generation around weekly rhythm

### Phase 6: WebSocket & Real-time
_Child doc: TBD_

- Live score consumers
- Activity feed
- WebSocket routing in `config/asgi.py`

### Phase 7: Polish & Launch
_Child doc: TBD_

- Test suite (target: match EPL/NBA coverage ratios)
- Integration into hub dashboard
- Global navbar updates
- Challenge templates for NFL
- Rewards integration
- Production deployment (Celery queues, beat schedule)

## Open Questions

1. **Scope of betting markets at launch**: Core three (moneyline/spread/total) only, or include player props from day one? Props would require the Player model and significantly more data plumbing.
2. **Teasers**: Unique to football culture. Worth building as a new bet type, or defer?
3. **Survivor/Pick'em pools**: These are social formats that don't exist in EPL/NBA. Could be a differentiator but are entirely new features. Defer to post-launch?
4. **Offseason content**: NFL has a ~7 month offseason. What keeps users engaged? Draft coverage? Futures markets? This is a product question more than a technical one.
5. **Season timing**: NFL regular season starts in September 2026. What's our target for having this ready?

## Child Documents

| Phase | Doc | Status |
|-------|-----|--------|
| Phase 1: Foundation | [0030-NFL_FOUNDATION.md](0030-NFL_FOUNDATION.md) | Complete |
| Phase 2: Betting Engine | [0031-NFL_BETTING_ENGINE.md](0031-NFL_BETTING_ENGINE.md) | Complete |
| Phase 3: Bot System | [0032-NFL_BOT_SYSTEM.md](0032-NFL_BOT_SYSTEM.md) | Planning |
| Phase 4: Website & Views | TBD | Not started |
| Phase 5: Celery Tasks | TBD | Not started |
| Phase 6: WebSocket | TBD | Not started |
| Phase 7: Polish & Launch | TBD | Not started |
