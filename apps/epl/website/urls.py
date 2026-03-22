from django.urls import path

from website.views import (
    AccountView,
    AdminActivityQueuePartialView,
    AdminBetsPartialView,
    AdminCommentsPartialView,
    AdminDashboardView,
    AdminTasksPartialView,
    AdminUsersPartialView,
    AvatarUpdateView,
    ComponentDetailView,
    CurrencyUpdateView,
    HowItWorksView,
    LoginView,
    LogoutView,
    SignupView,
    ThemeToggleView,
)

app_name = "website"

urlpatterns = [
    path("account/", AccountView.as_view(), name="account"),
    path("account/avatar/", AvatarUpdateView.as_view(), name="avatar_update"),
    path("account/currency/", CurrencyUpdateView.as_view(), name="currency_update"),
    path("login/", LoginView.as_view(), name="login"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("theme/toggle/", ThemeToggleView.as_view(), name="theme_toggle"),
    path("how-it-works/", HowItWorksView.as_view(), name="how_it_works"),
    path("how-it-works/component/", ComponentDetailView.as_view(), name="component_detail"),
    # Admin dashboard
    path("admin-dashboard/", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("admin-dashboard/bets/", AdminBetsPartialView.as_view(), name="admin_dashboard_bets"),
    path("admin-dashboard/comments/", AdminCommentsPartialView.as_view(), name="admin_dashboard_comments"),
    path("admin-dashboard/tasks/", AdminTasksPartialView.as_view(), name="admin_dashboard_tasks"),
    path("admin-dashboard/users/", AdminUsersPartialView.as_view(), name="admin_dashboard_users"),
    path("admin-dashboard/activity-queue/", AdminActivityQueuePartialView.as_view(), name="admin_dashboard_activity_queue"),
]
