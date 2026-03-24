# 0014 — Rewards Port (from epl-bets)

## Context

The `epl-bets` repo has a full rewards system with admin views, WebSocket-powered toast notifications, and real-time balance updates. The vinosports monorepo already has the **core models** (`Reward`, `RewardDistribution`, `RewardRule`) and the **broadcast function** (`_broadcast_rewards`) in `vinosports-core`, plus `NotificationConsumer` in both EPL and NBA. But the user-facing and admin-facing pieces were never ported over.

## What Already Exists

| Component | Location | Status |
|---|---|---|
| Reward, RewardDistribution, RewardRule models | `vinosports-core/rewards/` | Done |
| `distribute_to_users()` + `_broadcast_rewards()` | `vinosports-core/rewards/models.py` | Done |
| `NotificationConsumer` (reward, badge, challenge handlers) | `epl/rewards/consumers.py` | Done |
| `NotificationsConsumer` (NBA) | `nba/activity/consumers.py` | Done |
| WS routing for `/ws/notifications/` | EPL + NBA | Done |
| Reward toast templates | `epl/rewards/templates/` | Done |
| Balance OOB template | `epl/website/components/balance_oob.html` | Done |
| `#reward-notifications` container in base template | EPL `base.html` | Done |
| Unseen rewards context processor | `epl/rewards/context_processors.py` | Done |

## What's Missing

### 1. Rewards Admin (→ Hub)

The `epl-bets` repo has a rich admin interface for rewards that was never ported. This should live in **hub** since rewards are cross-league (shared DB, shared models).

**Port from epl-bets → hub:**

- **`RewardAdmin`** — Custom form with `distribute_to` user multi-select. Auto-sets `created_by`. Bulk action to distribute to all users. Shows recipient count annotation. Includes `RewardDistributionInline`.
- **`RewardDistributionAdmin`** — List/filter by seen status and reward. Manual balance crediting on save.
- **`RewardRuleAdmin`** — List-editable `is_active` toggle. Shows distribution count annotation.

**Steps:**
1. Add `vinosports.rewards` to hub's `INSTALLED_APPS`
2. Register `Reward`, `RewardDistribution`, `RewardRule` in `hub/admin.py` (or a new `hub/rewards_admin.py`)
3. Port the custom `RewardAdminForm` with user multi-select
4. Port the `distribute_to_all_users` admin action
5. Port `RewardDistributionInline`
6. Port `RewardRuleAdmin` with list-editable `is_active`

### 2. Rewards Dismiss View + URLs (→ EPL + NBA)

The toast dismiss button POSTs to `rewards:dismiss` but no view/URL exists yet in either league app.

**Steps:**
1. Create `rewards/views.py` in EPL with `DismissRewardView` (POST, login required, marks `seen=True`)
2. Create `rewards/urls.py` in EPL — `rewards/<int:pk>/dismiss/` named `rewards:dismiss`
3. Include in EPL's main `urls.py` under `rewards/` namespace
4. Replicate the same view + URL in NBA (or extract to core as a reusable view)

### 3. NBA Reward Toast Templates

NBA's `NotificationsConsumer` already handles `reward_notification` events, but it needs the templates to render.

**Steps:**
1. Create `nba/rewards/templates/rewards/partials/reward_toast.html` (port from EPL)
2. Create `nba/rewards/templates/rewards/partials/reward_toast_oob.html` (port from EPL)
3. Create `nba/website/components/balance_oob.html` (port from EPL, adjust for NBA template structure)
4. Add `#reward-notifications` container to NBA's `base.html` (already has `ws-connect` for notifications)

### 4. Unseen Rewards Context Processor (→ NBA)

EPL has `rewards/context_processors.py` that injects `unseen_rewards` so toasts render on page load (not just via WS). NBA needs this too.

**Steps:**
1. Port `rewards/context_processors.py` to NBA's rewards app
2. Add to NBA's `TEMPLATES` context processors in settings

### 5. Reward Signals (→ NBA)

EPL has `post_save` signals on BetSlip/Parlay that evaluate `RewardRule` triggers. NBA needs equivalent signals on its concrete BetSlip/Parlay models.

**Steps:**
1. Create `rewards/signals.py` in NBA (or in core if we can make it generic)
2. Wire up `post_save` on NBA's `BetSlip` and `Parlay`
3. Register signals in NBA's rewards `AppConfig.ready()`

## Implementation Order

```
Phase 1: Hub Admin
  1a. Add vinosports.rewards to hub INSTALLED_APPS
  1b. Port RewardAdmin, RewardDistributionAdmin, RewardRuleAdmin to hub

Phase 2: EPL Dismiss Flow
  2a. Create DismissRewardView + URL in EPL
  2b. Verify toast dismiss works end-to-end in EPL

Phase 3: NBA Rewards Parity
  3a. Port reward toast templates to NBA
  3b. Add #reward-notifications to NBA base.html
  3c. Port unseen_rewards context processor to NBA
  3d. Create DismissRewardView + URL in NBA
  3e. Port reward signals for NBA BetSlip/Parlay

Phase 4: Verify
  4a. Admin: create reward in hub admin, distribute to users, verify balance credited
  4b. EPL: trigger reward rule via bet, verify toast + balance update + dismiss
  4c. NBA: same as 4b
```

## Notes

- The dismiss view is simple enough that it could live in `vinosports-core` as a reusable class-based view, but since URL routing is league-specific, each app needs its own `urls.py` entry regardless.
- Hub does NOT need WebSocket support — it's an admin/auth app. Users see reward toasts on the league apps where they're actually playing.
- The `RewardRule` signal approach (checking on every bet save) is fine at current scale. If bet volume grows, consider moving rule evaluation to a Celery task.
