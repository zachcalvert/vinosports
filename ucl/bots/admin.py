from django.contrib import admin

from .models import BotComment


@admin.register(BotComment)
class BotCommentAdmin(admin.ModelAdmin):
    list_display = ["user", "match", "trigger_type", "created_at"]
    list_filter = ["trigger_type"]
    raw_id_fields = ["user", "match", "comment", "parent_comment"]
