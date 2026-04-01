# 0039: Admin Dashboard Enhancements

**Date:** 2026-04-01

## Overview

Four improvements to the admin dashboard: auto-refreshing data via WebSockets, including NFL in aggregate stats, linking rows to user profiles, and adding dedicated full-page views for recent bets/parlays and recent comments.

## Motivation

The admin dashboard at `/admin-dashboard/` provides a cross-league overview but has friction points: data goes stale unless you manually reload, NFL is absent from aggregate counts, there's no quick way to jump to a user's profile from recent activity rows, and "View all" just appends more items inline with no way to browse the full history.

## Current State

### Dashboard View (`hub/views.py`)
- `AdminDashboardView`: Main page showing 6 stat cards (Users, Active Bets, Active Parlays, Comments, Total Bets, In Play Stakes) plus league breakdown cards for EPL and NBA only.
- `AdminBetsPartialView`: HTMX partial merging EPL + NBA bet slips and parlays via `_admin_merged_querysets()` heap merge. Paginated at 5 items per page with max offset 500.
- `AdminCommentsPartialView`: HTMX partial merging EPL + NBA comments. Same pagination.
- `AdminUsersPartialView`: HTMX partial showing recent non-bot signups.
- All behind `SuperuserRequiredMixin`.

### Templates
- `hub/templates/hub/admin_dashboard.html`: Main dashboard with stat cards and three HTMX panels (`hx-get` with `hx-trigger="load"`).
- `hub/templates/hub/partials/admin_bets_list.html`: Renders merged bet/parlay items with type badge, league badge, user name, match/game link, stake, status.
- `hub/templates/hub/partials/admin_comments_list.html`: Renders merged comments with league badge, username, match/game link, truncated body.
- `hub/templates/hub/partials/admin_bets_page.html` / `admin_comments_page.html`: Pagination partials for "View all" infinite scroll.

### WebSocket Infrastructure
- Existing consumers: `LiveUpdatesConsumer` (EPL, NBA, NFL) for score updates, `ActivityConsumer` for site-wide activity feed, `NotificationsConsumer` for per-user alerts.
- Channel layer: Redis-backed (`channels_redis`).
- ASGI routing: `config/asgi.py` with nested `URLRouter` per league prefix.

### NFL Betting
- `nfl.betting` has full models: `BetSlip`, `Parlay`, `ParlayLeg` — identical structure to EPL/NBA.
- NFL is **not** included in the admin dashboard's aggregate counts or recent activity queries.

## Plan

### Phase 1: Include NFL in Aggregate Stats and Recent Activity

#### 1.1 Update Stat Cards

In `AdminDashboardView.get_context_data()`, add NFL counts alongside EPL and NBA:

```python
# Current: only EPL + NBA
from epl.betting.models import BetSlip as EplBetSlip, Parlay as EplParlay
from nba.betting.models import BetSlip as NbaBetSlip, Parlay as NbaParlay

# Add:
from nfl.betting.models import BetSlip as NflBetSlip, Parlay as NflParlay

# Total bets
total_bets = (
    EplBetSlip.objects.count()
    + NbaBetSlip.objects.count()
    + NflBetSlip.objects.count()
)

# Total parlays
total_parlays = (
    EplParlay.objects.count()
    + NbaParlay.objects.count()
    + NflParlay.objects.count()
)

# Active (pending) bets and parlays — same pattern with .filter(status="PENDING")
# In-play stakes — same pattern summing stakes
```

#### 1.2 Add NFL League Breakdown Card

Add a third league card (red border) to the dashboard template alongside EPL (green) and NBA (blue):

```html
{# NFL breakdown card #}
<div class="bg-gray-800 rounded-lg p-4 border-l-4 border-red-500">
    <h3 class="text-sm font-medium text-gray-400 mb-2">NFL</h3>
    <div class="grid grid-cols-2 gap-2 text-sm">
        <div><span class="text-gray-400">Bets:</span> <span class="text-white">{{ nfl_bet_count }}</span></div>
        <div><span class="text-gray-400">Parlays:</span> <span class="text-white">{{ nfl_parlay_count }}</span></div>
        <div><span class="text-gray-400">Comments:</span> <span class="text-white">{{ nfl_comment_count }}</span></div>
    </div>
</div>
```

