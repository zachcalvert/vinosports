from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from bots.models import BotComment, BotProfile


@admin.register(BotProfile)
class BotProfileAdmin(admin.ModelAdmin):
    list_display = ("user_display_name", "strategy_type", "team_tla", "is_active")
    list_filter = ("strategy_type", "is_active")
    list_select_related = ("user",)
    search_fields = ("user__display_name", "user__email")

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return ("user",)
        return ()

    fieldsets = (
        (_("Identity"), {
            "fields": ("user", "strategy_type", "team_tla", "is_active"),
        }),
        (_("Appearance"), {
            "fields": ("avatar_icon", "avatar_bg"),
        }),
        (_("Persona"), {
            "fields": ("persona_prompt",),
            "description": _(
                "The full system prompt sent to Claude when this bot generates "
                "comments or board posts. Edit to tweak personality and voice."
            ),
        }),
    )

    @admin.display(description="Bot", ordering="user__display_name")
    def user_display_name(self, obj):
        return obj.user.display_name


@admin.register(BotComment)
class BotCommentAdmin(admin.ModelAdmin):
    list_display = ("user", "match", "trigger_type", "filtered", "created_at")
    list_filter = ("trigger_type", "filtered")
    list_select_related = ("user", "match", "match__home_team", "match__away_team")
    raw_id_fields = ("user", "match", "comment", "parent_comment")
    readonly_fields = ("prompt_used", "raw_response")
