from django.urls import path

from nba.games.views import (
    GameDetailView,
    GameNotesView,
    PlayerDetailView,
    PlayerListView,
    ScheduleView,
    StandingsView,
    TeamDetailView,
)

app_name = "nba_games"

urlpatterns = [
    path("schedule/", ScheduleView.as_view(), name="schedule"),
    path("standings/", StandingsView.as_view(), name="standings"),
    path("players/", PlayerListView.as_view(), name="player_list"),
    path("players/<slug:slug>/", PlayerDetailView.as_view(), name="player_detail"),
    path("teams/<str:abbreviation>/", TeamDetailView.as_view(), name="team_detail"),
    path("<str:id_hash>/notes/", GameNotesView.as_view(), name="game_notes"),
    path("<str:id_hash>/", GameDetailView.as_view(), name="game_detail"),
]
