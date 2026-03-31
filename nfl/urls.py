from django.urls import include, path

from nfl.website.views import DashboardView

urlpatterns = [
    path("games/", include("nfl.games.urls")),
    path("odds/", include("nfl.betting.urls")),
    path("", include("nfl.discussions.urls")),
    path("activity/", include("nfl.activity.urls")),
    path("", include("nfl.website.urls")),
    path("", DashboardView.as_view(), name="nfl_dashboard"),
]
