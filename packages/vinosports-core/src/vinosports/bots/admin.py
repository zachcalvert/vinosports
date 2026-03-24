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
                "fields": ("avatar_icon", "avatar_bg"),
            },
        ),
        (
            "Persona",
            {
                "fields": ("persona_prompt",),
                "description": (
                    "Personality-only prompt — no team references. "
                    "Team context is injected at comment-generation time."
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
    actions = ["mark_active", "mark_inactive"]

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
