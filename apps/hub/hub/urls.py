from django.urls import path

from . import views

app_name = "hub"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("account/", views.AccountView.as_view(), name="account"),
    path(
        "account/currency/", views.CurrencyUpdateView.as_view(), name="currency_update"
    ),
]
