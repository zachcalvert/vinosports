from django.urls import path

from nba.games.views import GameDetailView, ScheduleView, StandingsView

app_name = "nba_games"

urlpatterns = [
    path("schedule/", ScheduleView.as_view(), name="schedule"),
    path("standings/", StandingsView.as_view(), name="standings"),
    path("<str:id_hash>/", GameDetailView.as_view(), name="game_detail"),
]
