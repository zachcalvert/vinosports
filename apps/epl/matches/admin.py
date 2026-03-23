from django.contrib import admin

from matches.models import Match, MatchNotes, MatchStats, Standing, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "tla", "venue"]
    search_fields = ["name", "short_name", "tla"]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["__str__", "status", "matchday", "kickoff", "season"]
    list_filter = ["status", "season", "matchday"]
    search_fields = ["home_team__name", "away_team__name"]
    raw_id_fields = ["home_team", "away_team"]


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
        "season",
    ]
    list_filter = ["season"]
    search_fields = ["team__name"]


@admin.register(MatchNotes)
class MatchNotesAdmin(admin.ModelAdmin):
    list_display = ["match", "created_at", "updated_at"]
    list_select_related = ["match__home_team", "match__away_team"]
    search_fields = ["match__home_team__name", "match__away_team__name"]
    raw_id_fields = ["match"]


@admin.register(MatchStats)
class MatchStatsAdmin(admin.ModelAdmin):
    list_display = ["match", "fetched_at", "is_stale"]
    list_select_related = ["match__home_team", "match__away_team"]
    search_fields = ["match__home_team__name", "match__away_team__name"]
    readonly_fields = [
        "fetched_at",
        "h2h_json",
        "h2h_summary_json",
        "home_form_json",
        "away_form_json",
    ]

    @admin.display(boolean=True, description="Stale?")
    def is_stale(self, obj):
        return obj.is_stale()
