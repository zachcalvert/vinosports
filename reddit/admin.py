from django.contrib import admin

from .models import SubredditSnapshot


@admin.register(SubredditSnapshot)
class SubredditSnapshotAdmin(admin.ModelAdmin):
    list_display = ("subreddit", "league", "fetched_at", "post_count")
    list_filter = ("league",)
    readonly_fields = (
        "id_hash",
        "league",
        "subreddit",
        "fetched_at",
        "data",
        "created_at",
        "updated_at",
    )
    ordering = ("-fetched_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
