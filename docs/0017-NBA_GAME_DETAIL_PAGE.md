# 0017: Enhanced NBA Game Detail Page

**Date:** 2026-03-24

## Goal

Redesign the NBA game detail page into a rich, real-time experience that takes full advantage of the BallDontLie (BDL) live scores API. The page should feel alive during in-progress games — scores update without refresh, the UI reflects game state transitions, and the layout adapts to whether a game is upcoming, live, or final.

## Current State

The existing `GameDetailView` (`apps/nba/games/views.py`) renders a single server-rendered page with:
- Game info (teams, scores, status, tip-off time)
- Latest odds (top 5 historical)
- Community sentiment widgets (moneyline, spread, total)
- Comments section (last 50 with replies)
- User's own bets for this game
- Recap context for final games (upset detection, betting outcomes)

**What's missing:**
- No live updates — users must refresh to see score changes
- No visual distinction between game states (upcoming vs live vs final)
- No quarter/half indicators during live games
- The `GameStats` model (h2h, form, injuries) exists but is unpopulated
- No transition animations when game state changes (e.g., scheduled → in progress → final)

**What we have to work with:**
- `sync_live_scores()` already broadcasts WebSocket messages to `game_{id_hash}` channel groups
- The NBA app already has Channels/Daphne configured (used by activity feed)
- BDL provides: scores, game status (quarter strings, "Halftime", "Final"), updated in near-real-time
- HTMX is the frontend framework — no JS framework needed

## Design

### Three-State Layout

The page should have three distinct presentations based on `game.status`:

#### 1. Pre-Game (SCHEDULED)

The game hasn't started yet. Focus on building anticipation and helping users place bets.

**Layout:**
```
┌─────────────────────────────────────────────┐
│  [Away Team Logo]  vs  [Home Team Logo]     │
│  Team Name              Team Name           │
│  (Record: 35-20)        (Record: 40-15)     │
│                                             │
│  Tip-off: Thu Mar 26 · 7:30 PM ET           │
│  Arena: TD Garden                           │
├─────────────────────────────────────────────┤
│  ODDS          │  PLACE YOUR BET            │
│  ML: -150/+130 │  [Market selector]         │
│  Spread: -4.5  │  [Selection]               │
│  Total: 215.5  │  [Stake input]             │
│                │  [Place bet button]         │
├─────────────────────────────────────────────┤
│  COMMUNITY PICKS                            │
│  [Moneyline %] [Spread %] [Total %]         │
├─────────────────────────────────────────────┤
│  YOUR BETS (if any)                         │
├─────────────────────────────────────────────┤
│  DISCUSSION                                 │
│  [Comment form + thread]                    │
└─────────────────────────────────────────────┘
```

**Key elements:**
- Countdown to tip-off (client-side JS, updates every second when <24h away)
- Team records from standings
- Odds prominently displayed with bet form
- Sentiment widgets showing community lean

#### 2. Live Game (IN_PROGRESS, HALFTIME)

The game is happening now. Focus shifts to the live score and game flow.

**Layout:**
```
┌─────────────────────────────────────────────┐
│  ● LIVE — 3rd Qtr                           │
│                                             │
│  [Away Logo]  98  -  102  [Home Logo]       │
│  Team Name              Team Name           │
│                                             │
│  Score last updated: 30s ago                │
├─────────────────────────────────────────────┤
│  LIVE BETTING          │  YOUR BETS         │
│  (if odds still open)  │  [bet cards with   │
│  [Bet form]            │   live status]     │
├─────────────────────────────────────────────┤
│  COMMUNITY PICKS                            │
│  [Moneyline %] [Spread %] [Total %]         │
├─────────────────────────────────────────────┤
│  DISCUSSION                                 │
│  [Live comment thread]                      │
└─────────────────────────────────────────────┘
```

**Key elements:**
- Pulsing live indicator (CSS animation)
- Large, prominent score display
- Game status badge (1st Qtr, 2nd Qtr, Halftime, 3rd Qtr, 4th Qtr)
- Scores update via WebSocket without page refresh
- "Last updated" timestamp so users know data freshness
- User's active bets shown with current game context (e.g., "You bet HOME -4.5 → currently leading by 4")

**Real-time update mechanism:**

The infrastructure is already in place:
1. `sync_live_scores()` (Celery task, runs every 20-30s during game windows) fetches scores from BDL
2. When scores change, it broadcasts to the `game_{id_hash}` WebSocket group
3. The game detail page needs a WebSocket consumer to receive these updates

**Implementation approach — HTMX + WebSocket:**
- Use `hx-ext="ws"` to connect to a game-specific WebSocket endpoint
- The WebSocket consumer sends an HTMX-compatible HTML fragment when scores update
- The fragment replaces the scoreboard partial via `hx-swap-oob`
- No custom JavaScript needed beyond HTMX's WebSocket extension

**WebSocket consumer (new):**
```python
# apps/nba/games/consumers.py
class GameScoreConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.id_hash = self.scope["url_route"]["kwargs"]["id_hash"]
        self.group_name = f"game_{self.id_hash}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def game_score_update(self, event):
        # Render the scoreboard partial with fresh data
        # Send as HTMX OOB swap
        html = render_scoreboard_partial(event)
        await self.send(text_data=html)
```

**What gets updated live:**
- Score (home and away)
- Game status badge (quarter/half)
- "Last updated" timestamp
- User bet status cards (if bet outcome becomes determinable)

**What does NOT update live (intentionally):**
- Odds (frozen at game start or managed separately)
- Comments (already have their own WebSocket via discussions)
- Sentiment widgets (static once game starts)

