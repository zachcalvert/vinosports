from django.contrib import admin

from worldcup.discussions.models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["user", "match", "created_at", "is_deleted"]
    list_filter = ["is_deleted"]
    search_fields = ["user__email", "body"]
    raw_id_fields = ["user", "match", "parent"]
