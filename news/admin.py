from django.contrib import admin
from django.utils import timezone

from .models import NewsArticle


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "league",
        "article_type",
        "status",
        "author",
        "published_at",
    ]
    list_filter = ["league", "article_type", "status"]
    search_fields = ["title", "body"]
    readonly_fields = [
        "id_hash",
        "prompt_used",
        "raw_response",
        "created_at",
        "updated_at",
    ]
    raw_id_fields = ["author"]
    actions = ["publish_articles", "archive_articles"]

    @admin.action(description="Publish selected articles")
    def publish_articles(self, request, queryset):
        count = queryset.filter(status=NewsArticle.Status.DRAFT).update(
            status=NewsArticle.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        self.message_user(request, f"{count} article(s) published.")

    @admin.action(description="Archive selected articles")
    def archive_articles(self, request, queryset):
        count = queryset.update(status=NewsArticle.Status.ARCHIVED)
        self.message_user(request, f"{count} article(s) archived.")
