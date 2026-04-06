from django.contrib import admin

from worldcup.activity.models import ActivityEvent


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "message", "created_at", "broadcast_at"]
    list_filter = ["event_type"]
    search_fields = ["message"]
