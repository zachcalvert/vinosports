from django.urls import path

from . import views

app_name = "hub"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("account/", views.AccountView.as_view(), name="account"),
    path(
        "account/currency/", views.CurrencyUpdateView.as_view(), name="currency_update"
    ),
    path("bots/<slug:slug>/", views.BotProfileView.as_view(), name="bot_profile"),
    # Global standings
    path("standings/", views.StandingsView.as_view(), name="standings"),
    # My Bets (cross-league)
    path("my-bets/", views.MyBetsView.as_view(), name="my_bets"),
    # Admin Dashboard (cross-league)
    path(
        "admin-dashboard/",
        views.AdminDashboardView.as_view(),
        name="admin_dashboard",
    ),
    path(
        "admin-dashboard/bets/",
        views.AdminBetsPartialView.as_view(),
        name="admin_dashboard_bets",
    ),
    path(
        "admin-dashboard/comments/",
        views.AdminCommentsPartialView.as_view(),
        name="admin_dashboard_comments",
    ),
    path(
        "admin-dashboard/users/",
        views.AdminUsersPartialView.as_view(),
        name="admin_dashboard_users",
    ),
]
