# 0021: Centralized Challenges

**Date:** 2026-03-25

## Overview

A hub-level challenges page that aggregates challenge data across leagues, with an optional path toward cross-league challenges.

## What Exists

### Core Models (`vinosports.challenges`)
- `ChallengeTemplate` — reusable blueprint with criteria_type and criteria_params (JSON)
  - ChallengeType: DAILY, WEEKLY, SPECIAL
  - CriteriaType: BET_COUNT, BET_ON_UNDERDOG, WIN_COUNT, WIN_STREAK, PARLAY_PLACED, PARLAY_WON, TOTAL_STAKED, BET_ALL_MATCHES, CORRECT_PREDICTIONS
- `Challenge` — time-bound instance (starts_at, ends_at, status: UPCOMING/ACTIVE/EXPIRED)
- `UserChallenge` — per-user progress (progress, target, status, completed_at, reward_credited)

### EPL Implementation (full-featured)
- 9 evaluators in `challenge_engine.py` covering all criteria types
- Auto-enrollment via `_ensure_enrollment()` in challenge views
- Three-tab UI (active/completed/upcoming) with HTMX partials
- Dashboard widget showing top 3 active challenges
- WebSocket broadcast on challenge completion
- Celery tasks for challenge lifecycle automation

### NBA Implementation (minimal)
- Basic list view, no auto-enrollment, no progress tracking UI
- Celery tasks exist but evaluation is simpler

## What to Build

### Phase 1: Hub Aggregation
- Hub view at `/challenges/` showing all `UserChallenge` records for the current user
- Group by status (active → completed → upcoming)
- Each challenge tagged with its league (EPL/NBA)
- Link to league-specific challenge detail if one exists

### Phase 2 (Nice-to-Have): Cross-League Challenges
- New criteria types that query across both leagues (e.g., "Place bets in 2+ leagues this week")
- Hub-level evaluator that can query both EPL and NBA betting models
- These challenges would have no league FK — they belong to the hub

## Key Files
- `packages/vinosports-core/src/vinosports/challenges/models.py` — core models
- `epl/website/challenge_engine.py` — full evaluator implementation (reference)
- `epl/website/challenge_views.py` — full UI implementation (reference)
- `nba/website/challenge_views.py` — minimal implementation
