from django.urls import path

from worldcup.betting.views import OddsBoardPartialView, OddsBoardView

app_name = "worldcup_betting"

urlpatterns = [
    path("", OddsBoardView.as_view(), name="odds_board"),
    path("partial/", OddsBoardPartialView.as_view(), name="odds_board_partial"),
]
