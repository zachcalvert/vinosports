from django.contrib import admin

from nba.games.models import (
    Game,
    GameStats,
    Odds,
    Player,
    PlayerBoxScore,
    Standing,
    Team,
)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["short_name", "abbreviation", "conference", "division"]
    list_filter = ["conference", "division"]
    search_fields = ["name", "short_name", "abbreviation"]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = [
        "full_name",
        "position",
        "jersey_number",
        "team",
        "country",
        "draft_year",
    ]
    list_filter = ["position", "team__conference", "team"]
    search_fields = ["first_name", "last_name"]
    raw_id_fields = ["team"]


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


@admin.register(PlayerBoxScore)
class PlayerBoxScoreAdmin(admin.ModelAdmin):
    list_display = [
        "player_name",
        "team",
        "game",
        "points",
        "reb",
        "ast",
        "minutes",
        "starter",
    ]
    list_filter = ["starter", "team"]
    search_fields = ["player_name"]
    raw_id_fields = ["game", "team"]


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
