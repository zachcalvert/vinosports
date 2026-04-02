from django.contrib import admin

from nfl.games.models import Game, GameNotes, GameStats, Player, Standing, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "abbreviation", "conference", "division"]
    list_filter = ["conference", "division"]
    search_fields = ["name", "short_name", "abbreviation"]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = [
        "full_name",
        "position_abbreviation",
        "jersey_number",
        "team",
        "experience",
        "is_active",
    ]
    list_filter = ["position_abbreviation", "team__conference", "team", "is_active"]
    search_fields = ["first_name", "last_name"]
    raw_id_fields = ["team"]


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "week",
        "game_date",
        "status",
        "home_score",
        "away_score",
        "season",
        "postseason",
    ]
    list_filter = ["status", "season", "week", "postseason"]
    search_fields = ["home_team__name", "away_team__name"]
    raw_id_fields = ["home_team", "away_team"]
    date_hierarchy = "game_date"


@admin.register(Standing)
class StandingAdmin(admin.ModelAdmin):
    list_display = [
        "team",
        "season",
        "division",
        "division_rank",
        "wins",
        "losses",
        "ties",
        "win_pct",
        "streak",
    ]
    list_filter = ["division", "conference", "season"]
    search_fields = ["team__name"]
    raw_id_fields = ["team"]


@admin.register(GameNotes)
class GameNotesAdmin(admin.ModelAdmin):
    list_display = ["game", "created_at", "updated_at"]
    list_select_related = ["game__home_team", "game__away_team"]
    search_fields = ["game__home_team__name", "game__away_team__name"]
    raw_id_fields = ["game"]


@admin.register(GameStats)
class GameStatsAdmin(admin.ModelAdmin):
    list_display = ["game", "fetched_at"]
    raw_id_fields = ["game"]
