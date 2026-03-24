# 0011 — NBA Admin Bot Actions (Ad Hoc Bets & Comments)

## Goal

Add Django admin actions to the NBA `BotProfileAdmin` page so admins can manually trigger selected bots to:

1. **Run bets** — execute the bot's strategy and place bets immediately
2. **Generate pregame comments** — write predictions on today's scheduled games
3. **Generate postgame comments** — write reactions to today's finished games

These bypass the Celery beat schedule and probability rolls, giving admins a way to test bots or fill in activity on demand.

---

## 1. Admin Actions Overview

Three new actions on the `BotProfileAdmin` changelist:

| Action | Label | What it does |
|--------|-------|-------------|
| `run_bets` | "Run bets for selected bots" | Calls `execute_bot_strategy` synchronously for each selected bot |
| `run_pregame_comments` | "Generate pregame comments" | Generates a pregame comment per selected bot per today's scheduled game |
| `run_postgame_comments` | "Generate postgame comments" | Generates a postgame comment per selected bot per today's final game |

All three operate on the selected queryset from the admin changelist (checkbox selection).

## 2. Implementation: `bots/admin.py`

```python
from django.contrib import admin, messages

@admin.register(BotProfile)
class BotProfileAdmin(admin.ModelAdmin):
    list_display = [...]
    list_filter = [...]
    actions = ["run_bets", "run_pregame_comments", "run_postgame_comments"]

    @admin.action(description="Run bets for selected bots")
    def run_bets(self, request, queryset):
        """Execute each selected bot's strategy synchronously."""
        from bots.tasks import execute_bot_strategy

        placed = 0
        errors = 0
        for profile in queryset.select_related("user"):
            result = execute_bot_strategy(profile.user_id, window_max_bets=None)
            if "error" in result:
                errors += 1
            else:
                placed += result.get("placed", 0)

        self.message_user(
            request,
            f"Placed {placed} bets across {queryset.count()} bots. Errors: {errors}.",
            messages.SUCCESS if errors == 0 else messages.WARNING,
        )

    @admin.action(description="Generate pregame comments for selected bots")
    def run_pregame_comments(self, request, queryset):
        """Generate pregame comments for selected bots on today's scheduled games."""
        from discussions.tasks import _generate_comment_body
        from games.models import Game, GameStatus
        from discussions.models import Comment
        from activity.models import ActivityEvent
        from django.utils import timezone

        today = timezone.localdate()
        games = Game.objects.filter(
            status=GameStatus.SCHEDULED, game_date=today
        ).select_related("home_team", "away_team")

        if not games.exists():
            self.message_user(request, "No scheduled games today.", messages.WARNING)
            return

        created = 0
        for game in games:
            matchup = f"{game.away_team.abbreviation} @ {game.home_team.abbreviation}"
            context = (
                f"Tonight's game: {matchup}\n\n"
                "Write a short comment (1-3 sentences) sharing your prediction "
                "or thoughts before tip-off. Stay in character."
            )
            for profile in queryset.select_related("user"):
                if Comment.objects.filter(user=profile.user, game=game).exists():
                    continue
                try:
                    body = _generate_comment_body(profile.persona_prompt, context)
                    Comment.objects.create(user=profile.user, game=game, body=body)
                    ActivityEvent.objects.create(
                        event_type=ActivityEvent.EventType.BOT_COMMENT,
                        message=f"{profile.user.display_name} commented on {matchup}",
                    )
                    created += 1
                except Exception as exc:
                    self.message_user(
                        request,
                        f"Error for {profile.user}: {exc}",
                        messages.ERROR,
                    )

        self.message_user(request, f"Created {created} pregame comments.", messages.SUCCESS)

    @admin.action(description="Generate postgame comments for selected bots")
    def run_postgame_comments(self, request, queryset):
        """Generate postgame comments for selected bots on today's final games."""
        from discussions.tasks import _generate_comment_body
        from games.models import Game, GameStatus
        from discussions.models import Comment
        from activity.models import ActivityEvent
        from django.utils import timezone

        today = timezone.localdate()
        games = Game.objects.filter(
            status=GameStatus.FINAL, game_date=today
        ).select_related("home_team", "away_team")

        if not games.exists():
            self.message_user(request, "No final games today.", messages.WARNING)
            return

        created = 0
        for game in games:
            matchup = f"{game.away_team.abbreviation} @ {game.home_team.abbreviation}"
            score = f"{game.away_score}-{game.home_score}"
            winner = game.winner
            winner_name = winner.abbreviation if winner else "TBD"
            context = (
                f"Final score: {matchup} — {score} ({winner_name} wins)\n\n"
                "Write a short comment (1-3 sentences) reacting to this result. "
                "Stay in character."
            )
            for profile in queryset.select_related("user"):
                if Comment.objects.filter(user=profile.user, game=game).exists():
                    continue
                try:
                    body = _generate_comment_body(profile.persona_prompt, context)
                    Comment.objects.create(user=profile.user, game=game, body=body)
                    ActivityEvent.objects.create(
                        event_type=ActivityEvent.EventType.BOT_COMMENT,
                        message=f"{profile.user.display_name} reacted to {matchup}",
                    )
                    created += 1
                except Exception as exc:
                    self.message_user(
                        request,
                        f"Error for {profile.user}: {exc}",
                        messages.ERROR,
                    )

        self.message_user(request, f"Created {created} postgame comments.", messages.SUCCESS)
```

## 3. Key Design Decisions

### Synchronous execution (no Celery dispatch)
The admin actions call the task functions **directly** (not via `.delay()` or `.apply_async()`). This means:
- Admin gets immediate feedback via `self.message_user()`
- No need to poll for async results
- Acceptable because ad hoc runs are for small batches (select a few bots)

If latency becomes an issue (many bots × many games × Claude API calls), switch to async dispatch with a progress message like "Dispatched N tasks — check logs."

### Bypasses schedule windows and probability rolls
The whole point is ad hoc control. The actions skip:
- `get_active_window()` / `is_bot_active_now()` checks
- `roll_action(probability)` randomness
- Staggered countdown delays

### Respects dedup and daily limits
- `run_bets` still respects `max_daily_bets` and balance checks (handled inside `execute_bot_strategy`)
- Comment actions skip bots that already commented on a game (existing `Comment.objects.filter` check)

### Reuses existing code
- `run_bets` calls `execute_bot_strategy()` directly (the same task function Celery calls)
- Comment actions reuse `_generate_comment_body()` from `discussions/tasks.py`

## 4. UX in Admin

After selecting bots and running an action, the admin sees a success/warning banner:
- "Placed 12 bets across 3 bots. Errors: 0."
- "Created 8 pregame comments."
- "No scheduled games today."

## 5. Future Enhancements

- **Confirmation page**: Add an intermediate confirmation page showing which games will be targeted before executing (override `ModelAdmin.response_action`)
- **Game picker**: Instead of acting on all today's games, let admin pick specific games via a custom form
- **Async with progress**: For bulk runs (all 40+ bots), dispatch to Celery and use Django messages or a simple polling UI for progress
- **Dry run mode**: Show what bets/comments would be generated without actually creating them

## 6. Implementation Order

1. Import `messages` in `bots/admin.py`
2. Add the three action methods to `BotProfileAdmin`
3. Register them in the `actions` list
4. Test manually: select 1-2 bots, run each action, verify in DB
5. (Optional) Add tests in `tests/test_admin.py` using `admin.site` action execution
