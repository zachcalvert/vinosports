from django.contrib import admin

from .models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["user", "match", "created_at"]
    list_filter = ["created_at"]
    raw_id_fields = ["user", "match", "parent"]
