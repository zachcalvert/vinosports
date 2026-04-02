"""Tests for website/views.py (DashboardView, AccountView, ThemeToggleView, etc.)."""

import pytest
from django.test import Client

from nba.tests.factories import (
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
    def test_anonymous_user_can_browse(self, client):
        response = client.get("/nba/")
        assert response.status_code == 200

    def test_authenticated_user_gets_200(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/nba/")
        assert response.status_code == 200

    def test_uses_dashboard_template(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/nba/")
        assert "nba_website/dashboard.html" in [t.name for t in response.templates]

    def test_context_contains_game_lists(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/nba/")
        assert "live_games" in response.context
        assert "upcoming_games" in response.context
        assert "final_games" in response.context
        assert "today" in response.context

    def test_no_games_shows_empty_lists(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/nba/")
        assert list(response.context["live_games"]) == []
        assert list(response.context["upcoming_games"]) == []
        assert list(response.context["final_games"]) == []


@pytest.mark.django_db
class TestLogoutView:
    def test_get_redirects_to_root(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/nba/logout/")
        assert response.status_code in (301, 302)

    def test_post_redirects_to_root(self, logged_in_client):
        c, user = logged_in_client
        response = c.post("/nba/logout/")
        assert response.status_code in (301, 302)

    def test_logs_out_user(self, logged_in_client):
        c, user = logged_in_client
        c.post("/nba/logout/")
        response = c.get("/nba/")
        # After logout, dashboard is still accessible (open browsing)
        assert response.status_code == 200


@pytest.mark.django_db
class TestAccountView:
    def test_redirects_unauthenticated_user(self, client):
        response = client.get("/nba/account/")
        assert response.status_code in (301, 302)

    def test_authenticated_user_gets_200(self, logged_in_client):
        c, user = logged_in_client
        UserBalanceFactory(user=user)
        response = c.get("/nba/account/")
        assert response.status_code == 200

    def test_uses_account_template(self, logged_in_client):
        c, user = logged_in_client
        response = c.get("/nba/account/")
        assert "nba_website/account.html" in [t.name for t in response.templates]

    def test_context_has_balance_and_stats(self, logged_in_client):
        c, user = logged_in_client
        UserBalanceFactory(user=user)
        response = c.get("/nba/account/")
        assert "balance" in response.context
        assert "stats" in response.context
        assert "transactions" in response.context

    def test_account_view_without_balance(self, logged_in_client):
        """AccountView should still render when user has no balance."""
        c, user = logged_in_client
        response = c.get("/nba/account/")
        assert response.status_code == 200
        assert response.context["balance"] is None


@pytest.mark.django_db
class TestThemeToggleView:
    def test_post_redirects(self, logged_in_client):
        c, user = logged_in_client
        response = c.post("/nba/theme/toggle/")
        assert response.status_code in (301, 302)

    def test_post_with_theme_sets_session(self, logged_in_client):
        c, user = logged_in_client
        c.post("/nba/theme/toggle/", {"theme": "dark"})
        session = c.session
        assert session.get("theme_preference") == "dark"

    def test_post_toggles_from_light_to_dark(self, logged_in_client):
        c, user = logged_in_client
        session = c.session
        session["theme_preference"] = "light"
        session.save()
        c.post("/nba/theme/toggle/")
        session = c.session
        assert session.get("theme_preference") == "dark"

    def test_post_toggles_from_dark_to_light(self, logged_in_client):
        c, user = logged_in_client
        session = c.session
        session["theme_preference"] = "dark"
        session.save()
        c.post("/nba/theme/toggle/")
        session = c.session
        assert session.get("theme_preference") == "light"

    def test_post_invalid_theme_uses_default(self, logged_in_client):
        c, user = logged_in_client
        c.post("/nba/theme/toggle/", {"theme": "rainbow"})
        session = c.session
        assert session.get("theme_preference") == "light"
