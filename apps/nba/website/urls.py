from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView

from website.views import (
    AccountView,
    LogoutView,
    ThemeToggleView,
)

app_name = "website"

HUB = settings.HUB_URL

urlpatterns = [
    path("account/", AccountView.as_view(), name="account"),
    # Auth — redirect login/signup to hub, keep local logout
    path("login/", RedirectView.as_view(url=f"{HUB}/login/"), name="login"),
    path("signup/", RedirectView.as_view(url=f"{HUB}/signup/"), name="signup"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("theme/toggle/", ThemeToggleView.as_view(), name="theme_toggle"),
]
