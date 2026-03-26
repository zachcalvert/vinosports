# 0020: Hub Quick Wins — Global Standings, My Bets, Admin Dashboard

**Date:** 2026-03-25

## Overview

Three hub-level views that aggregate existing league data into cross-league pages. All are "read existing data, render in hub" work — no new models, no new business logic. The unified Django project makes these trivial since everything is in one DB and one process.

## 1. Global Standings (`/standings/`)

### What Exists
- `vinosports.betting.leaderboard.get_leaderboard_entries(limit, board_type)` — already queries `UserBalance` and `UserStats`, which are global (one balance per user across all leagues)
- Four board types: `balance`, `profit`, `win_rate`, `streak`
- `get_user_rank()` computes rank for users outside the top N
- Results cached for 30 seconds, superusers excluded
- EPL renders this at `/epl/leaderboard/` with tabs for each board type + HTMX partials

### What to Build
- Hub view at `/standings/` rendering the existing `get_leaderboard_entries()` utility
- Tabs for each board type, reusing the EPL leaderboard template pattern
- Optional: league-specific filtering (show only users who've bet in EPL/NBA)
- Link user rows to their public profile (`/bots/<slug>/` or a future `/users/<slug>/`)

### Key Files
- `packages/vinosports-core/src/vinosports/betting/leaderboard.py` — leaderboard logic
- `epl/matches/views.py` — `LeaderboardView`, `LeaderboardPartialView` (reference implementation)
- `epl/matches/templates/epl_matches/leaderboard.html` — template to adapt

---

## 2. My Bets (`/my-bets/`)

### What Exists
- EPL: "My Bets" view at `/epl/bets/mine/` — shows user's BetSlips and Parlays
- NBA: "My Bets" view at `/nba/bets/mine/` — same pattern with American odds
- Each queries only its own league's models

### What to Build
- Hub view at `/my-bets/` (or `/account/bets/`) for the logged-in user
- Query both `epl.betting.BetSlip`, `nba.betting.BetSlip`, both Parlay models
- Sort: pending bets first, then completed by most recent
- Each bet links back to its league-specific match/game detail page
- League badge on each row (EPL/NBA) for visual distinction

### Design Decisions
- **Tabs vs. single list:** A single interleaved list (sorted by date, pending first) is simpler and more useful than per-league tabs (users can already visit league-specific pages for that)
- **Parlay display:** Show parlays as expandable rows with legs listed underneath

### Key Files
- `epl/betting/models.py` — `BetSlip`, `Parlay`, `ParlayLeg` (decimal odds, 1X2 market)
- `nba/betting/models.py` — `BetSlip`, `Parlay`, `ParlayLeg` (American odds, moneyline/spread/total)
- `epl/betting/views.py` — EPL my-bets view (reference)
- `nba/betting/views.py` — NBA my-bets view (reference)

---

## 3. Admin Dashboard (`/admin-dashboard/`)

### What Exists
- EPL: admin dashboard at `/epl/admin/dashboard/` — superuser-only, shows total_users, active_bets, active_parlays, total_comments, total_bets_all_time, total_in_play, with pagination
- NBA: similar dashboard at `/nba/admin/dashboard/`
- Both use `SuperuserRequiredMixin`

### What to Build
- Hub view at `/admin-dashboard/` behind `SuperuserRequiredMixin`
- Aggregate metrics: total users, total bets (EPL + NBA), total parlays, total comments
- Recent bets & parlays across both leagues (interleaved by created_at)
- Recent comments across both leagues (interleaved by created_at)
- Per-league breakdowns as secondary detail

### Key Files
- `epl/website/views.py` — EPL admin dashboard view (reference)
- `nba/website/views.py` — NBA admin dashboard view (reference)
- `epl/betting/models.py`, `nba/betting/models.py` — bet/parlay models
- `epl/discussions/models.py`, `nba/discussions/models.py` — comment models
