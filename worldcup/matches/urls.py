from django.urls import path

from worldcup.matches.views import (
    BracketView,
    DashboardView,
    GroupDetailView,
    GroupsView,
    LeaderboardPartialView,
    LeaderboardView,
    MatchDetailView,
)

app_name = "worldcup_matches"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("groups/", GroupsView.as_view(), name="groups"),
    path("groups/<str:letter>/", GroupDetailView.as_view(), name="group_detail"),
    path("bracket/", BracketView.as_view(), name="bracket"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path(
        "leaderboard/partial/",
        LeaderboardPartialView.as_view(),
        name="leaderboard_partial",
    ),
    path("match/<slug:slug>/", MatchDetailView.as_view(), name="match_detail"),
]
