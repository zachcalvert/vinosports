# 0037: Lightweight JS Bundling with esbuild

**Date:** 2026-04-01

## Overview

Introduce esbuild as a JS bundler to replace CDN `<script>` tags and scattered inline scripts with proper `import`-based modules. Same DHA philosophy — Django templates, HTMX, Alpine.js — just with organized, bundled JavaScript. Mirrors the Tailwind CDN-to-build evolution from 0034.

## Motivation

The frontend JS has grown organically alongside the DHA stack:

**Current state:**
- **7 CDN script tags** across base templates: HTMX (×4), htmx-ext-ws (×3), htmx-ext-head-support (×4), Alpine.js (×1), Chart.js + date-fns adapter (×4 account pages)
- **~70 lines of inline `<script>`** duplicated across 3 league base templates: CSRF config, `showToast()`, activity toast auto-fade + anonymous nudge
- **6 static JS files**, 4 of which are no-op placeholders (`payout-preview.js` in EPL/NBA/NFL)
- **No shared JS module system** — utilities like `showToast()` can't be imported, only copy-pasted
- **Version management is manual** — updating HTMX means editing 4 files

This works, but every new feature adds more scattered JS. The inbox (0035) needs badge update logic in every base template. The admin dashboard (0039) needs WebSocket auto-refresh JS. The profile page (0038) needs Lightweight Charts. Without a bundler, each of these becomes another inline `<script>` block or CDN tag to duplicate across templates.

**What we want:**
- Write `import` statements instead of CDN `<script>` tags
- Share utilities (CSRF config, toast system, WebSocket helpers) across leagues via modules
- One place to update dependency versions (`package.json`)
- Build-time output: a hashed `.js` file served by WhiteNoise, like Tailwind CSS
- No framework change — still Django templates with HTMX + Alpine

## Why esbuild

