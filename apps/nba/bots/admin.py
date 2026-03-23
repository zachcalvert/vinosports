from django.contrib import admin

from bots.models import BotComment, BotProfile


@admin.register(BotProfile)
class BotProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "strategy_type",
        "favorite_team",
        "is_active",
        "risk_multiplier",
        "max_daily_bets",
    ]
    list_filter = ["strategy_type", "is_active"]
    search_fields = ["user__email", "user__display_name"]
    raw_id_fields = ["user", "favorite_team"]


@admin.register(BotComment)
class BotCommentAdmin(admin.ModelAdmin):
    list_display = ["user", "game", "trigger_type", "filtered", "created_at"]
    list_filter = ["trigger_type", "filtered"]
    search_fields = ["user__email"]
    raw_id_fields = ["user", "game", "comment", "parent_comment"]
