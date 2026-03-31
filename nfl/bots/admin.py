from django.contrib import admin

from nfl.bots.models import BotComment


@admin.register(BotComment)
class BotCommentAdmin(admin.ModelAdmin):
    list_display = ["user", "game", "trigger_type", "filtered", "created_at"]
    list_filter = ["trigger_type", "filtered"]
    search_fields = ["user__email"]
    raw_id_fields = ["user", "game", "comment", "parent_comment"]
