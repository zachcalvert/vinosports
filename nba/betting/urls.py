from django.urls import path

from nba.betting.views import (
    AddToParlayView,
    BailoutView,
    BetFormView,
    ClearParlayView,
    MyBetsView,
    PlaceBetView,
    PlaceFeaturedParlayView,
    PlaceParlayView,
    QuickBetFormView,
    RemoveFromParlayView,
)

app_name = "nba_betting"

urlpatterns = [
    path("form/<str:id_hash>/", BetFormView.as_view(), name="bet_form"),
    path("quick-bet/<str:id_hash>/", QuickBetFormView.as_view(), name="quick_bet_form"),
    path("place/<str:id_hash>/", PlaceBetView.as_view(), name="place_bet"),
    path("my-bets/", MyBetsView.as_view(), name="my_bets"),
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
]
