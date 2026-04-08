from django.contrib import admin

from .models import Match, MatchNotes, Odds, Stage, Standing, Team


class MatchNotesInline(admin.StackedInline):
    model = MatchNotes
    extra = 0


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "tla", "country", "domestic_league", "external_id"]
    list_filter = ["country", "domestic_league"]
    search_fields = ["name", "short_name", "tla"]


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ["name", "stage_type", "order"]
    ordering = ["order"]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "stage",
        "matchday",
        "leg",
        "status",
        "kickoff",
    ]
    list_filter = ["status", "stage", "matchday", "season"]
    search_fields = ["home_team__name", "away_team__name", "slug"]
    raw_id_fields = ["home_team", "away_team"]
    inlines = [MatchNotesInline]


@admin.register(Standing)
class StandingAdmin(admin.ModelAdmin):
    list_display = [
        "position",
        "team",
        "played",
        "won",
        "drawn",
        "lost",
        "goal_difference",
        "points",
        "qualification_note",
    ]
    list_filter = ["season"]
    search_fields = ["team__name"]


@admin.register(Odds)
class OddsAdmin(admin.ModelAdmin):
    list_display = ["match", "bookmaker", "home_win", "draw", "away_win", "fetched_at"]
    list_filter = ["bookmaker"]
    raw_id_fields = ["match"]
