# 0007: Centralized Auth

**Date:** 2026-03-23

## Problem

User registration and login were duplicated across each league app. The EPL app's `SignupView` depended on a `SiteSettings` model whose migration had never been created, causing a 500 error when visiting `/signup/` on the hub (which redirected to EPL). More broadly, having auth scattered across league apps contradicted the architecture of a single shared user account.

## Decision

Move all user record management — signup, login, logout, and registration settings — into the hub app. The hub becomes the single auth provider. League apps redirect to hub for login/signup and keep only a thin local logout.

## What Changed

### Hub (new auth home)

| File | Change |
|------|--------|
| `hub/models.py` | New `SiteSettings` model (registration caps, singleton pattern) |
| `hub/forms.py` | Added `SignupForm`, `LoginForm` |
| `hub/views.py` | Added `SignupView`, `LoginView`, `LogoutView` |
| `hub/urls.py` | Added `/signup/`, `/login/`, `/logout/` routes |
| `hub/admin.py` | `UserAdmin` (email-based fieldsets, balance inline) + `SiteSettingsAdmin` |
| `hub/templates/hub/signup.html` | Registration form (extends hub base) |
| `hub/templates/hub/login.html` | Login form (extends hub base) |
| `hub/templates/hub/components/navbar.html` | Local auth links + logout button for authenticated users |
| `config/settings.py` | `LOGIN_URL = "/login/"` (was redirect to EPL) |
| `hub/migrations/0001_initial.py` | Creates `hub_sitesettings` table |

### EPL (auth removed)

| File | Change |
|------|--------|
| `website/models.py` | `SiteSettings` removed (emptied) |
| `website/views.py` | `SignupView`, `LoginView` removed. Thin `LogoutView` kept |
| `website/urls.py` | `/login/` and `/signup/` now `RedirectView` to hub. `/logout/` stays local |
| `website/templates/.../navbar.html` | Login/signup links point to `{{ hub_url }}` |
| `config/settings.py` | `LOGIN_URL = HUB_URL + "/login/"` |

### NBA (auth removed)

| File | Change |
|------|--------|
| `website/views.py` | `SignupView`, `LoginView` removed. Thin `LogoutView` kept |
| `website/urls.py` | `/login/` and `/signup/` now `RedirectView` to hub. `/logout/` stays local |
| `templates/.../navbar.html` | Login/signup links point to `{{ hub_url }}` |
| `config/settings.py` | `LOGIN_URL = HUB_URL + "/login/"` |

### Core (unchanged)

The `User` model stays in `vinosports-core`. No changes to the shared package.

## How Cross-App Sessions Work

All three apps (hub, EPL, NBA) share:

- **Same PostgreSQL database** — one `django_session` table
- **Same `SECRET_KEY`** — session cookies are cryptographically compatible
- **Same `sessionid` cookie name** — Django's default
- **Same cookie domain** — `localhost` (cookies are shared across ports)

This means a user who logs in on hub:7999 is automatically authenticated on epl:8000 and nba:8001. Logging out from any app clears the session everywhere.

### Why logout stays local

CSRF validation checks the `Origin` / `Referer` header against the server's host. A form on epl:8000 cannot POST to hub:7999 because the origin mismatch causes Django's CSRF middleware to reject the request. Each league app keeps a thin `LogoutView` that calls `django.contrib.auth.logout()` locally — since the session is shared, this logs the user out globally.

## Signup Flow

1. User visits hub:7999/signup/ (or is redirected from a league app)
2. `SignupView.get()` checks `SiteSettings.max_users` — shows closed message if at cap
3. `SignupView.post()` validates form, then inside `transaction.atomic()`:
   - Re-checks cap with `SiteSettings.load_for_update()` (row-level lock)
   - Creates `User`, `UserBalance`, `BalanceTransaction` (signup bonus)
4. Auto-login via `django.contrib.auth.login()`
5. Redirect to hub homepage

## Admin

Hub's Django admin (`localhost:7999/admin/`) now includes:

- **UserAdmin** — email-based (no username), list with email/display_name/is_staff/is_bot/date_joined, balance inline, search by email or display name
- **SiteSettingsAdmin** — singleton (no add/delete), controls max_users and closed message
