from betting.views import BalanceHistoryAPI, ProfileView
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path("healthz", lambda r: HttpResponse("ok"), name="healthz"),
    path("admin/", admin.site.urls),
    path(
        "api/balance-history/<slug:slug>/",
        BalanceHistoryAPI.as_view(),
        name="balance_history_api",
    ),
    path("odds/", include("betting.urls")),
    path("profile/<slug:slug>/", ProfileView.as_view(), name="profile"),
    path("", include("website.challenge_urls")),
    path("", include("discussions.urls")),
    path("activity/", include("activity.urls")),
    path("rewards/", include("rewards.urls")),
    path("", include("website.urls")),
    path("", include("matches.urls")),
]
