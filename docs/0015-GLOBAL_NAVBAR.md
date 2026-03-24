# Global Navbar & League Sidebar

**Date:** 2026-03-24
**Status:** Complete
**Relates to:** Phase 3a of `9999-PRE_LAUNCH_PLAN.md`

## Overview

Added a shared global navigation bar that appears on all three apps (hub, EPL, NBA) and converted each league app's page navigation into a left sidebar. This creates a two-tier navigation hierarchy: a consistent top bar for cross-app navigation, and a league-specific sidebar for in-app pages.

## Architecture

### Tier 1: Global Navbar

A single shared template partial in the `vinosports-core` package, included by all three apps via `{% include "vinosports/components/global_navbar.html" %}`.

**Contents:**
- **Logo** — "VINOSPORTS" wordmark linking back to hub
- **League tabs** — EPL and NBA links with gold active indicator for the current league
- **Mobile sidebar toggle** — hamburger button (league apps only, hidden on desktop)
- **Auth section** — login/signup buttons for anonymous users, or user dropdown (balance, profile, theme toggle, logout) for authenticated users

**Key design decisions:**
- Always-dark background (`--color-dark`) regardless of theme, matching the existing navbar aesthetic
- Gold accent (`--color-gold`) for the active league tab — neutral across league color schemes
- User icon instead of avatar component in the dropdown trigger (avatar depends on league-specific template tags)
- CSS is embedded in the template via `<style>` tag — keeps the partial self-contained since the core package has no static files infrastructure
- JS for dropdown and sidebar toggle is also inline in the partial

### Tier 2: League Sidebar

Each league app has its own sidebar partial (`website/components/sidebar.html`) since the page links differ between leagues.

**EPL sidebar:** Dashboard, Leaderboard, Odds, My Bets, Challenges, Admin (superuser)
**NBA sidebar:** Dashboard, Schedule, Standings, My Bets, Challenges, Admin (superuser)

**Desktop (lg+):** 13rem wide, sticky below the global nav, with Phosphor duotone icons + text labels. Active link highlighted with the league's accent color.

**Mobile (< lg):** Hidden by default. Triggered by the hamburger in the global nav. Slides in as a drawer from the left over a semi-transparent backdrop. Close via X button or tapping the backdrop.

### Hub (no sidebar)

The hub has no sidebar — just the global navbar above full-width content (the league picker page). The hamburger button is conditionally hidden when `current_league` is `None`.

## Implementation

### Shared context processor

`vinosports.context_processors.global_nav` provides three variables to all templates:
- `leagues` — the `LEAGUE_URLS` dict from settings
- `hub_url` — browser-facing hub URL
- `current_league` — `"epl"`, `"nba"`, or `None` (hub)

This replaced the hub's `hub.context_processors.league_urls` and the EPL/NBA `website.context_processors.hub_url`.

### Settings additions

Each app gained:
- `CURRENT_LEAGUE` — string identifier (`"epl"`, `"nba"`) or `None` (hub)
- `LEAGUE_URLS` — dict of active/coming-soon leagues with URLs and icons (EPL and NBA settings; hub already had this)
- Template `DIRS` entry for `vinosports-core` templates — falls back from Docker volume mount path to site-packages path

### Auth URL handling

Cross-port CSRF constraint drives the URL strategy:
- **Login/signup** — always link to hub (`{{ hub_url }}/login/`)
- **Logout** — POST to current app's logout endpoint (CSRF tokens don't work cross-port in dev)
- **Theme toggle** — POST to current app's `website:theme_toggle`
- **Profile** — links to `website:account` on league apps, `hub:account` on hub

### Template discovery

The `vinosports-core` package templates live at `packages/vinosports-core/src/vinosports/templates/`. Django finds them via a `DIRS` entry that checks the Docker volume mount path first, falling back to the pip-installed site-packages path:

```python
*(
    [Path("/packages/vinosports-core/src/vinosports/templates")]
    if Path("/packages/vinosports-core/src/vinosports/templates").is_dir()
    else [Path(__import__("vinosports").__path__[0]) / "templates"]
),
```

The `pyproject.toml` for `vinosports-core` includes a `force-include` directive to ensure templates are bundled in wheel builds.

## Files

### New
- `packages/vinosports-core/src/vinosports/templates/vinosports/components/global_navbar.html`
- `packages/vinosports-core/src/vinosports/context_processors.py`
- `apps/epl/website/templates/website/components/sidebar.html`
- `apps/nba/templates/website/components/sidebar.html`

### Modified
- `apps/hub/config/settings.py` — `CURRENT_LEAGUE`, template DIRS, context processor swap
- `apps/epl/config/settings.py` — `CURRENT_LEAGUE`, `LEAGUE_URLS`, template DIRS, context processor swap
- `apps/nba/config/settings.py` — same
- `apps/hub/hub/templates/hub/base.html` — swapped navbar include
- `apps/epl/website/templates/website/base.html` — global navbar + sidebar/content flex layout + mobile drawer
- `apps/nba/templates/website/base.html` — same
- `apps/epl/website/static/website/css/styles.css` — sidebar CSS
- `apps/nba/website/static/website/css/styles.css` — sidebar CSS
- `apps/hub/hub/static/hub/css/styles.css` — dropdown-link styles
- `packages/vinosports-core/pyproject.toml` — template force-include

### Superseded (still on disk, no longer included)
- `apps/hub/hub/templates/hub/components/navbar.html`
- `apps/epl/website/templates/website/components/navbar.html`
- `apps/nba/templates/website/components/navbar.html`
- `apps/hub/hub/context_processors.py`
