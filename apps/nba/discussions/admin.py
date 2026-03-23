from django.contrib import admin

from discussions.models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["user", "game", "body_preview", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__email", "body"]
    raw_id_fields = ["user", "game", "parent"]

    @admin.display(description="Body")
    def body_preview(self, obj):
        return obj.body[:80] + "..." if len(obj.body) > 80 else obj.body
