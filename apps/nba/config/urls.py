from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from website.views import DashboardView

urlpatterns = [
    path("healthz", lambda r: HttpResponse("ok"), name="healthz"),
    path("admin/", admin.site.urls),
    path("games/", include("games.urls")),
    path("odds/", include("betting.urls")),
    path("", include("challenges.urls")),
    path("", include("discussions.urls")),
    path("activity/", include("activity.urls")),
    path("rewards/", include("rewards.urls")),
    path("", include("website.urls")),
    path("", DashboardView.as_view(), name="dashboard"),
]
