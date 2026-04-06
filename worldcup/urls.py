from django.urls import include, path

urlpatterns = [
    path("odds/", include("worldcup.betting.urls")),
    path("", include("worldcup.website.challenge_urls")),
    path("", include("worldcup.discussions.urls")),
    path("activity/", include("worldcup.activity.urls")),
    path("rewards/", include("worldcup.rewards.urls")),
    path("", include("worldcup.website.urls")),
    path("", include("worldcup.matches.urls")),
]
