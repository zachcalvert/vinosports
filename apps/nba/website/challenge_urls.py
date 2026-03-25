from django.urls import path

from website.challenge_views import ChallengesPageView

app_name = "challenges"

urlpatterns = [
    path("challenges/", ChallengesPageView.as_view(), name="challenge_list"),
]