| Criteria | esbuild | Vite | Webpack |
|----------|---------|------|---------|
| **Speed** | ~10ms builds | ~200ms (uses esbuild under the hood) | Seconds |
| **Config** | Zero-config for basic bundling | Moderate | Heavy |
| **Binary** | Single Go binary, no Node runtime needed at build time | Requires Node | Requires Node |
| **Size** | ~9MB binary | ~30MB + node_modules | ~50MB + node_modules |
| **Watch mode** | Built-in, ~5ms rebuilds | Built-in (HMR, but we don't need it) | Built-in |
| **Maturity** | Stable, used by Vite internally | Stable | Stable |

esbuild wins on simplicity and speed. It follows the same pattern as the Tailwind standalone CLI: download a binary, run it at build time, output a static file. No Node.js runtime required in the Docker image.

**However:** esbuild requires Node.js for `npm install` to resolve packages from `node_modules/`. The binary itself doesn't need Node, but the dependency resolution does. Two approaches:

1. **Use npm + esbuild binary** — Install deps with npm at build time, then run esbuild binary to bundle. Requires adding Node to the Docker image.
2. **Use esbuild with vendored `node_modules`** — Check `node_modules/` into the repo (small, since we have few deps) and run the esbuild binary without Node. Avoids Node in Docker but pollutes the repo.

**Recommendation:** Option 1. Adding Node to the Docker image is a one-line `RUN` (install via apt or use a multi-stage build). It's lightweight and standard. The `node_modules/` stays gitignored.

## Plan

### Phase 1: Tooling Setup

#### 1.1 Add `package.json`

```json
{
  "private": true,
  "name": "vinosports",
  "scripts": {
    "js:build": "esbuild frontend/main.js --bundle --minify --sourcemap --outfile=packages/vinosports-core/src/vinosports/static/vinosports/js/app.js --format=iife --target=es2020",
    "js:watch": "esbuild frontend/main.js --bundle --sourcemap --outfile=packages/vinosports-core/src/vinosports/static/vinosports/js/app.js --format=iife --target=es2020 --watch"
  },
  "dependencies": {
    "htmx.org": "^2.0.4",
    "lightweight-charts": "^4.2.0"
  },
  "devDependencies": {
    "esbuild": "^0.24.0"
  }
}
```

Notes:
- **Alpine.js stays on CDN.** Alpine uses `x-data`, `x-show`, `@click` directives in HTML templates — it must initialize before the DOM is interactive and doesn't benefit from bundling. The `defer` CDN script is the recommended approach.
- **Phosphor Icons stays on CDN.** It's a CSS stylesheet, not JS.
- **HTMX moves into the bundle.** It's JS that we `import` and it auto-registers on `window`.
- **Lightweight Charts** is the new addition. Import only the `createChart` function (tree-shakeable).
- **Chart.js is removed.** Lightweight Charts replaces it for balance history.

#### 1.2 Create `frontend/` Directory

```
frontend/
  main.js              # Global entry point (loaded on every page)
  lib/
    csrf.js            # HTMX CSRF config
    toasts.js          # showToast() + error handlers
    activity-feed.js   # Activity toast auto-fade + MutationObserver
    inbox-badge.js     # Inbox badge WebSocket update (from 0035)
  charts/
    balance-history.js # Lightweight Charts balance history (from 0038)
```

This directory is **source only** — not served by Django, not in `static/`. esbuild compiles it into a single `app.js` in the static directory.

#### 1.3 Global Entry Point

```javascript
// frontend/main.js

// HTMX — separate module ensures window.htmx is set before vendor extensions run.
// IMPORTANT: ES imports are hoisted, so `import htmx ...; window.htmx = htmx;`
// in THIS file would execute AFTER the vendor imports. The htmx-init module
// guarantees the global is set before any extension calls htmx.defineExtension().
import "./lib/htmx-init.js";

// HTMX extensions (vendored, reference global htmx)
import "./vendor/htmx-ext-ws.js";
import "./vendor/htmx-ext-head-support.js";

// Shared utilities
import { initCsrf } from "./lib/csrf.js";
import { initToasts } from "./lib/toasts.js";
import { initActivityFeed } from "./lib/activity-feed.js";
import { initInboxBadge } from "./lib/inbox-badge.js";

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", function () {
  initCsrf();
  initToasts();
  initActivityFeed();
  initInboxBadge();
});
```

#### 1.4 Extract Inline Scripts to Modules

**`frontend/lib/csrf.js`:**
```javascript
export function initCsrf() {
  document.body.addEventListener("htmx:configRequest", function (e) {
    var csrfCookie = document.cookie
      .split("; ")
      .find(function (c) { return c.startsWith("csrftoken="); });
    if (csrfCookie) {
      e.detail.headers["X-CSRFToken"] = csrfCookie.split("=")[1];
    }
  });
}
```

**`frontend/lib/toasts.js`:**
```javascript
export function showToast(message) {
  var container = document.getElementById("notifications");
  if (!container) return;
  // ... existing showToast logic
}

export function initToasts() {
  document.body.addEventListener("htmx:responseError", function () {
    showToast("Something went wrong. Please try again.");
  });
  document.body.addEventListener("htmx:sendError", function () {
    showToast("Network error. Check your connection.");
  });
}
```

**`frontend/lib/activity-feed.js`:**
```javascript
export function initActivityFeed() {
  var container = document.getElementById("activity-toasts");
  if (!container) return;
  // ... existing MutationObserver logic
  // Note: the anonymous nudge URL needs to be data-driven (see Phase 2)
}
```

#### 1.5 Handle HTMX Extensions

The HTMX WebSocket and head-support extensions aren't published as clean npm packages. Two options:

1. **Vendor them** — Download the extension JS files into `frontend/vendor/` and import them. They're small (~5KB each) and rarely change.
2. **Keep on CDN** — Only bundle HTMX core, leave extensions as CDN `<script>` tags after the bundle.

**Recommendation:** Vendor them. The whole point is eliminating CDN dependencies. Download once, commit to `frontend/vendor/`, import in `main.js`.

### Phase 2: Template Changes

#### 2.1 Replace CDN Scripts

**Before** (in each of 4 base templates):
```html
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<script src="https://unpkg.com/htmx-ext-ws@2.0.2/ws.js"></script>
<script src="https://unpkg.com/htmx-ext-head-support@2.0.2/head-support.js"></script>
```

**After** (in `head_design_system.html`, loaded once):
```html
<script src="{% static 'vinosports/js/app.js' %}"></script>
```

This moves from 7-12 CDN script tags scattered across 4 base templates to 1 static script tag in 1 shared include.

#### 2.2 Remove Inline Scripts

Delete the `<script>` blocks for CSRF config, `showToast()`, and activity-feed auto-fade from all 3 league base templates + hub base. These now live in the bundle.

#### 2.3 Data Attributes for Template-Dependent Values

Some inline scripts reference Django template variables (e.g., `{% if user.is_authenticated %}`, `{% url "..." %}`). These can't live in a JS module. Solution: pass values via `data-` attributes on the `<body>` tag:

```html
<body class="h-full theme-page"
      hx-boost="true"
      hx-ext="head-support,ws"
      data-authenticated="{{ user.is_authenticated|yesno:'true,false' }}"
      data-signup-url="{% url 'hub:signup' %}"
      data-show-activity="{{ show_activity_toasts|yesno:'true,false' }}">
```

The JS modules read these:
```javascript
// frontend/lib/activity-feed.js
export function initActivityFeed() {
  var isAnon = document.body.dataset.authenticated !== "true";
  var signupUrl = document.body.dataset.signupUrl;
  var showActivity = document.body.dataset.showActivity === "true";
  if (!showActivity) return;
  // ...
}
```

#### 2.4 Page-Specific JS via `{% block extra_js %}`

Not everything belongs in the global bundle. Page-specific JS (like the balance history chart) should load only on pages that need it. Two approaches:

**a) Separate entry points** — Build multiple bundles:
```json
{
  "scripts": {
    "js:build": "esbuild frontend/main.js frontend/charts/balance-history.js --bundle --minify --splitting --outdir=... --format=esm"
  }
}
```

