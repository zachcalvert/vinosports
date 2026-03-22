from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from betting.views import BalanceHistoryAPI, ProfileView

urlpatterns = [
    path("healthz", lambda r: HttpResponse("ok"), name="healthz"),
    path("admin/", admin.site.urls),
    path("api/balance-history/<slug:slug>/", BalanceHistoryAPI.as_view(), name="balance_history_api"),
    path("odds/", include("betting.urls")),
    path("profile/<slug:slug>/", ProfileView.as_view(), name="profile"),
    path("", include("challenges.urls")),
    path("", include("discussions.urls")),
    path("", include("website.urls")),
    path("", include("matches.urls")),
]
