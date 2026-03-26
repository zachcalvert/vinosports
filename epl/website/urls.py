from django.urls import path
from django.views.generic import RedirectView

from epl.website.views import (
    AccountView,
    AvatarUpdateView,
    ComponentDetailView,
    CurrencyUpdateView,
    HowItWorksView,
    LogoutView,
    ThemeToggleView,
)

app_name = "epl_website"

urlpatterns = [
    path("account/", AccountView.as_view(), name="account"),
    path("account/avatar/", AvatarUpdateView.as_view(), name="avatar_update"),
    path("account/currency/", CurrencyUpdateView.as_view(), name="currency_update"),
    # Auth — redirect to hub
    path("login/", RedirectView.as_view(url="/login/"), name="login"),
    path("signup/", RedirectView.as_view(url="/signup/"), name="signup"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("theme/toggle/", ThemeToggleView.as_view(), name="theme_toggle"),
    path("how-it-works/", HowItWorksView.as_view(), name="how_it_works"),
    path(
        "how-it-works/component/",
        ComponentDetailView.as_view(),
        name="component_detail",
    ),
]
