"""Tests for website/views.py — AccountView, ThemeToggleView, etc."""

import pytest
from django.test import Client

from .factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def authed_client():
    user = UserFactory(password="testpass123")
    c = Client()
    c.login(email=user.email, password="testpass123")
    return c, user


class TestHowItWorksView:
    def test_renders(self, client):
        resp = client.get("/epl/how-it-works/")
        assert resp.status_code == 200
        assert "components" in resp.context
        assert "flows" in resp.context


class TestComponentDetailView:
    def test_renders_valid_component(self, client):
        resp = client.get("/epl/how-it-works/component/?name=django")
        assert resp.status_code == 200

    def test_404_for_invalid_component(self, client):
        resp = client.get("/epl/how-it-works/component/?name=nonexistent")
        assert resp.status_code == 404

    def test_404_when_no_name(self, client):
        resp = client.get("/epl/how-it-works/component/")
        assert resp.status_code == 404


class TestLogoutView:
    def test_post_redirects(self, authed_client):
        c, user = authed_client
        resp = c.post("/epl/logout/")
        assert resp.status_code in (301, 302)

    def test_logs_out_user(self, authed_client):
        c, user = authed_client
        c.post("/epl/logout/")
        # Verify logged out by checking a protected page
        resp = c.get("/epl/account/")
        assert resp.status_code in (301, 302)


class TestThemeToggleView:
    def test_post_redirects(self, authed_client):
        c, user = authed_client
        resp = c.post("/epl/theme/toggle/")
        assert resp.status_code in (301, 302)

    def test_sets_theme_from_post_data(self, authed_client):
        c, user = authed_client
        c.post("/epl/theme/toggle/", {"theme": "dark"})
        session = c.session
        assert session.get("theme_preference") == "dark"

    def test_toggles_from_light_to_dark(self, authed_client):
        c, user = authed_client
        session = c.session
        session["theme_preference"] = "light"
        session.save()
        c.post("/epl/theme/toggle/")
        session = c.session
        assert session.get("theme_preference") == "dark"

    def test_toggles_from_dark_to_light(self, authed_client):
        c, user = authed_client
        session = c.session
        session["theme_preference"] = "dark"
        session.save()
        c.post("/epl/theme/toggle/")
        session = c.session
        assert session.get("theme_preference") == "light"

    def test_invalid_theme_defaults_to_light(self, authed_client):
        c, user = authed_client
        c.post("/epl/theme/toggle/", {"theme": "rainbow"})
        session = c.session
        assert session.get("theme_preference") == "light"

    def test_redirects_to_referer(self, authed_client):
        c, user = authed_client
        resp = c.post(
            "/epl/theme/toggle/",
            HTTP_REFERER="http://testserver/epl/table/",
        )
        assert resp.status_code in (301, 302)
        assert "/epl/table/" in resp.url

    def test_unsafe_next_url_redirects_to_dashboard(self, authed_client):
        c, user = authed_client
        resp = c.post(
            "/epl/theme/toggle/",
            {"next": "https://evil.com/steal"},
        )
        assert resp.status_code in (301, 302)
        assert "/epl/" in resp.url


class TestAccountView:
    def test_redirects_unauthenticated(self, client):
        resp = client.get("/epl/account/")
        assert resp.status_code in (301, 302)

    def test_post_htmx_valid_display_name(self, authed_client):
        c, user = authed_client
        resp = c.post(
            "/epl/account/",
            {"display_name": "NewName"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.display_name == "NewName"
        templates = [t.name for t in resp.templates]
        assert "epl_website/partials/account_settings_card.html" in templates

    def test_post_htmx_empty_display_name_accepted(self, authed_client):
        c, user = authed_client
        resp = c.post(
            "/epl/account/",
            {"display_name": ""},
            HTTP_HX_REQUEST="true",
        )
        # display_name allows blank on the User model
        assert resp.status_code == 200


class TestCurrencyUpdateView:
    def test_redirects_unauthenticated(self, client):
        resp = client.post("/epl/account/currency/", {"currency": "USD"})
        assert resp.status_code in (301, 302)

    def test_htmx_valid_returns_partial(self, authed_client):
        c, user = authed_client
        resp = c.post(
            "/epl/account/currency/",
            {"currency": "GBP"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200

    def test_non_htmx_redirects_on_success(self, authed_client):
        c, user = authed_client
        resp = c.post(
            "/epl/account/currency/",
            {"currency": "GBP"},
        )
        assert resp.status_code in (301, 302)
