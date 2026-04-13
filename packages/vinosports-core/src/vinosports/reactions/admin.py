from django.contrib import admin

from .models import ArticleReaction, CommentReaction


@admin.register(CommentReaction)
class CommentReactionAdmin(admin.ModelAdmin):
    list_display = ("user", "reaction_type", "content_type", "object_id", "created_at")
    list_filter = ("reaction_type", "content_type")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at",)


@admin.register(ArticleReaction)
class ArticleReactionAdmin(admin.ModelAdmin):
    list_display = ("user", "reaction_type", "article", "created_at")
    list_filter = ("reaction_type",)
    raw_id_fields = ("user", "article")
    readonly_fields = ("created_at",)
