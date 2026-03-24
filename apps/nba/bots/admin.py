from django.contrib import admin, messages

from bots.models import BotComment, BotProfile, ScheduleTemplate


@admin.register(ScheduleTemplate)
class ScheduleTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "active_from", "active_to"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BotProfile)
class BotProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "strategy_type",
        "favorite_team",
        "is_active",
        "risk_multiplier",
        "max_daily_bets",
        "schedule_template",
    ]
    list_filter = ["strategy_type", "is_active", "schedule_template"]
    search_fields = ["user__email", "user__display_name"]
    raw_id_fields = ["user", "favorite_team"]
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
        from activity.models import ActivityEvent
        from discussions.models import Comment
        from discussions.tasks import _generate_comment_body
        from django.utils import timezone
        from games.models import Game, GameStatus

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

        self.message_user(
            request, f"Created {created} pregame comments.", messages.SUCCESS
        )

    @admin.action(description="Generate postgame comments for selected bots")
    def run_postgame_comments(self, request, queryset):
        """Generate postgame comments for selected bots on today's final games."""
        from activity.models import ActivityEvent
        from discussions.models import Comment
        from discussions.tasks import _generate_comment_body
        from django.utils import timezone
        from games.models import Game, GameStatus

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

        self.message_user(
            request, f"Created {created} postgame comments.", messages.SUCCESS
        )


@admin.register(BotComment)
class BotCommentAdmin(admin.ModelAdmin):
    list_display = ["user", "game", "trigger_type", "filtered", "created_at"]
    list_filter = ["trigger_type", "filtered"]
    search_fields = ["user__email"]
    raw_id_fields = ["user", "game", "comment", "parent_comment"]
