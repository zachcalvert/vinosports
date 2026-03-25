from django.urls import path

from nba.website.challenge_views import ChallengesPageView

app_name = "nba_challenges"

urlpatterns = [
    path("challenges/", ChallengesPageView.as_view(), name="challenge_list"),
]