**b) Dynamic import** — Keep one bundle but lazy-load page-specific code:
```javascript
// In the balance history template's extra_js block:
<script type="module">
  import { renderBalanceChart } from "/static/vinosports/js/app.js";
  renderBalanceChart(document.getElementById("balance-chart"), "{{ api_url }}");
</script>
```

**Recommendation:** Start with approach (b) — a single bundle with exports. The bundle is small enough that splitting isn't necessary yet. Page-specific templates use `<script type="module">` in `{% block extra_js %}` to call exported functions. If the bundle grows past ~200KB, revisit splitting.

Alternatively, the simplest approach: **page-specific entry points as separate bundles**. esbuild can compile multiple entry points in one command:

```json
"js:build": "esbuild frontend/main.js frontend/pages/balance-history.js --bundle --minify --outdir=packages/vinosports-core/src/vinosports/static/vinosports/js/"
```

This produces `app.js` (global, every page) and `balance-history.js` (loaded only on account/profile pages via `{% block extra_js %}`). Clean separation, no dynamic imports, simple mental model.

### Phase 3: Build Pipeline

#### 3.1 Docker Integration

Update the Dockerfile to install Node.js (for npm) and run esbuild at build time:

```dockerfile
# After Tailwind CLI download...

# Install Node.js (for npm package resolution)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install JS dependencies
COPY package.json package-lock.json ./
RUN npm ci --production

# Copy frontend source
COPY frontend/ frontend/

# Bundle JS
RUN npx esbuild frontend/main.js \
    --bundle --minify --sourcemap \
    --outfile=packages/vinosports-core/src/vinosports/static/vinosports/js/app.js \
    --format=iife --target=es2020
```

This runs **before** `collectstatic`, so WhiteNoise picks up the bundled JS with content-hashed filenames.

**Build order in Dockerfile:**
1. Install Python deps (vinosports-core, psycopg2, whitenoise)
2. Install Node.js + npm deps
3. Copy source code
4. Build Tailwind CSS
5. Build JS bundle ← new
6. `collectstatic` (picks up both tailwind-out.css and app.js)

#### 3.2 Docker Compose (Dev Watcher)

Add a JS watcher service alongside the existing Tailwind watcher:

```yaml
# docker-compose.yml
jsbuild:
  <<: *app-build
  command: ["npx", "esbuild", "frontend/main.js",
    "--bundle", "--sourcemap",
    "--outfile=/packages/vinosports-core/src/vinosports/static/vinosports/js/app.js",
    "--format=iife", "--target=es2020",
    "--watch"]
  volumes:
    - ./frontend:/app/frontend
    - ./package.json:/app/package.json
    - ./node_modules:/app/node_modules
    - ./packages/vinosports-core/src:/packages/vinosports-core/src
  depends_on: []
```

esbuild's watch mode rebuilds in ~5ms on file change — faster than the Tailwind watcher.

#### 3.3 Makefile Commands

```makefile
js:
	npx esbuild frontend/main.js \
		--bundle --minify --sourcemap \
		--outfile=packages/vinosports-core/src/vinosports/static/vinosports/js/app.js \
		--format=iife --target=es2020

js-watch:
	npx esbuild frontend/main.js \
		--bundle --sourcemap \
		--outfile=packages/vinosports-core/src/vinosports/static/vinosports/js/app.js \
		--format=iife --target=es2020 \
		--watch
```

#### 3.4 `.gitignore`

```
# JS build output (like tailwind-out.css)
packages/vinosports-core/src/vinosports/static/vinosports/js/app.js
packages/vinosports-core/src/vinosports/static/vinosports/js/app.js.map
node_modules/
```

The `frontend/vendor/` directory (HTMX extensions) **is** committed since those are vendored source files.

### Phase 4: Cleanup

#### 4.1 Remove CDN Script Tags

