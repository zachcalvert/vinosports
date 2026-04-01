from django.contrib import admin, messages

from vinosports.bots.models import BotProfile, ScheduleTemplate


@admin.register(ScheduleTemplate)
class ScheduleTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "active_from", "active_to"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BotProfile)
class BotProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "strategy_type",
        "is_active",
        "active_in_epl",
        "active_in_nba",
        "epl_team_tla",
        "nba_team_abbr",
        "risk_multiplier",
        "max_daily_bets",
        "schedule_template",
    ]
    list_filter = [
        "strategy_type",
        "is_active",
        "active_in_epl",
        "active_in_nba",
        "schedule_template",
    ]
    search_fields = ["user__email", "user__display_name"]
    raw_id_fields = ["user"]
    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "user",
                    "is_active",
                ),
            },
        ),
        (
            "Appearance",
            {
                "fields": ("avatar_icon", "avatar_bg", "portrait_url"),
            },
        ),
        (
            "Persona",
            {
                "fields": ("persona_prompt", "tagline"),
                "description": (
                    "Personality-only prompt — no team references. "
                    "Team context is injected at comment-generation time. "
                    "Tagline is the public-facing quote shown on the profile page."
                ),
            },
        ),
        (
            "Betting Behaviour",
            {
                "fields": (
                    "strategy_type",
                    "risk_multiplier",
                    "max_daily_bets",
                    "schedule_template",
                ),
            },
        ),
        (
            "League Activation",
            {
                "fields": ("active_in_epl", "active_in_nba", "active_in_nfl"),
            },
        ),
        (
            "Team Affiliations",
            {
                "fields": ("epl_team_tla", "nba_team_abbr"),
                "description": (
                    "Team abbreviations for homer bots. "
                    "Change these to reassign a bot's team loyalty."
                ),
            },
        ),
    )
    actions = [
        "mark_active",
        "mark_inactive",
        "run_strategies",
        "generate_pregame_comments",
        "generate_postgame_comments",
    ]

    @admin.action(description="Mark selected bots as active")
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request, f"Marked {updated} bot(s) as active.", messages.SUCCESS
        )

    @admin.action(description="Mark selected bots as inactive")
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request, f"Marked {updated} bot(s) as inactive.", messages.SUCCESS
        )

    @admin.action(description="Run bot strategies (all active leagues)")
    def run_strategies(self, request, queryset):
        dispatched = 0
        for profile in queryset.filter(is_active=True).select_related("user"):
            if profile.active_in_epl:
                from epl.bots.tasks import execute_bot_strategy as epl_run

                epl_run.apply_async(args=[profile.user_id])
                dispatched += 1
            if profile.active_in_nba:
                from nba.bots.tasks import execute_bot_strategy as nba_run

                nba_run.apply_async(args=[profile.user_id])
                dispatched += 1
            if profile.active_in_nfl:
                from nfl.bots.tasks import execute_bot_strategy as nfl_run

                nfl_run.apply_async(args=[profile.user_id])
                dispatched += 1
        self.message_user(
            request,
            f"Dispatched {dispatched} strategy task(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Generate pregame comments (all active leagues)")
    def generate_pregame_comments(self, request, queryset):
        user_ids = list(
            queryset.filter(is_active=True).values_list("user_id", flat=True)
        )
        if not user_ids:
            self.message_user(request, "No active bots selected.", messages.WARNING)
            return
        dispatched = 0
        if queryset.filter(active_in_epl=True).exists():
            from epl.bots.tasks import generate_prematch_comments

            generate_prematch_comments.apply_async(kwargs={"bot_user_ids": user_ids})
            dispatched += 1
        if queryset.filter(active_in_nba=True).exists():
            from nba.discussions.tasks import generate_pregame_comments as nba_pregame

            nba_pregame.apply_async(kwargs={"bot_user_ids": user_ids})
            dispatched += 1
        if queryset.filter(active_in_nfl=True).exists():
            from nfl.discussions.tasks import generate_pregame_comments as nfl_pregame

            nfl_pregame.apply_async(kwargs={"bot_user_ids": user_ids})
            dispatched += 1
        self.message_user(
            request,
            f"Dispatched pregame comment tasks for {len(user_ids)} bot(s) "
            f"across {dispatched} league(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Generate postgame comments (all active leagues)")
    def generate_postgame_comments(self, request, queryset):
        user_ids = list(
            queryset.filter(is_active=True).values_list("user_id", flat=True)
        )
        if not user_ids:
            self.message_user(request, "No active bots selected.", messages.WARNING)
            return
        dispatched = 0
        if queryset.filter(active_in_epl=True).exists():
            from epl.bots.tasks import generate_postmatch_comments

            generate_postmatch_comments.apply_async(kwargs={"bot_user_ids": user_ids})
            dispatched += 1
        if queryset.filter(active_in_nba=True).exists():
            from nba.discussions.tasks import generate_postgame_comments as nba_postgame

            nba_postgame.apply_async(kwargs={"bot_user_ids": user_ids})
            dispatched += 1
        if queryset.filter(active_in_nfl=True).exists():
            from nfl.discussions.tasks import generate_postgame_comments as nfl_postgame

            nfl_postgame.apply_async(kwargs={"bot_user_ids": user_ids})
            dispatched += 1
        self.message_user(
            request,
            f"Dispatched postgame comment tasks for {len(user_ids)} bot(s) "
            f"across {dispatched} league(s).",
            messages.SUCCESS,
        )
