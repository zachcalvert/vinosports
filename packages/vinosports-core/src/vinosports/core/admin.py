from django.contrib import admin

from vinosports.core.models import GlobalKnowledge


@admin.register(GlobalKnowledge)
class GlobalKnowledgeAdmin(admin.ModelAdmin):
    list_display = ["headline", "is_active", "sort_order", "updated_at"]
    list_editable = ["is_active", "sort_order"]
    list_filter = ["is_active"]
    search_fields = ["headline", "detail"]
    ordering = ["sort_order", "-created_at"]
