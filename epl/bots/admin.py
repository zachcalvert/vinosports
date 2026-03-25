from django.contrib import admin

from epl.bots.models import BotComment


@admin.register(BotComment)
class BotCommentAdmin(admin.ModelAdmin):
    list_display = ("user", "match", "trigger_type", "filtered", "created_at")
    list_filter = ("trigger_type", "filtered")
    list_select_related = ("user", "match", "match__home_team", "match__away_team")
    raw_id_fields = ("user", "match", "comment", "parent_comment")
    readonly_fields = ("prompt_used", "raw_response")
