from django.urls import path

from epl.betting.views import (
    AddToParlayView,
    BailoutView,
    ClearParlayView,
    FuturesBetFormView,
    FuturesListView,
    FuturesMarketDetailView,
    OddsBoardPartialView,
    OddsBoardView,
    ParlaySlipPartialView,
    PlaceBetView,
    PlaceFeaturedParlayView,
    PlaceFuturesBetView,
    PlaceParlayView,
    QuickBetFormView,
    RemoveFromParlayView,
)

app_name = "epl_betting"

urlpatterns = [
    path("", OddsBoardView.as_view(), name="odds"),
    path("partial/", OddsBoardPartialView.as_view(), name="odds_partial"),
    path("place/<slug:match_slug>/", PlaceBetView.as_view(), name="place_bet"),
    path(
        "quick-bet/<slug:match_slug>/",
        QuickBetFormView.as_view(),
        name="quick_bet_form",
    ),
    path("bailout/", BailoutView.as_view(), name="bailout"),
    # Parlay slip management
    path("parlay/add/", AddToParlayView.as_view(), name="parlay_add"),
    path("parlay/remove/", RemoveFromParlayView.as_view(), name="parlay_remove"),
    path("parlay/clear/", ClearParlayView.as_view(), name="parlay_clear"),
    path("parlay/slip/", ParlaySlipPartialView.as_view(), name="parlay_slip"),
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
