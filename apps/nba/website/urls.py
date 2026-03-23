from django.urls import path

from website.views import (
    AccountView,
    LoginView,
    LogoutView,
    SignupView,
    ThemeToggleView,
)

app_name = "website"

urlpatterns = [
    path("account/", AccountView.as_view(), name="account"),
    path("login/", LoginView.as_view(), name="login"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("theme/toggle/", ThemeToggleView.as_view(), name="theme_toggle"),
]
