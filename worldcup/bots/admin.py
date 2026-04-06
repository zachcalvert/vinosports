from django.contrib import admin

from worldcup.bots.models import BotComment


@admin.register(BotComment)
class BotCommentAdmin(admin.ModelAdmin):
    list_display = ["user", "match", "trigger_type", "created_at"]
    list_filter = ["trigger_type"]
    search_fields = ["user__display_name", "match__home_team__name"]
    raw_id_fields = ["user", "match", "comment", "parent_comment"]
