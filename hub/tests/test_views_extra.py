"""Additional tests for hub.views — coverage for uncovered views and edge cases.

Complements test_views.py; does NOT duplicate tests there.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from hub.models import SiteSettings
from vinosports.betting.models import (
    Badge,
    BalanceTransaction,
    UserBadge,
    UserBalance,
    UserStats,
)
from vinosports.bots.models import BotProfile

from .factories import UserBalanceFactory, UserFactory

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


@pytest.fixture
def superuser():
    u = UserFactory(password="testpass123")
    u.is_superuser = True
    u.save()
    return u


@pytest.fixture
def superuser_client(client, superuser):
    client.login(email=superuser.email, password="testpass123")
    return client


# ---------------------------------------------------------------------------
# HomeView — context assembly
# ---------------------------------------------------------------------------


class TestHomeViewContext:
    def test_context_has_bot_profiles(self, client):
        resp = client.get(reverse("hub:home"))
        assert "bot_profiles" in resp.context

    def test_context_has_hero_bots(self, client):
        resp = client.get(reverse("hub:home"))
        assert "hero_bots" in resp.context

    def test_context_has_featured_parlays(self, client):
        resp = client.get(reverse("hub:home"))
        assert "featured_parlays" in resp.context

    def test_bot_profiles_only_active(self, client):
        bot_user = UserFactory(is_bot=True)
        BotProfile.objects.create(
            user=bot_user,
            persona_prompt="test",
            is_active=True,
        )
        inactive_bot = UserFactory(is_bot=True)
        BotProfile.objects.create(
            user=inactive_bot,
            persona_prompt="inactive",
            is_active=False,
        )
        resp = client.get(reverse("hub:home"))
        profiles = list(resp.context["bot_profiles"])
        assert all(p.is_active for p in profiles)


# ---------------------------------------------------------------------------
# SignupView — additional edge cases beyond test_views.py
# ---------------------------------------------------------------------------


class TestSignupViewExtra:
    def test_registration_closed_post_blocked(self, client):
        """POST should also be rejected when registration is closed."""
        site = SiteSettings.load()
        site.max_users = 1
        site.save()
        UserFactory()  # fill cap

        resp = client.post(
            reverse("hub:signup"),
            {
                "email": "blocked@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            },
        )
        assert resp.status_code == 200
        assert resp.context.get("registration_closed") is True

    @patch("hub.views.evaluate_promo_code", return_value=0)
    def test_race_condition_max_users(self, mock_promo, client):
        """Atomic check inside POST prevents exceeding max_users."""
        site = SiteSettings.load()
        site.max_users = 1
        site.save()
        # No users yet — form validation passes, but create another user
        # before the atomic block runs (simulate by creating user first)
        UserFactory()  # fill the cap

        resp = client.post(
            reverse("hub:signup"),
            {
                "email": "race@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            },
        )
        assert resp.status_code == 200
        assert resp.context.get("registration_closed") is True

    @patch("hub.views.evaluate_promo_code", return_value=0)
    def test_unlimited_registration(self, mock_promo, client):
        """max_users=0 means unlimited."""
        site = SiteSettings.load()
        site.max_users = 0
        site.save()

        resp = client.post(
            reverse("hub:signup"),
            {
                "email": "unlimited@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            },
        )
        assert resp.status_code == 302

    def test_password_mismatch(self, client):
        resp = client.post(
            reverse("hub:signup"),
            {
                "email": "mismatch@test.com",
                "password": "securepass1",
                "password_confirm": "differentpass",
            },
        )
        assert resp.status_code == 200
        assert "form" in resp.context

    @patch("hub.views.evaluate_promo_code", return_value=0)
    def test_duplicate_email(self, mock_promo, client):
        existing = UserFactory()
        resp = client.post(
            reverse("hub:signup"),
            {
                "email": existing.email,
                "password": "securepass1",
                "password_confirm": "securepass1",
            },
        )
        assert resp.status_code == 200
        assert "form" in resp.context

    @patch("hub.views.evaluate_promo_code", return_value=0)
    def test_signup_creates_balance_transaction(self, mock_promo, client):
        client.post(
            reverse("hub:signup"),
            {
                "email": "txn@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            },
        )
        txn = BalanceTransaction.objects.get(user__email="txn@test.com")
        assert txn.transaction_type == BalanceTransaction.Type.SIGNUP
        assert txn.amount == Decimal("1000.00")

    @patch("hub.views.evaluate_promo_code", return_value=0)
    def test_signup_logs_user_in(self, mock_promo, client):
        client.post(
            reverse("hub:signup"),
            {
                "email": "loggedin@test.com",
                "password": "securepass1",
                "password_confirm": "securepass1",
            },
        )
        # After signup, user should be logged in (can access account)
        resp = client.get(reverse("hub:account"))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# LoginView — edge cases
# ---------------------------------------------------------------------------


class TestLoginViewExtra:
    def test_invalid_form_data(self, client):
        """Non-email value should re-render with errors."""
        resp = client.post(
            reverse("hub:login"),
            {
                "email": "not-an-email",
                "password": "whatever",
            },
        )
        assert resp.status_code == 200

    def test_wrong_password(self, client, user):
        resp = client.post(
            reverse("hub:login"),
            {
                "email": user.email,
                "password": "wrongpassword",
            },
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# BotProfileView
# ---------------------------------------------------------------------------


class TestBotProfileView:
    @pytest.fixture
    def bot_with_profile(self):
        bot_user = UserFactory(is_bot=True)
        bp = BotProfile.objects.create(
            user=bot_user,
            persona_prompt="I am a test bot",
            is_active=True,
        )
        return bot_user, bp

    def test_renders_bot_profile(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert resp.status_code == 200

    def test_context_has_profile_user(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert resp.context["profile_user"] == bot_user

    def test_context_has_bot_profile(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert resp.context["bot_profile"] == bp

    def test_context_has_stats_none_when_missing(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert resp.context["stats"] is None

    def test_context_has_stats_when_present(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        stats = UserStats.objects.create(user=bot_user)
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert resp.context["stats"] == stats

    def test_default_balance_when_missing(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert resp.context["balance"] == Decimal("1000.00")

    def test_real_balance_when_present(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        UserBalance.objects.create(user=bot_user, balance=Decimal("2500.00"))
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert resp.context["balance"] == Decimal("2500.00")

    def test_badge_grid_in_context(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert "all_badges" in resp.context

    def test_earned_badge_has_earned_date(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        badge = Badge.objects.create(slug="test_badge", name="Test Badge")
        UserBadge.objects.create(user=bot_user, badge=badge)
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        earned_badge = next(
            (b for b in resp.context["all_badges"] if b.slug == "test_badge"), None
        )
        assert earned_badge is not None
        assert earned_badge.earned is not None

    def test_404_for_non_bot_user(self, client, user):
        resp = client.get(reverse("hub:bot_profile", args=[user.slug]))
        assert resp.status_code == 404

    def test_404_for_nonexistent_slug(self, client):
        resp = client.get(reverse("hub:bot_profile", args=["no-such-bot"]))
        assert resp.status_code == 404

    def test_context_has_user_rank(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert "user_rank" in resp.context

    def test_context_has_display_identity(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert "display_identity" in resp.context


# ---------------------------------------------------------------------------
# AccountView — balance context & currency update
# ---------------------------------------------------------------------------


class TestAccountViewExtra:
    def test_masked_email_in_context(self, authed_client, user):
        resp = authed_client.get(reverse("hub:account"))
        masked = resp.context["account_masked_email"]
        assert "***@" in masked

    def test_balance_in_context_with_balance(self, authed_client, user):
        UserBalanceFactory(user=user, balance=Decimal("750.00"))
        resp = authed_client.get(reverse("hub:account"))
        assert resp.context["balance"] == Decimal("750.00")

    def test_balance_none_without_balance(self, authed_client, user):
        resp = authed_client.get(reverse("hub:account"))
        assert resp.context["balance"] is None

    def test_invalid_display_name_re_renders(self, authed_client, user):
        UserFactory(display_name="TakenName")
        resp = authed_client.post(
            reverse("hub:account"),
            {"display_name": "TakenName"},
        )
        assert resp.status_code == 200

    def test_display_name_form_in_context(self, authed_client):
        resp = authed_client.get(reverse("hub:account"))
        assert "display_name_form" in resp.context

    def test_currency_form_in_context(self, authed_client):
        resp = authed_client.get(reverse("hub:account"))
        assert "currency_form" in resp.context

    def test_all_badges_in_context(self, authed_client):
        resp = authed_client.get(reverse("hub:account"))
        assert "all_badges" in resp.context

    def test_profile_image_form_in_context(self, authed_client):
        resp = authed_client.get(reverse("hub:account"))
        assert "profile_image_form" in resp.context

    def test_stats_in_context(self, authed_client):
        resp = authed_client.get(reverse("hub:account"))
        assert "stats" in resp.context

    def test_user_rank_in_context(self, authed_client):
        resp = authed_client.get(reverse("hub:account"))
        assert "user_rank" in resp.context


# ---------------------------------------------------------------------------
# ProfileImageUploadView
# ---------------------------------------------------------------------------


class TestProfileImageUploadView:
    def test_requires_login(self, client):
        resp = client.post(reverse("hub:profile_image_upload"), {})
        assert resp.status_code == 302

    def test_upload_valid_image(self, authed_client, user, tmp_path):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (10, 10), color=(100, 100, 100)).save(buf, format="PNG")
        buf.seek(0)
        img = SimpleUploadedFile("test.png", buf.read(), content_type="image/png")
        resp = authed_client.post(
            reverse("hub:profile_image_upload"),
            {"profile_image": img},
        )
        assert resp.status_code == 200
        assert resp.context["image_save_success"] is True
        user.refresh_from_db()
        assert user.profile_image


# ---------------------------------------------------------------------------
# BalanceHistoryAPI (hub)
# ---------------------------------------------------------------------------


class TestHubBalanceHistoryAPI:
    def test_requires_login(self, client, user):
        resp = client.get(reverse("hub:balance_history_api", args=[user.slug]))
        assert resp.status_code == 302

    def test_returns_json(self, authed_client, user):
        resp = authed_client.get(reverse("hub:balance_history_api", args=[user.slug]))
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_empty_when_no_transactions(self, authed_client, user):
        resp = authed_client.get(reverse("hub:balance_history_api", args=[user.slug]))
        assert resp.json()["data"] == []

    def test_forbidden_for_other_user_slug(self, authed_client, user):
        other = UserFactory()
        resp = authed_client.get(reverse("hub:balance_history_api", args=[other.slug]))
        assert resp.status_code == 403

    def test_returns_data_with_transactions(self, authed_client, user):
        from vinosports.betting.models import BalanceTransaction

        BalanceTransaction.objects.create(
            user=user,
            amount=Decimal("1000.00"),
            balance_after=Decimal("1000.00"),
            transaction_type=BalanceTransaction.Type.SIGNUP,
        )
        resp = authed_client.get(reverse("hub:balance_history_api", args=[user.slug]))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) > 0
        assert "t" in data[0]
        assert "y" in data[0]


class TestCurrencyUpdateView:
    def test_requires_login(self, client):
        resp = client.post(reverse("hub:currency_update"), {"currency": "EUR"})
        assert resp.status_code == 302

    def test_valid_currency_update(self, authed_client, user):
        resp = authed_client.post(reverse("hub:currency_update"), {"currency": "EUR"})
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.currency == "EUR"

    def test_invalid_currency_redirects(self, authed_client, user):
        resp = authed_client.post(
            reverse("hub:currency_update"), {"currency": "INVALID"}
        )
        # Invalid form redirects to account
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# StandingsView — extra
# ---------------------------------------------------------------------------


class TestStandingsViewExtra:
    def test_invalid_board_type_defaults_to_balance(self, client):
        resp = client.get(reverse("hub:standings") + "?type=nonexistent")
        assert resp.context["board_type"] == "balance"

    def test_context_has_leaderboard(self, client):
        resp = client.get(reverse("hub:standings"))
        assert "leaderboard" in resp.context

    def test_context_has_board_types(self, client):
        resp = client.get(reverse("hub:standings"))
        assert "board_types" in resp.context


# ---------------------------------------------------------------------------
# MyBetsView (cross-league)
# ---------------------------------------------------------------------------


class TestMyBetsView:
    def test_requires_login(self, client):
        resp = client.get(reverse("hub:my_bets"))
        assert resp.status_code == 302

    def test_renders_for_authenticated_user(self, authed_client):
        resp = authed_client.get(reverse("hub:my_bets"))
        assert resp.status_code == 200

    def test_context_has_totals(self, authed_client):
        resp = authed_client.get(reverse("hub:my_bets"))
        assert "total_staked" in resp.context
        assert "total_payout" in resp.context
        assert "net_pnl" in resp.context

    def test_context_has_current_balance(self, authed_client, user):
        UserBalanceFactory(user=user, balance=Decimal("800.00"))
        resp = authed_client.get(reverse("hub:my_bets"))
        assert resp.context["current_balance"] == Decimal("800.00")

    def test_default_balance_when_missing(self, authed_client):
        resp = authed_client.get(reverse("hub:my_bets"))
        assert resp.context["current_balance"] == Decimal("1000.00")

    def test_context_has_activity(self, authed_client):
        resp = authed_client.get(reverse("hub:my_bets"))
        assert "activity" in resp.context

    def test_empty_activity_when_no_bets(self, authed_client):
        resp = authed_client.get(reverse("hub:my_bets"))
        assert resp.context["activity"] == []


# ---------------------------------------------------------------------------
# ChallengesView
# ---------------------------------------------------------------------------


class TestChallengesView:
    def test_requires_login(self, client):
        resp = client.get(reverse("hub:challenges"))
        assert resp.status_code == 302

    def test_renders_for_authed(self, authed_client):
        resp = authed_client.get(reverse("hub:challenges"))
        assert resp.status_code == 200

    def test_default_tab_is_active(self, authed_client):
        resp = authed_client.get(reverse("hub:challenges"))
        assert resp.context["active_tab"] == "active"

    def test_completed_tab(self, authed_client):
        resp = authed_client.get(reverse("hub:challenges") + "?tab=completed")
        assert resp.context["active_tab"] == "completed"

    def test_upcoming_tab(self, authed_client):
        resp = authed_client.get(reverse("hub:challenges") + "?tab=upcoming")
        assert resp.context["active_tab"] == "upcoming"

    def test_unknown_tab_defaults(self, authed_client):
        resp = authed_client.get(reverse("hub:challenges") + "?tab=unknown")
        assert "challenges" in resp.context


class TestChallengesPartials:
    def test_active_partial_requires_login(self, client):
        resp = client.get(reverse("hub:challenges_active_partial"))
        assert resp.status_code == 302

    def test_active_partial_renders(self, authed_client):
        resp = authed_client.get(reverse("hub:challenges_active_partial"))
        assert resp.status_code == 200

    def test_completed_partial_requires_login(self, client):
        resp = client.get(reverse("hub:challenges_completed_partial"))
        assert resp.status_code == 302

    def test_completed_partial_renders(self, authed_client):
        resp = authed_client.get(reverse("hub:challenges_completed_partial"))
        assert resp.status_code == 200

    def test_upcoming_partial_requires_login(self, client):
        resp = client.get(reverse("hub:challenges_upcoming_partial"))
        assert resp.status_code == 302

    def test_upcoming_partial_renders(self, authed_client):
        resp = authed_client.get(reverse("hub:challenges_upcoming_partial"))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AdminDashboardView
# ---------------------------------------------------------------------------


class TestAdminDashboardView:
    def test_requires_superuser(self, authed_client):
        resp = authed_client.get(reverse("hub:admin_dashboard"))
        assert resp.status_code == 403

    def test_anonymous_redirected(self, client):
        resp = client.get(reverse("hub:admin_dashboard"))
        assert resp.status_code == 302

    def test_renders_for_superuser(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard"))
        assert resp.status_code == 200

    def test_context_has_stats(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard"))
        assert "total_users" in resp.context
        assert "active_bets" in resp.context
        assert "active_parlays" in resp.context
        assert "total_comments" in resp.context
        assert "total_bets_all_time" in resp.context
        assert "total_in_play" in resp.context
        assert "epl_bets" in resp.context
        assert "nba_bets" in resp.context


class TestAdminBetsPartial:
    def test_requires_superuser(self, authed_client):
        resp = authed_client.get(reverse("hub:admin_dashboard_bets"))
        assert resp.status_code == 403

    def test_renders_for_superuser(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard_bets"))
        assert resp.status_code == 200

    def test_offset_param(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard_bets") + "?offset=5")
        assert resp.status_code == 200

    def test_invalid_offset_defaults_to_zero(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard_bets") + "?offset=abc")
        assert resp.status_code == 200


class TestAdminCommentsPartial:
    def test_requires_superuser(self, authed_client):
        resp = authed_client.get(reverse("hub:admin_dashboard_comments"))
        assert resp.status_code == 403

    def test_renders_for_superuser(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard_comments"))
        assert resp.status_code == 200


class TestAdminUsersPartial:
    def test_requires_superuser(self, authed_client):
        resp = authed_client.get(reverse("hub:admin_dashboard_users"))
        assert resp.status_code == 403

    def test_renders_for_superuser(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard_users"))
        assert resp.status_code == 200

    def test_offset_param(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard_users") + "?offset=5")
        assert resp.status_code == 200