#### 3. Post-Game (FINAL)

The game is over. Focus on results, outcomes, and discussion.

**Layout:**
```
┌─────────────────────────────────────────────┐
│  FINAL                                      │
│                                             │
│  [Away Logo]  108  -  115  [Home Logo]      │
│  Team Name     ✗           ✓  Team Name     │
│                                             │
│  [Upset badge if applicable]                │
├─────────────────────────────────────────────┤
│  RECAP                                      │
│  Total bets: 47 · Winners: 28 (60%)        │
│  Total staked: 12,500 · Total paid: 15,200 │
├─────────────────────────────────────────────┤
│  YOUR RESULTS                               │
│  [Bet cards with WON/LOST/VOID badges]      │
├─────────────────────────────────────────────┤
│  COMMUNITY PICKS (how the crowd did)        │
│  [Moneyline %] [Spread %] [Total %]         │
├─────────────────────────────────────────────┤
│  DISCUSSION                                 │
│  [Post-game thread]                         │
└─────────────────────────────────────────────┘
```

**Key elements:**
- Winner/loser clearly indicated (checkmark/X, or bold/muted)
- Upset detection badge (underdog won)
- Betting recap stats (total bets, win rate, total staked vs paid out)
- User's bet results with clear WON/LOST/VOID styling
- Community sentiment shown as "how the crowd picked" — retrospective

### Scoreboard Component

The scoreboard is the centerpiece. It should be a single reusable partial (`games/partials/scoreboard.html`) that renders differently based on state:

| State | Display |
|-------|---------|
| SCHEDULED | Team logos + names + records, tip-off countdown |
| IN_PROGRESS | Pulsing dot + quarter, large scores, last-updated |
| HALFTIME | "Halftime" badge, scores, last-updated |
| FINAL | "Final" badge, scores, winner highlight |
| POSTPONED | "Postponed" badge, original tip-off time |

This partial is also the target for WebSocket OOB swaps during live games.

### Live Update Flow

```
BDL API ──(every 20-30s)──▶ sync_live_scores() Celery task
                                    │
                              score changed?
                                    │ yes
                                    ▼
                           Channel layer group_send
                           to "game_{id_hash}"
                                    │
                                    ▼
                          GameScoreConsumer
                          renders scoreboard partial
                                    │
                                    ▼
                          HTMX ws extension
                          swaps #scoreboard div
                          on user's open page
```

**Freshness guarantee:** The `sync_live_scores` task runs every 20-30 seconds during active game windows. Users see score updates within ~30-60 seconds of the real event. The "last updated" timestamp sets expectations.

**Reconnection:** HTMX's WebSocket extension handles reconnection automatically. If a user's connection drops, it reconnects and the next score update will bring the UI current.

### Bet Status During Live Games

User bet cards should reflect live game context where possible:

| Bet Type | Live Context |
|----------|-------------|
| Moneyline HOME | "Your team is winning" / "Your team is trailing" |
| Spread HOME -4.5 | "Currently covering (leading by 6)" / "Not covering (leading by 2)" |
| Total OVER 215.5 | "Combined: 200 — pace for 267" / "Combined: 150 — pace for 200" |

Pace calculation: `(current_total / quarters_elapsed) * 4` — rough but useful. This is client-side display only, not stored.

## Implementation Steps

### Phase 1: Template Restructuring
1. Split `game_detail.html` into state-specific sections using `{% if game.is_live %}` / `{% if game.is_final %}` / `{% else %}` blocks
2. Extract `scoreboard.html` partial (reusable across states)
3. Extract `bet_card.html` partial (shows a single user bet with status styling)
4. Extract `recap_card.html` partial (post-game stats — already partially exists)
5. Style the three states with appropriate visual treatment (live pulse, final muted tones, pre-game anticipation)

### Phase 2: WebSocket Live Updates
1. Create `GameScoreConsumer` in `apps/nba/games/consumers.py`
2. Add WebSocket URL route: `ws/game/<id_hash>/`
3. Update `sync_live_scores()` broadcast payload to include all fields the scoreboard partial needs
4. Add `hx-ext="ws"` connection to the game detail template (only for non-final games)
5. Render scoreboard partial server-side in the consumer's `game_score_update` handler
6. Test with a live game — verify score updates flow through without page refresh

### Phase 3: Enhanced Pre-Game
1. Add tip-off countdown (small inline `<script>` targeting a `<time>` element — no framework needed)
2. Display team records from standings alongside team names
3. Improve odds display layout (current odds card already exists, enhance visual hierarchy)

### Phase 4: Enhanced Post-Game
1. Build the recap section (total bets, win %, staked vs paid, upset badge)
2. Style user bet results with clear WON (green) / LOST (red) / VOID (gray) treatment
3. Show community sentiment as retrospective ("58% picked Home — they were right")

### Phase 5: Polish
1. Transition animations when game state changes (scheduled → live → final)
2. Responsive layout adjustments (scoreboard stacks vertically on mobile)
3. Loading states for WebSocket connection (subtle indicator)
4. Test across game states with real BDL data

## Dependencies

- BDL API (All-Star tier) — already configured, provides live scores
- Django Channels + Daphne — already configured in NBA app
- Redis — already running for channel layer backend
- HTMX WebSocket extension — may need to add `ws.js` to static assets if not already included

## Out of Scope

- Player-level stats (BDL v1 doesn't provide per-player data in the games endpoint)
- Play-by-play feed
- Box scores
- Populating the `GameStats` model (h2h, form, injuries) — future enhancement
- Cross-app challenge integration with live game events