#### 1.3 Update Merged Querysets

`AdminBetsPartialView` and `AdminCommentsPartialView` currently merge EPL + NBA. Extend `_admin_merged_querysets()` to accept 3+ querysets:

```python
def _admin_merged_querysets(*querysets, limit=5, offset=0):
    """Heap-merge N querysets ordered by created_at descending."""
    import heapq

    iterators = []
    for qs in querysets:
        for obj in qs.order_by("-created_at")[offset:offset + limit * 2]:
            heapq.heappush(iterators, (-obj.created_at.timestamp(), id(obj), obj))

    results = []
    while iterators and len(results) < limit:
        _, _, obj = heapq.heappop(iterators)
        results.append(obj)

    return results
```

Call with all three leagues:

```python
# In AdminBetsPartialView
items = _admin_merged_querysets(
    epl_bets_qs, nba_bets_qs, nfl_bets_qs,
    epl_parlays_qs, nba_parlays_qs, nfl_parlays_qs,
    limit=ADMIN_PAGE_SIZE, offset=offset,
)
```

Add NFL league badge (red) to the template alongside EPL (green) and NBA (blue).

### Phase 2: Link Rows to User Profiles

#### 2.1 Bets & Parlays List

In `admin_bets_list.html`, wrap the user display name in a link to their public profile:

```html
{# Current #}
<span class="text-sm text-white">{{ item.user.display_name|default:item.user.email }}</span>

{# Updated #}
<a href="{% url 'profile' slug=item.user.slug %}"
   class="text-sm text-white hover:text-blue-400 transition">
    {{ item.user.display_name|default:item.user.email }}
</a>
```

#### 2.2 Comments List

Same change in `admin_comments_list.html`:

```html
{# Current #}
<span class="text-sm text-white">{{ comment.user.display_name|default:comment.user.email }}</span>

{# Updated #}
<a href="{% url 'profile' slug=comment.user.slug %}"
   class="text-sm text-white hover:text-blue-400 transition">
    {{ comment.user.display_name|default:comment.user.email }}
</a>
```

#### 2.3 Ensure `user.slug` is Available

The merged querysets already use `select_related("user")`, so `user.slug` is available without additional queries. Verify this in both views.

### Phase 3: Dedicated Full Pages for Bets/Parlays and Comments

#### 3.1 New Views

Create two new views for full-page browsing:

```python
class AdminBetsFullView(SuperuserRequiredMixin, TemplateView):
    """Full page: all bets & parlays, paginated."""
    template_name = "hub/admin_bets_full.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = int(self.request.GET.get("page", 1))
        per_page = 25

        # Merge all leagues
        items = _admin_merged_querysets(
            epl_bets_qs, nba_bets_qs, nfl_bets_qs,
            epl_parlays_qs, nba_parlays_qs, nfl_parlays_qs,
            limit=per_page, offset=(page - 1) * per_page,
        )

        context["items"] = items
        context["page"] = page
        context["has_next"] = len(items) == per_page
        context["has_prev"] = page > 1
        return context


class AdminCommentsFullView(SuperuserRequiredMixin, TemplateView):
    """Full page: all comments, paginated."""
    template_name = "hub/admin_comments_full.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = int(self.request.GET.get("page", 1))
        per_page = 25

        items = _admin_merged_querysets(
            epl_comments_qs, nba_comments_qs, nfl_comments_qs,
            limit=per_page, offset=(page - 1) * per_page,
        )

        context["items"] = items
        context["page"] = page
        context["has_next"] = len(items) == per_page
        context["has_prev"] = page > 1
        return context
```

#### 3.2 New URLs

```python
# hub/urls.py
path("admin-dashboard/bets/all/", views.AdminBetsFullView.as_view(), name="admin_bets_full"),
path("admin-dashboard/comments/all/", views.AdminCommentsFullView.as_view(), name="admin_comments_full"),
```

#### 3.3 Full Page Templates

Create `hub/templates/hub/admin_bets_full.html`:

