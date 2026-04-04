"""Tests for hub.views — auth, account, standings."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from hub.models import SiteSettings
from vinosports.betting.models import BalanceTransaction, UserBalance
from vinosports.bots.models import BotProfile

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
        assert balance.balance == Decimal("100500.00")  # 100000 + 500

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


# ---------------------------------------------------------------------------
# Bot profile management
# ---------------------------------------------------------------------------

_BOT_FORM_DATA = {
    "persona_prompt": "A test bot persona",
    "tagline": "Testing 1-2-3",
    "strategy_type": "frontrunner",
    "risk_multiplier": "1.0",
    "max_daily_bets": "5",
    "active_in_epl": "on",
    "active_in_nba": "on",
    "active_in_nfl": "",
    "epl_team_tla": "",
    "nba_team_abbr": "",
    "nfl_team_abbr": "",
}


def _create_bot_for(owner, **profile_overrides):
    """Helper: create a bot User + BotProfile owned by *owner*."""
    defaults = {"persona_prompt": "test persona", "strategy_type": "frontrunner"}
    defaults.update(profile_overrides)
    bot_user = UserFactory(
        email=f"bot+{owner.id_hash}@vinosports.com",
        is_bot=True,
        display_name=f"Bot of {owner.id_hash}",
    )
    bot_user.created_by = owner
    bot_user.set_unusable_password()
    bot_user.save()
    profile = BotProfile.objects.create(user=bot_user, **defaults)
    return bot_user, profile


class TestCreateBotProfileView:
    def test_requires_login(self, client):
        resp = client.get(reverse("hub:create_bot_profile"))
        assert resp.status_code == 302

    def test_get_renders_form(self, authed_client):
        resp = authed_client.get(reverse("hub:create_bot_profile"))
        assert resp.status_code == 200
        assert "form" in resp.context

    def test_redirect_if_bot_exists(self, authed_client, user):
        _create_bot_for(user)
        resp = authed_client.get(reverse("hub:create_bot_profile"))
        assert resp.status_code == 302
        assert "edit" in resp["Location"]

    def test_create_makes_separate_bot_user(self, authed_client, user):
        authed_client.post(reverse("hub:create_bot_profile"), _BOT_FORM_DATA)
        user.refresh_from_db()
        # Owner should NOT become a bot
        assert user.is_bot is False
        # A separate bot user should exist
        from django.contrib.auth import get_user_model

        User = get_user_model()
        bot_user = User.objects.get(created_by=user)
        assert bot_user.is_bot is True
        assert not bot_user.has_usable_password()

    def test_create_creates_bot_profile(self, authed_client, user):
        authed_client.post(reverse("hub:create_bot_profile"), _BOT_FORM_DATA)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        bot_user = User.objects.get(created_by=user)
        assert BotProfile.objects.filter(user=bot_user).exists()

    def test_create_bot_profile_inactive_by_default(self, authed_client, user):
        authed_client.post(reverse("hub:create_bot_profile"), _BOT_FORM_DATA)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        bot_user = User.objects.get(created_by=user)
        assert bot_user.bot_profile.is_active is False

    def test_create_redirects_to_account(self, authed_client):
        resp = authed_client.post(reverse("hub:create_bot_profile"), _BOT_FORM_DATA)
        assert resp.status_code == 302
        assert resp["Location"].endswith(reverse("hub:account"))

    def test_create_sets_bot_display_name(self, authed_client, user):
        data = dict(_BOT_FORM_DATA, display_name="RoboGambler")
        authed_client.post(reverse("hub:create_bot_profile"), data)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        bot_user = User.objects.get(created_by=user)
        assert bot_user.display_name == "RoboGambler"

    def test_create_duplicate_display_name_rejected(self, authed_client):
        UserFactory(display_name="TakenName")
        data = dict(_BOT_FORM_DATA, display_name="TakenName")
        resp = authed_client.post(reverse("hub:create_bot_profile"), data)
        assert resp.status_code == 200
        assert "form" in resp.context

    def test_invalid_form_rerenders(self, authed_client):
        resp = authed_client.post(
            reverse("hub:create_bot_profile"), {"persona_prompt": ""}
        )
        assert resp.status_code == 200
        assert "form" in resp.context


class TestEditBotProfileView:
    def test_requires_login(self, client):
        resp = client.get(reverse("hub:edit_bot_profile"))
        assert resp.status_code == 302

    def test_redirect_if_no_bot(self, authed_client):
        resp = authed_client.get(reverse("hub:edit_bot_profile"))
        assert resp.status_code == 302
        assert "create" in resp["Location"]

    def test_get_renders_form_with_instance(self, authed_client, user):
        _create_bot_for(user, persona_prompt="original", strategy_type="underdog")
        resp = authed_client.get(reverse("hub:edit_bot_profile"))
        assert resp.status_code == 200
        assert resp.context["editing"] is True

    def test_post_updates_profile(self, authed_client, user):
        bot_user, _ = _create_bot_for(
            user, persona_prompt="original", strategy_type="underdog"
        )
        data = dict(_BOT_FORM_DATA, persona_prompt="updated persona")
        authed_client.post(reverse("hub:edit_bot_profile"), data)
        profile = BotProfile.objects.get(user=bot_user)
        assert profile.persona_prompt == "updated persona"

    def test_post_updates_bot_display_name(self, authed_client, user):
        bot_user, _ = _create_bot_for(
            user, persona_prompt="original", strategy_type="underdog"
        )
        data = dict(_BOT_FORM_DATA, display_name="NewBotName")
        authed_client.post(reverse("hub:edit_bot_profile"), data)
        bot_user.refresh_from_db()
        assert bot_user.display_name == "NewBotName"

    def test_post_redirects_to_account(self, authed_client, user):
        _create_bot_for(user, persona_prompt="original", strategy_type="underdog")
        resp = authed_client.post(reverse("hub:edit_bot_profile"), _BOT_FORM_DATA)
        assert resp.status_code == 302
        assert resp["Location"].endswith(reverse("hub:account"))


class TestToggleBotProfileView:
    def test_requires_login(self, client):
        resp = client.post(reverse("hub:toggle_bot_profile"))
        assert resp.status_code == 302
        assert "login" in resp["Location"]

    def test_redirect_if_no_bot(self, authed_client):
        resp = authed_client.post(reverse("hub:toggle_bot_profile"))
        assert resp.status_code == 302
        assert "create" in resp["Location"]

    def test_activates_inactive_profile(self, authed_client, user):
        _, profile = _create_bot_for(user, is_active=False)
        authed_client.post(reverse("hub:toggle_bot_profile"))
        profile.refresh_from_db()
        assert profile.is_active is True

    def test_deactivates_active_profile(self, authed_client, user):
        _, profile = _create_bot_for(user, is_active=True)
        authed_client.post(reverse("hub:toggle_bot_profile"))
        profile.refresh_from_db()
        assert profile.is_active is False

    def test_redirects_to_account(self, authed_client, user):
        _create_bot_for(user, is_active=False)
        resp = authed_client.post(reverse("hub:toggle_bot_profile"))
        assert resp.status_code == 302
        assert resp["Location"].endswith(reverse("hub:account"))


class TestAccountViewBotProfileContext:
    def test_bot_profile_none_when_not_created(self, authed_client):
        resp = authed_client.get(reverse("hub:account"))
        assert resp.status_code == 200
        assert resp.context["bot_profile"] is None

    def test_bot_profile_in_context_when_exists(self, authed_client, user):
        _create_bot_for(user)
        resp = authed_client.get(reverse("hub:account"))
        assert resp.context["bot_profile"] is not None
        assert resp.context["bot_user"] is not None
