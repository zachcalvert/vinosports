from django.urls import path
from django.views.generic import RedirectView

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
    path(
        "account/profile-image/",
        views.ProfileImageUploadView.as_view(),
        name="profile_image_upload",
    ),
    path(
        "account/bot-profile/create/",
        views.CreateBotProfileView.as_view(),
        name="create_bot_profile",
    ),
    path(
        "account/bot-profile/edit/",
        views.EditBotProfileView.as_view(),
        name="edit_bot_profile",
    ),
    path(
        "account/bot-profile/toggle/",
        views.ToggleBotProfileView.as_view(),
        name="toggle_bot_profile",
    ),
    path(
        "api/balance-history/<slug:slug>/",
        views.BalanceHistoryAPI.as_view(),
        name="balance_history_api",
    ),
    path("profile/<slug:slug>/", views.ProfileView.as_view(), name="profile"),
    path(
        "bots/<slug:slug>/",
        RedirectView.as_view(pattern_name="hub:profile", permanent=True),
        name="bot_profile",
    ),
    # Global standings
    path("standings/", views.StandingsView.as_view(), name="standings"),
    # My Bets (cross-league)
    path("my-bets/", views.MyBetsView.as_view(), name="my_bets"),
    # Challenges (cross-league)
    path("challenges/", views.ChallengesView.as_view(), name="challenges"),
    path(
        "challenges/active/",
        views.ActiveChallengesHubPartial.as_view(),
        name="challenges_active_partial",
    ),
    path(
        "challenges/completed/",
        views.CompletedChallengesHubPartial.as_view(),
        name="challenges_completed_partial",
    ),
    path(
        "challenges/upcoming/",
        views.UpcomingChallengesHubPartial.as_view(),
        name="challenges_upcoming_partial",
    ),
    # Inbox (notifications)
    path("inbox/", views.InboxView.as_view(), name="inbox"),
    path(
        "inbox/read/<str:id_hash>/",
        views.MarkNotificationReadView.as_view(),
        name="inbox_mark_read",
    ),
    path(
        "inbox/read-all/",
        views.MarkAllReadView.as_view(),
        name="inbox_mark_all_read",
    ),
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
    path(
        "admin-dashboard/stats/",
        views.AdminStatsPartialView.as_view(),
        name="admin_dashboard_stats",
    ),
    path(
        "admin-dashboard/bets/all/",
        views.AdminBetsFullView.as_view(),
        name="admin_bets_full",
    ),
    path(
        "admin-dashboard/comments/all/",
        views.AdminCommentsFullView.as_view(),
        name="admin_comments_full",
    ),
    path(
        "featured-parlays/<int:pk>/delete/",
        views.DeleteFeaturedParlayView.as_view(),
        name="delete_featured_parlay",
    ),
    path("live-games/", views.LiveGamesStripView.as_view(), name="live_games_strip"),
]
