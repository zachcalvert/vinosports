from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path("healthz", lambda r: HttpResponse("ok"), name="healthz"),
    path("admin/", admin.site.urls),
    path("epl/", include("epl.urls")),
    path("nba/", include("nba.urls")),
    path("", include("hub.urls")),
]
