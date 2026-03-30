from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path("healthz", lambda r: HttpResponse("ok"), name="healthz"),
    path("admin/", admin.site.urls),
    path("epl/", include("epl.urls")),
    path("nba/", include("nba.urls")),
    path("nfl/", include("nfl.urls")),
    path("", include("hub.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
