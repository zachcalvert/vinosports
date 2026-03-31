from django.urls import path

from nba.betting.views import (
    AddToParlayView,
    BailoutView,
    BetFormView,
    ClearParlayView,
    FuturesBetFormView,
    FuturesListView,
    FuturesMarketDetailView,
    OddsBoardPartialView,
    OddsBoardView,
    PlaceBetView,
    PlaceFeaturedParlayView,
    PlaceFuturesBetView,
    PlaceParlayView,
    QuickBetFormView,
    RemoveFromParlayView,
)

app_name = "nba_betting"

urlpatterns = [
    path("", OddsBoardView.as_view(), name="odds"),
    path("partial/", OddsBoardPartialView.as_view(), name="odds_partial"),
    path("form/<str:id_hash>/", BetFormView.as_view(), name="bet_form"),
    path("quick-bet/<str:id_hash>/", QuickBetFormView.as_view(), name="quick_bet_form"),
    path("place/<str:id_hash>/", PlaceBetView.as_view(), name="place_bet"),
    path("bailout/", BailoutView.as_view(), name="bailout"),
    path("parlay/add/", AddToParlayView.as_view(), name="parlay_add"),
    path("parlay/remove/", RemoveFromParlayView.as_view(), name="parlay_remove"),
    path("parlay/clear/", ClearParlayView.as_view(), name="parlay_clear"),
    path("parlay/place/", PlaceParlayView.as_view(), name="parlay_place"),
    path(
        "parlay/featured/<int:pk>/place/",
        PlaceFeaturedParlayView.as_view(),
        name="place_featured_parlay",
    ),
    # Futures
    path("futures/", FuturesListView.as_view(), name="futures"),
    path(
        "futures/<str:id_hash>/",
        FuturesMarketDetailView.as_view(),
        name="futures_detail",
    ),
    path(
        "futures/bet/<str:id_hash>/",
        FuturesBetFormView.as_view(),
        name="futures_bet_form",
    ),
    path(
        "futures/place/<str:id_hash>/",
        PlaceFuturesBetView.as_view(),
        name="place_futures_bet",
    ),
]
