from django.urls import path
from django.views.generic import RedirectView

from matches.views import (
    DashboardView,
    LeaderboardPartialView,
    LeaderboardView,
    LeagueTableView,
    MatchDetailView,
    MatchNotesView,
    MatchOddsPartialView,
    MatchStatusCardPartialView,
)

app_name = "matches"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("leaderboard/partial/", LeaderboardPartialView.as_view(), name="leaderboard_partial"),
    path("fixtures/", RedirectView.as_view(url="/", permanent=True), name="fixtures"),
    path("table/", LeagueTableView.as_view(), name="table"),
    path("match/<slug:slug>/", MatchDetailView.as_view(), name="match_detail"),
    path(
        "match/<slug:slug>/status-card/",
        MatchStatusCardPartialView.as_view(),
        name="match_status_card",
    ),
    path("match/<slug:slug>/notes/", MatchNotesView.as_view(), name="match_notes"),
    path("match/<slug:slug>/odds/", MatchOddsPartialView.as_view(), name="match_odds_partial"),
]
