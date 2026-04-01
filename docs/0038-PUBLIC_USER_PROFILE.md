# 0038: Public User Profile Page

**Date:** 2026-04-01

## Overview

Enhance the public user profile page with a smaller profile image, a balance history chart, and a "biggest wins" highlight section. Turn the profile into a showcase of a user's betting identity.

## Motivation

The public profile (`/profile/<slug>/`) currently shows identity info, a performance ledger, badges, and (for bots) recent activity. It's functional but plain — there's no visual storytelling about a user's betting journey. The account page (`/account/`) already has a balance history chart via Chart.js, but it's private. Exposing a version publicly lets users show off their track record. Highlighting biggest wins gives the profile a "trophy case" feel that encourages competitive engagement.

## Current State

### Public Profile (`hub/views.py` — `ProfileView`)
- Displays: display name, avatar, bot profile info (if bot), win rate, rank, record, net profit, badge grid.
- For bots: shows recent bets, parlays, and comments from EPL and NBA.
- Route: `/profile/<slug>/`
- Template: `hub/templates/hub/profile.html`

### Account Page (`hub/views.py` — `AccountView`)
- Private, authenticated-only.
- Has a 10-day balance history chart powered by Chart.js.
- Fetches data from `BalanceHistoryAPI` at `/api/balance-history/<slug>/`.
- `BalanceHistoryAPI` returns daily `balance_after` snapshots for the last 10 days.

### Profile Image Handling
- `User.profile_image` (ImageField, upload to `profile_images/`).
- Avatar component (`epl_website/components/avatar.html` and similar) renders profile image or falls back to icon + background color.
- Currently renders at whatever size the container allows — no explicit small variant for profiles.

### Balance & Stats Models
- `UserBalance`: One-to-one with User, stores current balance.
- `BalanceTransaction`: Full ledger with `amount`, `balance_after`, `transaction_type`, `description`, `created_at`. Indexed on `(user, created_at)`.
- `UserStats`: Aggregated stats — `total_bets`, `total_wins`, `total_losses`, `total_staked`, `total_payout`, `net_profit`, `current_streak`, `best_streak`, `win_rate` property.

### Bet Models (for "biggest wins")
- EPL: `BetSlip` with `potential_payout`, `status` (WON/LOST/VOID/PENDING), `settled_at`.
- NBA: `BetSlip` with same fields.
- NFL: `BetSlip` with same fields.
- All inherit from `AbstractBetSlip` which has `stake`, `potential_payout`, `status`.
- `Parlay` models similarly have `potential_payout` and `status`.
- Actual profit = `potential_payout - stake` for won bets.

## Plan

### Phase 1: Profile Image at Smaller Size

#### 1.1 Create a Reusable Avatar Size Variant

The avatar component currently renders at the container's size. Add explicit size classes:

```html
{# hub/templates/hub/components/profile_avatar.html #}
{% comment %}
Renders a user avatar at a specified size.
Sizes: sm (32px), md (48px), lg (64px), xl (96px)
{% endcomment %}

{% with size=size|default:"lg" %}
<div class="relative inline-flex items-center justify-center rounded-full overflow-hidden flex-shrink-0
    {% if size == 'sm' %}w-8 h-8{% elif size == 'md' %}w-12 h-12{% elif size == 'lg' %}w-16 h-16{% elif size == 'xl' %}w-24 h-24{% endif %}"
    {% if not user.profile_image %}style="background-color: {{ user.avatar_bg }}"{% endif %}>
    {% if user.profile_image %}
        <img src="{{ user.profile_image.url }}" alt="{{ user.display_name }}"
             class="w-full h-full object-cover">
    {% else %}
        <i class="ph ph-{{ user.avatar_icon }}
            {% if size == 'sm' %}text-lg{% elif size == 'md' %}text-2xl{% elif size == 'lg' %}text-3xl{% elif size == 'xl' %}text-4xl{% endif %}
            text-white"></i>
    {% endif %}
</div>
{% endwith %}
```