```html
{% extends "hub/base.html" %}
{% block title %}All Bets & Parlays — Admin{% endblock %}

{% block content %}
<div class="max-w-4xl mx-auto px-4 py-8">
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-xl font-bold text-white">All Bets & Parlays</h1>
        <a href="{% url 'admin_dashboard' %}" class="text-sm text-gray-400 hover:text-white">
            ← Back to Dashboard
        </a>
    </div>

    <div class="space-y-2">
        {% for item in items %}
            {% include "hub/partials/admin_bets_row.html" with item=item %}
        {% empty %}
            <p class="text-gray-500 text-center py-8">No bets or parlays yet.</p>
        {% endfor %}
    </div>

    {# Pagination #}
    <div class="flex items-center justify-between mt-6">
        {% if has_prev %}
        <a href="?page={{ page|add:"-1" }}"
           class="text-sm text-gray-400 hover:text-white">← Previous</a>
        {% else %}
        <span></span>
        {% endif %}

        <span class="text-sm text-gray-500">Page {{ page }}</span>

        {% if has_next %}
        <a href="?page={{ page|add:"1" }}"
           class="text-sm text-gray-400 hover:text-white">Next →</a>
        {% else %}
        <span></span>
        {% endif %}
    </div>
</div>
{% endblock %}
```

Create `hub/templates/hub/admin_comments_full.html` with the same structure but using comment row partials.

#### 3.4 Extract Shared Row Partials

To avoid duplicating row markup between the dashboard partials and the full pages, extract:

- `hub/templates/hub/partials/admin_bets_row.html` — single bet/parlay row (user link + match link + stake + status).
- `hub/templates/hub/partials/admin_comments_row.html` — single comment row (user link + match link + body + timestamp).

Both `admin_bets_list.html` and `admin_bets_full.html` include these same row partials.

#### 3.5 Update "View All" Buttons

Change the "View all" button on the dashboard from HTMX infinite-scroll to a regular navigation link:

```html
{# Current: HTMX append #}
<button hx-get="{% url 'admin_dashboard_bets' %}?offset={{ next_offset }}"
        hx-swap="beforeend">View all</button>

{# Updated: Navigate to full page #}
<a href="{% url 'admin_bets_full' %}"
   class="text-sm text-blue-400 hover:text-blue-300">View all →</a>
```

The inline HTMX pagination (`?offset=...`) can remain for the first few pages of "load more" within the dashboard panel. The "View all" link at the bottom navigates to the dedicated page.

### Phase 4: Auto Data Refreshes via WebSocket

#### 4.1 New Admin WebSocket Consumer

Create a dedicated consumer for the admin dashboard:

```python
# hub/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class AdminDashboardConsumer(AsyncWebsocketConsumer):
    """Push real-time updates to the admin dashboard."""

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated or not user.is_superuser:
            await self.close()
            return

        await self.channel_layer.group_add("admin_dashboard", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("admin_dashboard", self.channel_name)

    async def dashboard_update(self, event):
        """Handle dashboard update events."""
        await self.send(text_data=json.dumps({
            "type": event["update_type"],
            "html": event.get("html", ""),
        }))
```

#### 4.2 WebSocket Routing

Add the admin WebSocket route to `config/asgi.py`:

```python
# In the WebSocket URLRouter
from hub.consumers import AdminDashboardConsumer

websocket_urlpatterns = [
    path("epl/", URLRouter(epl_ws_patterns)),
    path("nba/", URLRouter(nba_ws_patterns)),
    path("nfl/", URLRouter(nfl_ws_patterns)),
    path("ws/admin/", AdminDashboardConsumer.as_asgi()),  # new
]
```

#### 4.3 Send Updates on Key Events

Broadcast to the `admin_dashboard` group whenever relevant events occur. Hook into existing signal/task points:

**On new bet placed:**
```python
# In bet placement logic (e.g., epl/betting/views.py, nba/betting/views.py, nfl/betting/views.py)
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def _notify_admin_dashboard(update_type, html=""):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "admin_dashboard",
        {
            "type": "dashboard_update",
            "update_type": update_type,
            "html": html,
        },
    )
```

Call `_notify_admin_dashboard("new_bet")` after bet creation, `_notify_admin_dashboard("new_comment")` after comment creation, `_notify_admin_dashboard("new_user")` after signup.

#### 4.4 Client-Side WebSocket Handler

