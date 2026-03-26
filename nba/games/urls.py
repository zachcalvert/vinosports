from django.urls import path

from nba.games.views import (
    GameDetailView,
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
    path("players/<str:id_hash>/", PlayerDetailView.as_view(), name="player_detail"),
    path("teams/<str:abbreviation>/", TeamDetailView.as_view(), name="team_detail"),
    path("<str:id_hash>/", GameDetailView.as_view(), name="game_detail"),
]