#### 1.2 Update Profile Page

Replace the current large avatar on the profile page with the `md` size variant. The profile header should show the avatar at 48px alongside the display name and stats — compact enough to leave room for the new chart and wins sections below.

```html
{# In hub/templates/hub/profile.html — header section #}
<div class="flex items-center gap-4">
    {% include "hub/components/profile_avatar.html" with user=profile_user size="md" %}
    <div>
        <h1 class="text-xl font-bold text-white">{{ display_identity }}</h1>
        <p class="text-sm text-gray-400">Joined {{ profile_user.date_joined|timesince }} ago</p>
    </div>
</div>
```

### Phase 2: Balance History Chart on Public Profile

#### 2.1 Extend `BalanceHistoryAPI`

The existing API at `/api/balance-history/<slug>/` already returns data for any user by slug. Verify it doesn't require authentication (it currently uses `View`, not `LoginRequiredMixin`). If it does, ensure the endpoint is publicly accessible — balance history is not sensitive since it's derived from aggregate amounts, not individual bet details.

#### 2.2 Expand Time Range

The current API returns 10 days of history. For public profiles, a longer view is more interesting. Add a `days` query parameter:

```python
class BalanceHistoryAPI(View):
    def get(self, request, slug):
        days = min(int(request.GET.get("days", 30)), 90)  # default 30, max 90
        user = get_object_or_404(User, slug=slug)
        # ... existing logic but with `days` instead of hardcoded 10
```

#### 2.3 Add Chart to Profile Template

Add a Chart.js line chart below the stats section on the public profile. Reuse the same chart style from the account page:

```html
{# In hub/templates/hub/profile.html — after stats section #}
<div class="bg-gray-800 rounded-lg p-4 mt-6">
    <h3 class="text-sm font-medium text-gray-400 mb-3">Balance History</h3>
    <canvas id="balance-chart" class="w-full" style="height: 200px;"></canvas>
</div>

<script>
document.addEventListener("DOMContentLoaded", function() {
    fetch("{% url 'balance_history_api' slug=profile_user.slug %}?days=30")
        .then(r => r.json())
        .then(data => {
            const ctx = document.getElementById("balance-chart").getContext("2d");
            new Chart(ctx, {
                type: "line",
                data: {
                    labels: data.map(d => d.date),
                    datasets: [{
                        data: data.map(d => d.balance),
                        borderColor: "#22c55e",
                        backgroundColor: "rgba(34, 197, 94, 0.1)",
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: {
                            ticks: { color: "#9ca3af", maxTicksToShow: 6 },
                            grid: { display: false },
                        },
                        y: {
                            ticks: { color: "#9ca3af", callback: v => "$" + v },
                            grid: { color: "rgba(75, 85, 99, 0.3)" },
                        },
                    },
                },
            });
        });
});
</script>
```

#### 2.4 Handle Empty State

If a user has no transactions (new account), show a placeholder instead of an empty chart:

```html
{% if profile_user.balance_transactions.exists %}
    {# chart #}
{% else %}
    <p class="text-gray-500 text-sm text-center py-8">No balance history yet</p>
{% endif %}
```

### Phase 3: Highlight 3 Biggest Wins

#### 3.1 Query Biggest Wins

Build a cross-league query in `ProfileView.get_context_data()`:

