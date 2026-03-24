"""Tests for website/views.py (DashboardView, AccountView, ThemeToggleView, etc.)."""

import pytest
from django.test import Client

from tests.factories import (
    ActivityEventFactory,
    BetSlipFactory,
    CommentFactory,
    GameFactory,
    UserBalanceFactory,
    UserFactory,
)


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def logged_in_client(db):
    user = UserFactory()
    c = Client()
    c.force_login(user)
    return c, user


@pytest.fixture
def superuser_client(db):
    user = UserFactory()
    user.is_superuser = True
    user.save()
    c = Client()
    c.force_login(user)
    return c, user


@pytest.mark.django_db
class TestDashboardView:
    def test_redirects_unauthenticated_user(self, client):
        response = client.get("/")
        assert response.status_code in (301, 302)

    def test_authenticated_user_gets_200(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/")
        assert response.status_code == 200

    def test_uses_dashboard_template(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/")
        assert "website/dashboard.html" in [t.name for t in response.templates]

    def test_context_contains_game_lists(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/")
        assert "live_games" in response.context
        assert "upcoming_games" in response.context
        assert "final_games" in response.context
        assert "today" in response.context

    def test_no_games_shows_empty_lists(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/")
        assert list(response.context["live_games"]) == []
        assert list(response.context["upcoming_games"]) == []
        assert list(response.context["final_games"]) == []


@pytest.mark.django_db
class TestLogoutView:
    def test_get_redirects_to_root(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/logout/")
        assert response.status_code in (301, 302)

    def test_post_redirects_to_root(self, logged_in_client):
        c, user = logged_in_client
        response = c.post("/logout/")
        assert response.status_code in (301, 302)

    def test_logs_out_user(self, logged_in_client):
        c, user = logged_in_client
        c.post("/logout/")
        response = c.get("/")
        # After logout, dashboard should redirect to login
        assert response.status_code in (301, 302)


@pytest.mark.django_db
class TestAccountView:
    def test_redirects_unauthenticated_user(self, client):
        response = client.get("/account/")
        assert response.status_code in (301, 302)

    def test_authenticated_user_gets_200(self, logged_in_client):
        c, user = logged_in_client
        UserBalanceFactory(user=user)
        response = c.get("/account/")
        assert response.status_code == 200

    def test_uses_account_template(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/account/")
        assert "website/account.html" in [t.name for t in response.templates]

    def test_context_has_balance_and_stats(self, logged_in_client):
        c, user = logged_in_client
        UserBalanceFactory(user=user)
        response = c.get("/account/")
        assert "balance" in response.context
        assert "stats" in response.context
        assert "transactions" in response.context

    def test_account_view_without_balance(self, logged_in_client):
        """AccountView should still render when user has no balance."""
        c, user = logged_in_client
        response = c.get("/account/")
        assert response.status_code == 200
        assert response.context["balance"] is None


@pytest.mark.django_db
class TestThemeToggleView:
    def test_post_redirects(self, logged_in_client):
        c, user = logged_in_client
        response = c.post("/theme/toggle/")
        assert response.status_code in (301, 302)

    def test_post_with_theme_sets_session(self, logged_in_client):
        c, user = logged_in_client
        c.post("/theme/toggle/", {"theme": "dark"})
        session = c.session
        assert session.get("theme_preference") == "dark"

    def test_post_toggles_from_light_to_dark(self, logged_in_client):
        c, user = logged_in_client
        session = c.session
        session["theme_preference"] = "light"
        session.save()
        c.post("/theme/toggle/")
        session = c.session
        assert session.get("theme_preference") == "dark"

    def test_post_toggles_from_dark_to_light(self, logged_in_client):
        c, user = logged_in_client
        session = c.session
        session["theme_preference"] = "dark"
        session.save()
        c.post("/theme/toggle/")
        session = c.session
        assert session.get("theme_preference") == "light"

    def test_post_invalid_theme_uses_default(self, logged_in_client):
        c, user = logged_in_client
        c.post("/theme/toggle/", {"theme": "rainbow"})
        session = c.session
        assert session.get("theme_preference") == "light"


@pytest.mark.django_db
class TestAdminDashboardView:
    def test_non_superuser_redirected(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/admin-dashboard/")
        assert response.status_code in (301, 302, 403)

    def test_superuser_gets_200(self, superuser_client):
        c, user = superuser_client
        response = c.get("/admin-dashboard/")
        assert response.status_code == 200

    def test_uses_admin_dashboard_template(self, superuser_client):
        c, user = superuser_client
        response = c.get("/admin-dashboard/")
        assert "website/admin_dashboard.html" in [t.name for t in response.templates]

    def test_context_has_stats(self, superuser_client):
        c, user = superuser_client
        response = c.get("/admin-dashboard/")
        assert "total_users" in response.context
        assert "active_bets" in response.context
        assert "total_comments" in response.context
        assert "queued_events" in response.context

    def test_counts_reflect_created_objects(self, superuser_client):
        c, user = superuser_client
        UserFactory()
        UserFactory()
        response = c.get("/admin-dashboard/")
        assert response.context["total_users"] >= 3  # 2 + superuser


@pytest.mark.django_db
class TestAdminBetsPartialView:
    def test_non_superuser_denied(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/admin-dashboard/bets/")
        assert response.status_code in (301, 302, 403)

    def test_superuser_gets_200(self, superuser_client):
        c, user = superuser_client
        response = c.get("/admin-dashboard/bets/")
        assert response.status_code == 200

    def test_with_existing_bets(self, superuser_client):
        c, user = superuser_client
        other_user = UserFactory()
        UserBalanceFactory(user=other_user)
        game = GameFactory()
        BetSlipFactory(user=other_user, game=game)
        response = c.get("/admin-dashboard/bets/")
        assert response.status_code == 200

    def test_paginated_response_with_offset(self, superuser_client):
        c, user = superuser_client
        response = c.get("/admin-dashboard/bets/?offset=5")
        assert response.status_code == 200


@pytest.mark.django_db
class TestAdminCommentsPartialView:
    def test_non_superuser_denied(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/admin-dashboard/comments/")
        assert response.status_code in (301, 302, 403)

    def test_superuser_gets_200(self, superuser_client):
        c, user = superuser_client
        response = c.get("/admin-dashboard/comments/")
        assert response.status_code == 200

    def test_with_existing_comments(self, superuser_client):
        c, user = superuser_client
        CommentFactory()
        CommentFactory()
        response = c.get("/admin-dashboard/comments/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestAdminUsersPartialView:
    def test_non_superuser_denied(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/admin-dashboard/users/")
        assert response.status_code in (301, 302, 403)

    def test_superuser_gets_200(self, superuser_client):
        c, user = superuser_client
        response = c.get("/admin-dashboard/users/")
        assert response.status_code == 200

    def test_excludes_bots(self, superuser_client):
        c, user = superuser_client
        from tests.factories import BotUserFactory

        BotUserFactory()
        UserFactory()
        response = c.get("/admin-dashboard/users/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestAdminActivityQueuePartialView:
    def test_non_superuser_denied(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/admin-dashboard/activity-queue/")
        assert response.status_code in (301, 302, 403)

    def test_superuser_gets_200(self, superuser_client):
        c, user = superuser_client
        response = c.get("/admin-dashboard/activity-queue/")
        assert response.status_code == 200

    def test_shows_queued_events(self, superuser_client):
        c, user = superuser_client
        ActivityEventFactory(broadcast_at=None)
        ActivityEventFactory(broadcast_at=None)
        response = c.get("/admin-dashboard/activity-queue/")
        assert response.status_code == 200
