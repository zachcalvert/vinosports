from django.contrib import admin

from .models import ActivityEvent


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "message", "broadcast_at", "created_at"]
    list_filter = ["event_type"]