```python
from itertools import heapq

def _get_biggest_wins(user, limit=3):
    """Return the top N biggest wins across all leagues, sorted by profit descending."""
    wins = []

    # EPL bets
    epl_bets = (
        EplBetSlip.objects.filter(user=user, status="WON")
        .annotate(profit=F("potential_payout") - F("stake"))
        .order_by("-profit")[:limit]
        .select_related("match", "match__home_team", "match__away_team")
    )
    for b in epl_bets:
        wins.append({
            "type": "bet",
            "league": "EPL",
            "league_color": "green",
            "profit": b.profit,
            "stake": b.stake,
            "payout": b.potential_payout,
            "description": f"{b.match.home_team.name} vs {b.match.away_team.name}",
            "pick": b.get_pick_display(),
            "odds": b.odds,
            "date": b.settled_at,
            "url": b.match.get_absolute_url(),
        })

    # NBA bets (same pattern)
    # NFL bets (same pattern)
    # EPL/NBA/NFL parlays (same pattern, profit = potential_payout - total_stake)

    # Sort all wins by profit descending, take top 3
    wins.sort(key=lambda w: w["profit"], reverse=True)
    return wins[:limit]
```

#### 3.2 Trophy Case Template

Display the top 3 wins as highlight cards:

```html
{# In hub/templates/hub/profile.html — after balance chart #}
{% if biggest_wins %}
<div class="mt-6">
    <h3 class="text-sm font-medium text-gray-400 mb-3">Biggest Wins</h3>
    <div class="space-y-3">
        {% for win in biggest_wins %}
        <a href="{{ win.url }}" class="block bg-gray-800 rounded-lg p-4 hover:bg-gray-750 transition">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                    {# Rank medal #}
                    <span class="text-lg
                        {% if forloop.counter == 1 %}text-yellow-400
                        {% elif forloop.counter == 2 %}text-gray-300
                        {% else %}text-amber-600{% endif %}">
                        {% if forloop.counter == 1 %}🥇{% elif forloop.counter == 2 %}🥈{% else %}🥉{% endif %}
                    </span>
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="text-xs px-1.5 py-0.5 rounded
                                {% if win.league == 'EPL' %}bg-green-900 text-green-300
                                {% elif win.league == 'NBA' %}bg-blue-900 text-blue-300
                                {% else %}bg-red-900 text-red-300{% endif %}">
                                {{ win.league }}
                            </span>
                            <span class="text-xs px-1.5 py-0.5 rounded bg-gray-700 text-gray-300">
                                {{ win.type|title }}
                            </span>
                        </div>
                        <p class="text-sm text-white mt-1">{{ win.description }}</p>
                        <p class="text-xs text-gray-400">{{ win.pick }} @ {{ win.odds }}</p>
                    </div>
                </div>
                <div class="text-right">
                    <p class="text-green-400 font-bold">+{{ win.profit|floatformat:2 }}</p>
                    <p class="text-xs text-gray-500">{{ win.date|date:"M j, Y" }}</p>
                </div>
            </div>
        </a>
        {% endfor %}
    </div>
</div>
{% endif %}
```

#### 3.3 Handle Edge Cases

- **No wins yet:** Don't render the section at all (handled by `{% if biggest_wins %}`).
- **Fewer than 3 wins:** Show however many exist.
- **Voided bets:** Excluded by filtering `status="WON"` only.
- **Currency formatting:** Use the profile user's currency preference for displaying amounts (the existing `format_currency` template filter handles this).

## Files Affected

| Area | Files |
|------|-------|
| Avatar component | `hub/templates/hub/components/profile_avatar.html` (new) |
| Profile template | `hub/templates/hub/profile.html` |
| Profile view | `hub/views.py` (`ProfileView`) |
| Balance API | `hub/views.py` (`BalanceHistoryAPI`) |
| Hub URLs | `hub/urls.py` (no new routes needed) |

## Testing

- **View tests:** `ProfileView` returns correct `biggest_wins` context for users with mixed EPL/NBA/NFL wins.
- **API tests:** `BalanceHistoryAPI` respects `days` param and clamps to 90.
- **Template tests:** Avatar renders at each size variant. Empty states render correctly.
- **Cross-league tests:** Biggest wins correctly merges and sorts across all three leagues + parlays.

## Rollout Order

1. **Phase 1** — Profile image sizing. Purely visual, no data changes.
2. **Phase 2** — Balance history chart. Reuses existing API with minor extension.
3. **Phase 3** — Biggest wins. New query logic + template section.
