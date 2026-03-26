"""Tests for hub.views — auth, account, standings."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from hub.models import SiteSettings
from vinosports.betting.models import BalanceTransaction, UserBalance

from .factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user():
    return UserFactory(password="testpass123")


@pytest.fixture
def authed_client(client, user):
    client.login(email=user.email, password="testpass123")
    return client


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------


class TestHomeView:
    def test_renders(self, client):
        resp = client.get(reverse("hub:home"))
        assert resp.status_code == 200

    def test_uses_home_template(self, client):
        resp = client.get(reverse("hub:home"))
        assert "hub/home.html" in [t.name for t in resp.templates]


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


class TestSignupView:
    def test_get_renders_form(self, client):
        resp = client.get(reverse("hub:signup"))
        assert resp.status_code == 200
        assert "form" in resp.context

    def test_authenticated_user_redirected(self, authed_client):
        resp = authed_client.get(reverse("hub:signup"))
        assert resp.status_code == 302

    @patch("hub.views.evaluate_promo_code", return_value=0)
    def test_successful_signup(self, mock_promo, client):
        resp = client.post(
            reverse("hub:signup"),
            {
                "email": "new@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            },
        )
        assert resp.status_code == 302
        # User created with balance
        assert UserBalance.objects.filter(user__email="new@test.com").exists()
        # Signup transaction created
        txn = BalanceTransaction.objects.get(user__email="new@test.com")
        assert txn.transaction_type == BalanceTransaction.Type.SIGNUP

    @patch("hub.views.evaluate_promo_code", return_value=500)
    def test_promo_code_adds_bonus(self, mock_promo, client):
        resp = client.post(
            reverse("hub:signup"),
            {
                "email": "promo@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
                "promo_code": "COOLCODE",
            },
        )
        assert resp.status_code == 302
        balance = UserBalance.objects.get(user__email="promo@test.com")
        assert balance.balance == Decimal("1500.00")  # 1000 + 500

    def test_registration_closed(self, client):
        site = SiteSettings.load()
        site.max_users = 1
        site.save()
        UserFactory()  # fills the cap

        resp = client.get(reverse("hub:signup"))
        assert resp.status_code == 200
        assert resp.context.get("registration_closed") is True

    def test_invalid_form_re_renders(self, client):
        resp = client.post(
            reverse("hub:signup"),
            {
                "email": "bad",
                "password": "short",
                "password_confirm": "short",
            },
        )
        assert resp.status_code == 200
        assert "form" in resp.context


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLoginView:
    def test_get_renders_form(self, client):
        resp = client.get(reverse("hub:login"))
        assert resp.status_code == 200

    def test_authenticated_user_redirected(self, authed_client):
        resp = authed_client.get(reverse("hub:login"))
        assert resp.status_code == 302

    def test_valid_login(self, client, user):
        resp = client.post(
            reverse("hub:login"),
            {
                "email": user.email,
                "password": "testpass123",
            },
        )
        assert resp.status_code == 302

    def test_invalid_credentials(self, client):
        resp = client.post(
            reverse("hub:login"),
            {
                "email": "nobody@test.com",
                "password": "wrongpass",
            },
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class TestLogoutView:
    def test_post_logs_out(self, authed_client):
        resp = authed_client.post(reverse("hub:logout"))
        assert resp.status_code == 302
        # Verify logged out
        resp2 = authed_client.get(reverse("hub:account"))
        assert resp2.status_code == 302  # redirects to login


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


class TestAccountView:
    def test_requires_login(self, client):
        resp = client.get(reverse("hub:account"))
        assert resp.status_code == 302

    def test_renders_for_authed_user(self, authed_client):
        resp = authed_client.get(reverse("hub:account"))
        assert resp.status_code == 200

    def test_update_display_name(self, authed_client, user):
        resp = authed_client.post(
            reverse("hub:account"),
            {
                "display_name": "NewDisplayName",
            },
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.display_name == "NewDisplayName"


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------


class TestStandingsView:
    def test_renders(self, client):
        resp = client.get(reverse("hub:standings"))
        assert resp.status_code == 200

    def test_board_type_in_context(self, client):
        resp = client.get(reverse("hub:standings") + "?type=profit")
        assert resp.context["board_type"] == "profit"

    def test_default_board_type(self, client):
        resp = client.get(reverse("hub:standings"))
        assert resp.context["board_type"] == "balance"
