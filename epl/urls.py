from django.urls import include, path

from epl.betting.views import BalanceHistoryAPI, ProfileView

urlpatterns = [
    path(
        "api/balance-history/<slug:slug>/",
        BalanceHistoryAPI.as_view(),
        name="epl_balance_history_api",
    ),
    path("odds/", include("epl.betting.urls")),
    path("profile/<slug:slug>/", ProfileView.as_view(), name="epl_profile"),
    path("", include("epl.website.challenge_urls")),
    path("", include("epl.discussions.urls")),
    path("activity/", include("epl.activity.urls")),
    path("rewards/", include("epl.rewards.urls")),
    path("", include("epl.website.urls")),
    path("", include("epl.matches.urls")),
]
