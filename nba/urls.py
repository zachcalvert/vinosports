from django.urls import include, path

from nba.website.views import DashboardView

urlpatterns = [
    path("games/", include("nba.games.urls")),
    path("odds/", include("nba.betting.urls")),
    path("news/", include(("news.urls", "nba_news"))),
    path("", include("nba.website.challenge_urls")),
    path("", include("nba.discussions.urls")),
    path("activity/", include("nba.activity.urls")),
    path("rewards/", include("nba.rewards.urls")),
    path("", include("nba.website.urls")),
    path("", DashboardView.as_view(), name="nba_dashboard"),
]
