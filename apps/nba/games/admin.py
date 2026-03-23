from django.contrib import admin

from games.models import Game, GameStats, Odds, Standing, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["short_name", "abbreviation", "conference", "division"]
    list_filter = ["conference", "division"]
    search_fields = ["name", "short_name", "abbreviation"]


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "game_date",
        "status",
        "home_score",
        "away_score",
        "season",
        "postseason",
    ]
    list_filter = ["status", "season", "postseason"]
    search_fields = ["home_team__name", "away_team__name"]
    raw_id_fields = ["home_team", "away_team"]
    date_hierarchy = "game_date"


@admin.register(Standing)
class StandingAdmin(admin.ModelAdmin):
    list_display = [
        "team",
        "season",
        "conference",
        "conference_rank",
        "wins",
        "losses",
        "win_pct",
        "streak",
    ]
    list_filter = ["conference", "season"]
    search_fields = ["team__name"]
    raw_id_fields = ["team"]


@admin.register(GameStats)
class GameStatsAdmin(admin.ModelAdmin):
    list_display = ["game", "fetched_at"]
    raw_id_fields = ["game"]


@admin.register(Odds)
class OddsAdmin(admin.ModelAdmin):
    list_display = [
        "game",
        "bookmaker",
        "home_moneyline",
        "away_moneyline",
        "spread_line",
        "total_line",
        "fetched_at",
    ]
    list_filter = ["bookmaker"]
    search_fields = ["game__home_team__name", "game__away_team__name"]
    raw_id_fields = ["game"]
