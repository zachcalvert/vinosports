# 0024: Standings Page Redesign — NBA & EPL

**Date:** 2026-03-25

## Overview

Editorial-style redesign of both the NBA standings and EPL league table pages. Inspired by designer mockups, these pages now feature bold typographic headers, sidebar widgets with contextual data, zone boundary indicators, and a premium "sports magazine" aesthetic. No new models or migrations — everything is derived from existing `Standing`, `Team`, and `Match` data.

## NBA Standings (`/nba/standings/`)

### What Changed

**Editorial header** — large italic Epilogue "NBA CONFERENCE STANDINGS" with season subtitle and red accent bar. Replaces the previous plain heading.

**Pill-style conference tabs** — rounded-full buttons (Western default, Eastern). Same HTMX tab-switching mechanism (`hx-target="#standings-panel"`), just restyled.

**Two-column grid layout** — standings table + dynamic widgets on the left (HTMX-swappable), static Championship Odds widget on the right. Collapses to single column below `xl`.

**Table refinements:**
- Play-in tournament boundary separator (thick border between rank 6 and 7)
- Bolder rank numbers for playoff seeds
- Larger team logos (w-6 instead of w-5)
- Monospace W/L columns

**New sidebar widgets:**
- **Projected Matchup** — shows 1 vs 8 seed for the active conference. Computed by indexing the standings queryset at positions 0 and 7.
- **Division Leaders** — top 3 teams in the #1 seed's division. Queries `Standing` filtered by `team__division`.
- **Championship Odds** — static editorial content with hardcoded futures odds. Placeholder until we have a data source.

**Sidebar CTA** — "Place Live Bet" button added to the NBA left-nav sidebar, linking to the schedule page.

### Files Modified
- `nba/games/views.py` — `StandingsView` now computes `projected_matchup`, `division_leaders`, `division_name`; HTMX partial changed to `standings_panel.html`
- `nba/games/templates/games/standings.html` — full page restructure
- `nba/games/templates/games/partials/_standings_body.html` — table visual refinements
- `nba/templates/nba_website/components/sidebar.html` — CTA button
- `nba/website/static/nba_website/css/styles.css` — `.sidebar-link--cta`

### Files Created
- `nba/games/templates/games/partials/standings_panel.html` — HTMX swap wrapper
- `nba/games/templates/games/partials/_projected_matchup.html`
- `nba/games/templates/games/partials/_division_leaders.html`
- `nba/games/templates/games/partials/_championship_odds.html`

## EPL League Table (`/epl/table/`)

### What Changed

**Editorial header** — large italic Epilogue "PREMIER LEAGUE TABLE" inside a rounded card with left border accent, "Vinosports Editorial" label, matchday counter ("Matchday 32 of 38"), and decorative soccer ball icon.

**Two-column grid layout** — table takes 2/3 width, sidebar widgets take 1/3. Collapses to single column below `xl`.

**Restyled table:**
- **Champions League zone** (positions 1-4) — blue left border (`border-l-secondary`), tinted background
- **Mid-Table Boundary** — separator row between position 4 and 5
- **Relegation Danger Zone** — separator row and red left border for positions 18-20
- **Combined W-D-L column** — replaces separate W, D, L columns
- **Last 5 form circles** — green (W), red (L), gray (D) circles computed from recent `Match` results
- **Bold italic team names** using Epilogue font
- **Large bold points** in primary color
- **TLA fallback badges** when team crests aren't available

**New sidebar widgets:**
- **Title Race Probability** — progress bars for top 3 teams with editorial percentages. Static content.
- **Next Major Broadcast** — upcoming fixture between top-6 teams. Dark card with team crests, kickoff time, and "View Match Preview" link. Gold text (`tertiary-fixed-dim`) on dark background for contrast.

**Sidebar updates:**
- Added "Standings" link (was previously missing from EPL nav)
- Added "View Live Scores" CTA button

### View Logic
`LeagueTableView.get_context_data()` now computes:
- `matchday` — highest matchday among finished matches (`Max` aggregate)
- `form_by_team` — dict mapping team PK → list of last 5 results (W/D/L), computed from `Match` objects
- `next_big_match` — first upcoming match where both teams are in the top 6

### Files Modified
- `epl/matches/views.py` — expanded `LeagueTableView` with form, matchday, next match context
- `epl/matches/templatetags/match_tags.py` — added `get_item` filter for dict lookups
- `epl/matches/templates/matches/league_table.html` — full page restructure
- `epl/matches/templates/matches/partials/standings_row.html` — zone indicators, form circles, combined W-D-L
- `epl/website/templates/epl_website/components/sidebar.html` — Standings link + CTA
- `epl/website/static/epl_website/css/styles.css` — `.sidebar-link--cta`

### Files Created
- `epl/matches/templates/matches/partials/_title_race.html`
- `epl/matches/templates/matches/partials/_next_big_match.html`

## Future Work

Two features identified during this work are deferred for later:

1. **L10 Record** (NBA) — "Last 10 games" column. Likely available from BallDontLie API, otherwise computable from `Game` objects. Would need a model field + sync update.

2. **AI Analyst Insight** (both leagues) — generated commentary using Claude API. The bot infrastructure already has Claude API integration patterns to reuse. Approach: prompt template with standings context → Celery task on standings sync → cached display.

3. **Leading Goalscorer** (EPL) — requires player stats data we don't currently have.

4. **Dynamic Title Race / Championship Odds** — currently hardcoded editorial content. Could be computed algorithmically or managed via admin.
