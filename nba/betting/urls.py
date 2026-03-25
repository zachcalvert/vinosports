from django.urls import path

from nba.betting.views import (
    AddToParlayView,
    BailoutView,
    ClearParlayView,
    MyBetsView,
    PlaceBetView,
    PlaceParlayView,
    RemoveFromParlayView,
)

app_name = "nba_betting"

urlpatterns = [
    path("place/<str:id_hash>/", PlaceBetView.as_view(), name="place_bet"),
    path("my-bets/", MyBetsView.as_view(), name="my_bets"),
    path("bailout/", BailoutView.as_view(), name="bailout"),
    path("parlay/add/", AddToParlayView.as_view(), name="parlay_add"),
    path("parlay/remove/", RemoveFromParlayView.as_view(), name="parlay_remove"),
    path("parlay/clear/", ClearParlayView.as_view(), name="parlay_clear"),
    path("parlay/place/", PlaceParlayView.as_view(), name="parlay_place"),
]