Delete from all base templates:
- `htmx.org@2.0.4` (4 occurrences)
- `htmx-ext-ws@2.0.2` (3 occurrences)
- `htmx-ext-head-support@2.0.2` (4 occurrences)

Delete from account templates:
- `chart.js@4` (4 occurrences)
- `chartjs-adapter-date-fns@3` (4 occurrences)

Total: **19 CDN script tags removed.**

#### 4.2 Remove Inline Scripts

Delete from 3 league base templates:
- CSRF config block (~10 lines each)
- `showToast()` + error handlers (~20 lines each)
- Activity toast auto-fade + nudge (~35 lines each)

Total: **~195 lines of inline JS removed** (65 lines × 3 leagues).

#### 4.3 Remove No-Op Static Files

Delete the placeholder files:
- `epl/website/static/epl_website/js/payout-preview.js`
- `nba/website/static/nba_website/js/payout-preview.js`
- `nfl/website/static/nfl_website/js/payout-preview.js`

Keep `local-times.js` files — evaluate whether to fold them into the bundle or keep as page-specific scripts.

#### 4.4 Update `head_design_system.html`

```html
{% load static %}
<!-- Tailwind CSS (compiled at build time) -->
<link rel="stylesheet" href="{% static 'vinosports/css/tailwind-out.css' %}">

<!-- Google Fonts -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Epilogue:ital,wght@0,400;0,700;0,800;0,900;1,900&family=Public+Sans:wght@400;600;700;800&family=Roboto+Mono:wght@400;500;700&display=swap" rel="stylesheet">

<!-- Phosphor Icons (duotone) -->
<link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/duotone/style.css">

<!-- Shared design-system CSS -->
<link rel="stylesheet" href="{% static 'vinosports/css/design-system.css' %}">

<!-- Alpine.js (stays on CDN — declarative HTML directives, no bundling benefit) -->
<script defer src="https://unpkg.com/alpinejs@3.14.8/dist/cdn.min.js"></script>

<!-- App JS bundle (HTMX + extensions + shared utilities) -->
<script src="{% static 'vinosports/js/app.js' %}"></script>
```

## What Stays on CDN

| Dependency | Why |
|------------|-----|
| **Alpine.js** | Declarative HTML directives — needs to initialize before DOM interaction, recommended as CDN by Alpine docs. No import/export usage. |
| **Phosphor Icons** | CSS stylesheet, not JS. |
| **Google Fonts** | CSS, loaded from Google's CDN. |

Everything else moves into the bundle.

## Migration Checklist

The migration can be done incrementally — the bundle and CDN scripts can coexist during transition:

1. Set up `package.json`, `frontend/`, esbuild config
2. Build `app.js` with just HTMX + extensions (verify HTMX still works)
3. Extract inline scripts to modules one at a time (CSRF → toasts → activity feed)
4. Remove corresponding CDN tags and inline `<script>` blocks
5. Add Lightweight Charts as a page-specific bundle (feeds directly into 0038)
6. Remove Chart.js CDN tags from account templates
7. Clean up placeholder static files

Each step is independently deployable. If something breaks, revert the one step.

## Files Affected

| Area | Files |
|------|-------|
| New: frontend source | `frontend/main.js`, `frontend/lib/*.js`, `frontend/vendor/*.js` |
| New: package config | `package.json`, `package-lock.json` |
| Build: Docker | `Dockerfile` (add Node.js, npm ci, esbuild) |
| Build: Compose | `docker-compose.yml` (add jsbuild watcher service) |
| Build: Make | `Makefile` (add `js`, `js-watch` targets) |
| Build: gitignore | `.gitignore` (add app.js, node_modules) |
| Templates: shared | `vinosports/includes/head_design_system.html` |
| Templates: base | `hub/base.html`, `epl_website/base.html`, `nba_website/base.html`, `nfl_website/base.html` |
| Templates: account | `hub/account.html`, `epl_website/account.html`, `nba_website/account.html`, `nfl_website/account.html` |
| Cleanup: static | Delete 3 placeholder `payout-preview.js` files |

## Testing

- **Smoke test:** Every page loads without JS console errors. HTMX forms submit. Alpine dropdowns toggle. WebSocket connections establish.
- **Build test:** `make js` produces `app.js` in the expected location. `collectstatic` picks it up.
- **Watch test:** Editing a file in `frontend/` triggers a rebuild. Browser refresh picks up changes.
- **Docker test:** `make up` builds the image with JS bundle included. Production-like `collectstatic` hashes the filename.
- **No-JS fallback:** Pages degrade gracefully when JS fails to load (forms still submit, links still navigate — this is the DHA guarantee).
