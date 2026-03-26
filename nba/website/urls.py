from django.urls import path
from django.views.generic import RedirectView

from nba.website.views import (
    AccountView,
    LogoutView,
    ThemeToggleView,
)

app_name = "nba_website"

urlpatterns = [
    path("account/", AccountView.as_view(), name="account"),
    # Auth — redirect login/signup to hub, keep local logout
    path("login/", RedirectView.as_view(url="/login/"), name="login"),
    path("signup/", RedirectView.as_view(url="/signup/"), name="signup"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("theme/toggle/", ThemeToggleView.as_view(), name="theme_toggle"),
]
