from django.urls import path

from worldcup.betting.views import (
    OddsBoardPartialView,
    OddsBoardView,
    PlaceBetView,
    QuickBetFormView,
)

app_name = "worldcup_betting"

urlpatterns = [
    path("", OddsBoardView.as_view(), name="odds_board"),
    path("partial/", OddsBoardPartialView.as_view(), name="odds_board_partial"),
    path("place/<slug:match_slug>/", PlaceBetView.as_view(), name="place_bet"),
    path(
        "quick-bet/<slug:match_slug>/",
        QuickBetFormView.as_view(),
        name="quick_bet_form",
    ),
]
