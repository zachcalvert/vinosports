from django.urls import path

from ucl.betting.views import (
    AddToParlayView,
    ClearParlayView,
    FuturesBetFormView,
    FuturesMarketDetailView,
    FuturesView,
    OddsBoardPartialView,
    OddsBoardView,
    PlaceBetView,
    PlaceFuturesBetView,
    PlaceParlayView,
    QuickBetFormView,
    RemoveFromParlayView,
)

app_name = "ucl_betting"

urlpatterns = [
    path("", OddsBoardView.as_view(), name="odds_board"),
    path("partial/", OddsBoardPartialView.as_view(), name="odds_board_partial"),
    path("place/<slug:match_slug>/", PlaceBetView.as_view(), name="place_bet"),
    path(
        "quick-bet/<slug:match_slug>/",
        QuickBetFormView.as_view(),
        name="quick_bet_form",
    ),
    path("parlay/add/", AddToParlayView.as_view(), name="parlay_add"),
    path("parlay/remove/", RemoveFromParlayView.as_view(), name="parlay_remove"),
    path("parlay/clear/", ClearParlayView.as_view(), name="parlay_clear"),
    path("parlay/place/", PlaceParlayView.as_view(), name="parlay_place"),
    path("futures/", FuturesView.as_view(), name="futures"),
    path(
        "futures/<str:id_hash>/",
        FuturesMarketDetailView.as_view(),
        name="futures_detail",
    ),
    path(
        "futures/<str:id_hash>/bet/",
        FuturesBetFormView.as_view(),
        name="futures_bet_form",
    ),
    path(
        "futures/<str:id_hash>/place/",
        PlaceFuturesBetView.as_view(),
        name="place_futures_bet",
    ),
]
