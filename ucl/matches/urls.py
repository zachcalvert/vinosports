from django.urls import path

from ucl.matches.views import (
    BracketView,
    DashboardView,
    LeaderboardPartialView,
    LeaderboardView,
    MatchDetailView,
    StandingsView,
)

app_name = "ucl_matches"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("standings/", StandingsView.as_view(), name="standings"),
    path("bracket/", BracketView.as_view(), name="bracket"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path(
        "leaderboard/partial/",
        LeaderboardPartialView.as_view(),
        name="leaderboard_partial",
    ),
    path("match/<slug:slug>/", MatchDetailView.as_view(), name="match_detail"),
]