In `admin_dashboard.html`, connect to the WebSocket and refresh panels on updates:

```html
<script>
document.addEventListener("DOMContentLoaded", function() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/admin/`);

    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);

        // Refresh the relevant panel via HTMX
        switch (data.type) {
            case "new_bet":
                htmx.trigger("#bets-panel", "load");
                // Also update stat cards
                htmx.ajax("GET", "{% url 'admin_dashboard_stats' %}", {target: "#stats-cards", swap: "innerHTML"});
                break;
            case "new_comment":
                htmx.trigger("#comments-panel", "load");
                break;
            case "new_user":
                htmx.trigger("#users-panel", "load");
                htmx.ajax("GET", "{% url 'admin_dashboard_stats' %}", {target: "#stats-cards", swap: "innerHTML"});
                break;
        }
    };

    ws.onclose = function() {
        // Reconnect after 5 seconds
        setTimeout(() => location.reload(), 5000);
    };
});
</script>
```

#### 4.5 Stats Partial Endpoint

Extract the stat cards into an HTMX-refreshable partial so WebSocket events can trigger stat recalculation:

```python
class AdminStatsPartialView(SuperuserRequiredMixin, TemplateView):
    """Returns just the stat cards HTML for HTMX refresh."""
    template_name = "hub/partials/admin_stats.html"

    def get_context_data(self, **kwargs):
        # Same stat aggregation logic from AdminDashboardView
        ...
```

New URL:
```python
path("admin-dashboard/stats/", views.AdminStatsPartialView.as_view(), name="admin_dashboard_stats"),
```

#### 4.6 Debounce Updates

Multiple bets or comments can arrive in quick succession. Debounce client-side refreshes:

```javascript
let refreshTimers = {};

function debouncedRefresh(panelId, url, delay = 2000) {
    if (refreshTimers[panelId]) clearTimeout(refreshTimers[panelId]);
    refreshTimers[panelId] = setTimeout(() => {
        htmx.trigger(`#${panelId}`, "load");
    }, delay);
}
```

This prevents hammering the server when a batch of bot bets are placed simultaneously.

## Files Affected

| Area | Files |
|------|-------|
| Dashboard view | `hub/views.py` (AdminDashboardView, new full-page views, stats partial) |
| Dashboard template | `hub/templates/hub/admin_dashboard.html` |
| Bets partial | `hub/templates/hub/partials/admin_bets_list.html` |
| Comments partial | `hub/templates/hub/partials/admin_comments_list.html` |
| Row partials | `hub/templates/hub/partials/admin_bets_row.html` (new), `hub/templates/hub/partials/admin_comments_row.html` (new) |
| Full page templates | `hub/templates/hub/admin_bets_full.html` (new), `hub/templates/hub/admin_comments_full.html` (new) |
| Stats partial | `hub/templates/hub/partials/admin_stats.html` (new) |
| WebSocket consumer | `hub/consumers.py` (new) |
| ASGI routing | `config/asgi.py` |
| Hub URLs | `hub/urls.py` |
| Bet views (all leagues) | `epl/betting/views.py`, `nba/betting/views.py`, `nfl/betting/views.py` (notification hook) |
| Discussion views (all leagues) | `epl/discussions/views.py`, `nba/discussions/views.py`, `nfl/discussions/views.py` (notification hook) |

## Rollout Order

1. **Phase 1** — NFL in aggregate stats. Pure additive, low risk.
2. **Phase 2** — User profile links in rows. Template-only change.
3. **Phase 3** — Dedicated full pages. New views + templates, no changes to existing functionality.
4. **Phase 4** — WebSocket auto-refresh. New consumer + client JS + notification hooks across bet/comment creation.

## Testing

- **View tests:** `AdminBetsFullView` and `AdminCommentsFullView` return correct paginated results across all three leagues.
- **Merge tests:** `_admin_merged_querysets()` correctly interleaves 6 querysets (3 leagues x bets + parlays) by created_at.
- **WebSocket tests:** `AdminDashboardConsumer` rejects non-superusers, joins group, receives `dashboard_update` events.
- **Integration tests:** Placing a bet triggers admin dashboard WebSocket notification.
- **Template tests:** User names link to `/profile/<slug>/`. NFL badge renders with correct color.
