from django.contrib import admin
from django.utils.html import format_html

from worldcup.matches.models import (
    Group,
    Match,
    MatchNotes,
    Odds,
    Stage,
    Standing,
    Team,
)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "tla", "confederation", "country_code", "has_crest"]
    list_filter = ["confederation"]
    search_fields = ["name", "short_name", "tla"]
    readonly_fields = ["crest_preview"]
    fieldsets = [
        (None, {"fields": ["external_id", "name", "short_name", "tla"]}),
        ("Country", {"fields": ["country_code", "confederation"]}),
        ("Crest", {"fields": ["crest_image", "crest_url", "crest_preview"]}),
    ]

    @admin.display(boolean=True, description="Crest?")
    def has_crest(self, obj):
        return bool(obj.crest_image or obj.crest_url)

    @admin.display(description="Preview")
    def crest_preview(self, obj):
        url = obj.crest
        if url:
            return format_html(
                '<img src="{}" style="max-height:80px;max-width:80px;">', url
            )
        return "—"


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ["__str__", "team_list"]
    filter_horizontal = ["teams"]

    @admin.display(description="Teams")
    def team_list(self, obj):
        return ", ".join(t.tla or t.short_name for t in obj.teams.all())


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ["name", "stage_type", "order"]
    list_editable = ["order"]
    ordering = ["order"]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["__str__", "stage", "group", "status", "kickoff", "venue"]
    list_filter = ["status", "stage", "group"]
    search_fields = ["home_team__name", "away_team__name", "venue", "city"]
    raw_id_fields = ["home_team", "away_team"]


@admin.register(Standing)
class StandingAdmin(admin.ModelAdmin):
    list_display = [
        "group",
        "position",
        "team",
        "played",
        "won",
        "drawn",
        "lost",
        "goal_difference",
        "points",
    ]
    list_filter = ["group"]
    search_fields = ["team__name"]


@admin.register(MatchNotes)
class MatchNotesAdmin(admin.ModelAdmin):
    list_display = ["match", "created_at", "updated_at"]
    list_select_related = ["match__home_team", "match__away_team"]
    search_fields = ["match__home_team__name", "match__away_team__name"]
    raw_id_fields = ["match"]


@admin.register(Odds)
class OddsAdmin(admin.ModelAdmin):
    list_display = ["match", "bookmaker", "home_win", "draw", "away_win", "fetched_at"]
    list_filter = ["bookmaker"]
    search_fields = ["match__home_team__name", "match__away_team__name"]
    raw_id_fields = ["match"]
