from django.urls import include, path

urlpatterns = [
    path("odds/", include("ucl.betting.urls")),
    path("", include("ucl.discussions.urls")),
    path("activity/", include("ucl.activity.urls")),
    path("rewards/", include("ucl.rewards.urls")),
    path("", include("ucl.website.urls")),
    path("", include("ucl.matches.urls")),
]
