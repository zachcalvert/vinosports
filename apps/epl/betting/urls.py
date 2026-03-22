from django.urls import path

from betting.views import (
    AddToParlayView,
    BailoutView,
    ClearParlayView,
    MyBetsView,
    OddsBoardPartialView,
    OddsBoardView,
    ParlaySlipPartialView,
    PlaceBetView,
    PlaceParlayView,
    QuickBetFormView,
    RemoveFromParlayView,
)

app_name = "betting"

urlpatterns = [
    path("", OddsBoardView.as_view(), name="odds"),
    path("partial/", OddsBoardPartialView.as_view(), name="odds_partial"),
    path("place/<slug:match_slug>/", PlaceBetView.as_view(), name="place_bet"),
    path("my-bets/", MyBetsView.as_view(), name="my_bets"),
    path("quick-bet/<slug:match_slug>/", QuickBetFormView.as_view(), name="quick_bet_form"),
    path("bailout/", BailoutView.as_view(), name="bailout"),
    # Parlay slip management
    path("parlay/add/", AddToParlayView.as_view(), name="parlay_add"),
    path("parlay/remove/", RemoveFromParlayView.as_view(), name="parlay_remove"),
    path("parlay/clear/", ClearParlayView.as_view(), name="parlay_clear"),
    path("parlay/slip/", ParlaySlipPartialView.as_view(), name="parlay_slip"),
    path("parlay/place/", PlaceParlayView.as_view(), name="parlay_place"),
]
