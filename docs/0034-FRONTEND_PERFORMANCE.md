# 0034: Frontend Performance — Tailwind Build, Alpine.js, hx-boost

**Date:** 2026-03-31

## Overview

Eliminated the flash of unstyled content (FOUC) visible on every page load and modernized the frontend stack. Tailwind CSS moved from browser-side CDN compilation to build-time static CSS. Alpine.js replaced scattered vanilla JS for interactive behavior. HTMX's `hx-boost` now intercepts internal navigation, giving the site SPA-like page transitions without a full JS framework. WhiteNoise upgraded to compressed manifest storage for production static file optimization.

## Motivation

Every page on vinosports.com showed content unstyled for ~500ms before snapping into the correct layout. Users experienced this on every click because each navigation was a full page reload.

Root causes:

1. **Tailwind CSS ran in the browser.** The CDN script at `cdn.tailwindcss.com` JIT-compiled utility classes at runtime. The browser had to download the script, parse it, scan the DOM for classes, generate CSS, and inject it — all before the page could render correctly. This is the Play CDN, explicitly not recommended for production.

2. **No navigation caching.** Every link click triggered a full page reload: re-download CSS, re-parse fonts, re-compile Tailwind. The Tailwind CDN also broke bfcache (back/forward cache), which required a `pageshow` hack to force-reload on back-button navigation.

3. **No static file optimization.** WhiteNoise served static files without content hashing or compression. Browsers re-downloaded identical CSS on every visit.

4. **Fragile inline JS.** Sidebar toggles, dropdown menus, and toast auto-fade were implemented as ~80 lines of vanilla JS IIFEs spread across 4 base templates and 1 shared component. Each used `getElementById` + `classList.toggle` patterns that were verbose and duplicated per league.

## What Changed

### 1. Tailwind CDN → Build-Time CLI

Replaced the CDN `<script>` tag with the Tailwind CLI standalone binary (no Node.js required). CSS is now a normal static file, parsed by the browser like any stylesheet — zero compilation delay.

**New files:**
- `tailwind.config.js` — extracted from the inline `tailwind.config` object that was embedded in `head_design_system.html`
- `packages/vinosports-core/src/vinosports/static/vinosports/css/tailwind.css` — input file with `@tailwind` directives and base font-family rules
- `packages/vinosports-core/src/vinosports/static/vinosports/css/tailwind-out.css` — compiled output (gitignored, built at image build time and by the dev watcher)

**Modified files:**
- `head_design_system.html` — removed CDN script (58 lines of inline config), replaced with `<link>` to compiled `tailwind-out.css`
- `Dockerfile` — downloads Tailwind CLI standalone binary, builds minified CSS before `collectstatic`
- `docker-compose.yml` — added `tailwind` service that watches template files and rebuilds CSS on change (uses `--watch --poll` for Docker volume compatibility, `stdin_open: true` to prevent exit)
- `Makefile` — added `make tw` (one-shot build) and `make tw-watch` (start watcher)
- `.gitignore` — added `tailwind-out.css`

**Removed:**
- `pageshow` bfcache reload hack from all 3 league base templates (only existed because "Tailwind CDN doesn't re-run after back/forward navigation")

### 2. hx-boost for SPA-Like Navigation

Added `hx-boost="true"` and `hx-ext="head-support"` to all 4 base template `<body>` tags (EPL, NBA, NFL, Hub). HTMX now intercepts internal link clicks, fetches the target page via AJAX, and swaps the `<body>` content — CSS, JS, and fonts stay loaded.

The `head-support` extension (loaded from unpkg CDN) ensures `<title>`, league-specific stylesheets, and other `<head>` elements update correctly when navigating between leagues (e.g., `/epl/` → `/nba/`).

This is a progressive enhancement — forms and links degrade to normal behavior if JS fails.

### 3. Alpine.js

Added Alpine.js 3.x via CDN (`defer` attribute) in `head_design_system.html`. Converted interactive behavior from imperative vanilla JS to declarative Alpine directives:

**Global navbar** (`global_navbar.html`):
- League dropdown: `x-data="{ open: false }"` + `x-show` + `@click.outside` (was 12 lines of addEventListener/classList.toggle)
- User dropdown: same pattern (was 12 lines)
- Sidebar hamburger: `@click="$dispatch('toggle-sidebar')"` (was getElementById + classList.toggle)
- Removed the entire `<script>` block (44 lines of vanilla JS)

**Mobile sidebar overlay** (all 3 league base templates):
- `x-data="{ open: false }"` + `@toggle-sidebar.window` + `@keydown.escape.window` (was getElementById + classList IIFE per league)
- Backdrop click: `@click="open = false"` (was addEventListener)
- Close button: `@click="open = false"` (was addEventListener)
- Added `x-cloak` to prevent flash of dropdown/sidebar content before Alpine initializes

**What was NOT converted:**
- HTMX CSRF token injection script (HTMX-specific, not toggle logic)
- Activity toast MutationObserver (complex DOM creation with league-specific URLs, not a good Alpine fit)
- `showToast()` function (imperative DOM creation for error handling)

### 4. WhiteNoise Optimization

Set `STORAGES["staticfiles"]["BACKEND"]` to `whitenoise.storage.CompressedManifestStaticFilesStorage` for production (when S3 endpoint is configured). This enables:
- Content-hashed filenames (e.g., `styles.a1b2c3d4.css`)
- `Cache-Control: max-age=315360000` (10 years) for hashed files
- Automatic gzip compression of CSS/JS

Development and test environments continue using Django's default `StaticFilesStorage` (manifest storage requires `collectstatic` which doesn't run in dev/test).

## Docker Services

The `tailwind` service brings the total from 6 to 7:

| Service | Description |
|---------|-------------|
| `db` | PostgreSQL |
| `redis` | Redis (Celery broker + Channels layer) |
| `web` | Django dev server (all leagues) |
| `tailwind` | Tailwind CSS watcher (rebuilds on template changes) |
| `worker` | Celery worker (`-Q epl,nba,nfl`) |
| `beat` | Celery beat scheduler |

## Dev Workflow

```bash
make up          # builds images, starts all services, runs initial Tailwind build
make tw          # one-shot Tailwind build (minified)
make tw-watch    # start Tailwind watcher in foreground
```

The `tailwind` service starts automatically with `make up` and watches for template changes. When you edit an HTML template, the watcher recompiles CSS within ~1s. Django's dev server picks up the changed file via the shared volume mount.

**Important:** The `tailwind-out.css` file is gitignored. It's built:
- In Docker: by the `tailwind` watcher service (dev) or in the Dockerfile (production)
- In CI: by the Dockerfile's `RUN tailwindcss ... --minify` step before `collectstatic`

## Frontend Stack Summary

| Layer | Tool | Role |
|-------|------|------|
| Styling | Tailwind CSS 3.4 (build-time) | Utility-first CSS |
| Design tokens | `design-system.css` (hand-written) | CSS custom properties, shared components |
| Interactivity | Alpine.js 3.x | Declarative UI state (dropdowns, sidebars, toggles) |
| Server communication | HTMX 2.0 | Partial page updates, WebSocket connections |
| Navigation | HTMX hx-boost + head-support | SPA-like transitions without full reloads |
| Icons | Phosphor Icons (duotone) | Icon set via CDN |

This is the "DHA stack" (Django + HTMX + Alpine) — a well-established pattern for server-rendered apps that need client-side interactivity without the complexity of React/Vue/Svelte.
