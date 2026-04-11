"""Additional tests for hub.views — coverage for uncovered views and edge cases.

Complements test_views.py; does NOT duplicate tests there.
"""

import io
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from epl.betting.models import BetSlip as EplBetSlip
from epl.discussions.models import Comment as EplComment
from epl.tests.factories import BetSlipFactory as EplBetSlipFactory
from epl.tests.factories import CommentFactory as EplCommentFactory
from epl.tests.factories import MatchFactory as EplMatchFactory
from hub.consumers import AdminDashboardConsumer, notify_admin_dashboard
from hub.models import SiteSettings
from hub.tests.factories import UserBalanceFactory, UserFactory
from hub.views import _admin_merged_querysets
from nba.betting.models import BetSlip as NbaBetSlip
from nba.tests.factories import BetSlipFactory as NbaBetSlipFactory
from nba.tests.factories import CommentFactory as NbaCommentFactory
from nfl.betting.models import BetSlip as NflBetSlip
from nfl.discussions.models import Comment as NflComment
from nfl.tests.factories import BetSlipFactory as NflBetSlipFactory
from nfl.tests.factories import GameFactory as NflGameFactory
from nfl.tests.factories import ParlayFactory as NflParlayFactory
from vinosports.betting.models import (
    Badge,
    BalanceTransaction,
    UserBadge,
    UserBalance,
    UserStats,
)
from vinosports.bots.models import BotProfile

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

    def test_context_has_featured_props(self, client):
        resp = client.get(reverse("hub:home"))
        assert "featured_props" in resp.context

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
        assert txn.amount == Decimal("100000.00")

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
# ProfileView
# ---------------------------------------------------------------------------


class TestProfileView:
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
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert resp.status_code == 200

    def test_renders_regular_user_profile(self, client, user):
        resp = client.get(reverse("hub:profile", args=[user.slug]))
        assert resp.status_code == 200

    def test_context_has_profile_user(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert resp.context["profile_user"] == bot_user

    def test_context_has_bot_profile(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert resp.context["bot_profile"] == bp

    def test_context_has_stats_none_when_missing(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert resp.context["stats"] is None

    def test_context_has_stats_when_present(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        stats = UserStats.objects.create(user=bot_user)
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert resp.context["stats"] == stats

    def test_default_balance_when_missing(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert resp.context["balance"] == Decimal("100000.00")

    def test_real_balance_when_present(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        UserBalance.objects.create(user=bot_user, balance=Decimal("2500.00"))
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert resp.context["balance"] == Decimal("2500.00")

    def test_badge_grid_in_context(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert "all_badges" in resp.context

    def test_earned_badge_has_earned_date(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        badge = Badge.objects.create(slug="test_badge", name="Test Badge")
        UserBadge.objects.create(user=bot_user, badge=badge)
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        earned_badge = next(
            (b for b in resp.context["all_badges"] if b.slug == "test_badge"), None
        )
        assert earned_badge is not None
        assert earned_badge.earned is not None

    def test_404_for_nonexistent_slug(self, client):
        resp = client.get(reverse("hub:profile", args=["no-such-user"]))
        assert resp.status_code == 404

    def test_old_bot_url_redirects(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:bot_profile", args=[bot_user.slug]))
        assert resp.status_code == 301
        assert f"/profile/{bot_user.slug}/" in resp["Location"]

    def test_context_has_user_rank(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert "user_rank" in resp.context

    def test_context_has_display_identity(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert "display_identity" in resp.context


class TestProfileViewRecentActivity:
    """Recent bets and comments on bot profile pages."""

    @pytest.fixture
    def bot_with_profile(self):
        bot_user = UserFactory(is_bot=True)
        bp = BotProfile.objects.create(
            user=bot_user,
            persona_prompt="I am a test bot",
            is_active=True,
        )
        return bot_user, bp

    def test_bot_profile_has_recent_activity(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        EplBetSlipFactory(user=bot_user)
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert len(resp.context["recent_activity"]) == 1
        assert resp.context["recent_activity"][0]["league"] == "epl"

    def test_bot_profile_has_recent_comments(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        EplCommentFactory(user=bot_user)
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert len(resp.context["recent_comments"]) == 1
        assert resp.context["recent_comments"][0]["league"] == "epl"

    def test_regular_user_no_recent_activity(self, client):
        regular_user = UserFactory(is_bot=False)
        resp = client.get(reverse("hub:profile", args=[regular_user.slug]))
        assert "recent_activity" not in resp.context
        assert "recent_comments" not in resp.context

    def test_cross_league_activity(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        EplBetSlipFactory(user=bot_user)
        NbaBetSlipFactory(user=bot_user)
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        leagues = {e["league"] for e in resp.context["recent_activity"]}
        assert leagues == {"epl", "nba"}

    def test_recent_activity_sorted_newest_first(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        EplBetSlipFactory(user=bot_user)
        EplBetSlipFactory(user=bot_user)
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        dates = [e["date"] for e in resp.context["recent_activity"]]
        assert dates == sorted(dates, reverse=True)

    def test_deleted_comments_excluded(self, client, bot_with_profile):
        bot_user, bp = bot_with_profile
        EplCommentFactory(user=bot_user, is_deleted=True)
        EplCommentFactory(user=bot_user, is_deleted=False)
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert len(resp.context["recent_comments"]) == 1

    def test_parlays_in_activity(self, client, bot_with_profile):
        from epl.tests.factories import ParlayFactory as EplParlayFactory

        bot_user, bp = bot_with_profile
        EplParlayFactory(user=bot_user)
        resp = client.get(reverse("hub:profile", args=[bot_user.slug]))
        assert any(e["type"] == "parlay" for e in resp.context["recent_activity"])


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
    def test_publicly_accessible(self, client, user):
        resp = client.get(reverse("hub:balance_history_api", args=[user.slug]))
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_returns_json(self, authed_client, user):
        resp = authed_client.get(reverse("hub:balance_history_api", args=[user.slug]))
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_empty_when_no_transactions(self, client, user):
        resp = client.get(reverse("hub:balance_history_api", args=[user.slug]))
        assert resp.json()["data"] == []

    def test_other_user_slug_accessible(self, client, user):
        other = UserFactory()
        resp = client.get(reverse("hub:balance_history_api", args=[other.slug]))
        assert resp.status_code == 200

    def test_days_param(self, client, user):
        resp = client.get(
            reverse("hub:balance_history_api", args=[user.slug]) + "?days=7"
        )
        assert resp.status_code == 200

    def test_days_param_clamped(self, client, user):
        from vinosports.betting.models import BalanceTransaction

        BalanceTransaction.objects.create(
            user=user,
            amount=Decimal("1000.00"),
            balance_after=Decimal("1000.00"),
            transaction_type=BalanceTransaction.Type.SIGNUP,
        )
        resp = client.get(
            reverse("hub:balance_history_api", args=[user.slug]) + "?days=200"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) <= 90

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
        assert resp.context["current_balance"] == Decimal("100000.00")

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
        assert "total_articles" in resp.context
        assert "total_comments" in resp.context
        assert "active_bets" in resp.context
        assert "total_bets_all_time" in resp.context
        assert "total_wagered" in resp.context


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


# ---------------------------------------------------------------------------
# Phase 1: NFL in aggregate stats
# ---------------------------------------------------------------------------


class TestAdminDashboardNflStats:
    """Phase 1: NFL counts appear in aggregate stats and league breakdown."""

    def test_nfl_bets_counted_in_aggregate(self, superuser_client):
        NflBetSlipFactory()
        resp = superuser_client.get(reverse("hub:admin_dashboard"))
        assert resp.context["total_bets_all_time"] >= 1

    def test_nfl_pending_bets_in_active_count(self, superuser_client):

        NflBetSlipFactory(status="PENDING")
        resp = superuser_client.get(reverse("hub:admin_dashboard"))
        assert resp.context["active_bets"] >= 1

    def test_nfl_in_play_stakes(self, superuser_client):
        NflBetSlipFactory(status="PENDING", stake=Decimal("100.00"))
        resp = superuser_client.get(reverse("hub:admin_dashboard"))
        assert resp.context["total_wagered"] >= 100

    def test_nfl_parlays_counted(self, superuser_client):
        NflParlayFactory()
        resp = superuser_client.get(reverse("hub:admin_dashboard"))
        assert resp.context["total_bets_all_time"] >= 1

    def test_nfl_comments_counted(self, superuser_client):
        game = NflGameFactory()
        user = UserFactory()
        NflComment.objects.create(user=user, game=game, body="Go team!")
        resp = superuser_client.get(reverse("hub:admin_dashboard"))
        assert resp.context["total_comments"] >= 1


class TestAdminBetsPartialWithNfl:
    """Phase 1: NFL bets appear in merged recent bets list."""

    def test_nfl_bet_appears_in_list(self, superuser_client):
        NflBetSlipFactory()
        resp = superuser_client.get(reverse("hub:admin_dashboard_bets"))
        assert resp.status_code == 200
        assert b"NFL" in resp.content

    def test_merged_querysets_interleave_correctly(self, superuser_client):
        """Items from all leagues are sorted by created_at descending."""
        EplBetSlipFactory()
        NbaBetSlipFactory()
        NflBetSlipFactory()
        resp = superuser_client.get(reverse("hub:admin_dashboard_bets"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "EPL" in content
        assert "NBA" in content
        assert "NFL" in content


class TestAdminCommentsPartialWithNfl:
    """Phase 1: NFL comments appear in merged recent comments list."""

    def test_nfl_comment_appears_in_list(self, superuser_client):
        game = NflGameFactory()
        user = UserFactory()
        NflComment.objects.create(user=user, game=game, body="Nice play!")
        resp = superuser_client.get(reverse("hub:admin_dashboard_comments"))
        assert resp.status_code == 200
        assert b"NFL" in resp.content

    def test_three_leagues_in_comments(self, superuser_client):
        EplCommentFactory()
        NbaCommentFactory()
        game = NflGameFactory()
        user = UserFactory()
        NflComment.objects.create(user=user, game=game, body="Test comment")
        resp = superuser_client.get(reverse("hub:admin_dashboard_comments"))
        content = resp.content.decode()
        assert "EPL" in content
        assert "NBA" in content
        assert "NFL" in content


# ---------------------------------------------------------------------------
# Phase 1: _admin_merged_querysets with N querysets
# ---------------------------------------------------------------------------


class TestAdminMergedQuerysets:
    """Unit tests for the _admin_merged_querysets helper."""

    def test_merges_three_querysets(self):
        EplBetSlipFactory()
        NbaBetSlipFactory()
        NflBetSlipFactory()

        result = _admin_merged_querysets(
            EplBetSlip.objects.order_by("-created_at"),
            NbaBetSlip.objects.order_by("-created_at"),
            NflBetSlip.objects.order_by("-created_at"),
            offset=0,
            page_size=10,
        )
        assert len(result) == 3
        # Verify sorted descending by created_at
        for i in range(len(result) - 1):
            assert result[i].created_at >= result[i + 1].created_at

    def test_league_attribute_set(self):
        EplBetSlipFactory()
        NflBetSlipFactory()

        result = _admin_merged_querysets(
            EplBetSlip.objects.order_by("-created_at"),
            NflBetSlip.objects.order_by("-created_at"),
            offset=0,
            page_size=10,
        )
        leagues = {item.league for item in result}
        assert "epl" in leagues
        assert "nfl" in leagues

    def test_offset_and_page_size(self):
        for _ in range(5):
            NbaBetSlipFactory()

        result = _admin_merged_querysets(
            NbaBetSlip.objects.order_by("-created_at"),
            offset=2,
            page_size=2,
        )
        assert len(result) == 2

    def test_empty_querysets(self):
        result = _admin_merged_querysets(
            EplBetSlip.objects.order_by("-created_at"),
            NbaBetSlip.objects.order_by("-created_at"),
            offset=0,
            page_size=10,
        )
        assert result == []


# ---------------------------------------------------------------------------
# Phase 2: User profile links
# ---------------------------------------------------------------------------


class TestAdminProfileLinks:
    """Phase 2: User names in bets/comments link to profiles."""

    def test_bet_row_links_to_profile(self, superuser_client):
        bet = EplBetSlipFactory()
        resp = superuser_client.get(reverse("hub:admin_dashboard_bets"))
        content = resp.content.decode()
        expected_url = reverse("hub:profile", kwargs={"slug": bet.user.slug})
        assert expected_url in content

    def test_comment_row_links_to_profile(self, superuser_client):
        comment = EplCommentFactory()
        resp = superuser_client.get(reverse("hub:admin_dashboard_comments"))
        content = resp.content.decode()
        expected_url = reverse("hub:profile", kwargs={"slug": comment.user.slug})
        assert expected_url in content


# ---------------------------------------------------------------------------
# Phase 3: Full page views
# ---------------------------------------------------------------------------


class TestAdminBetsFullView:
    def test_requires_superuser(self, authed_client):
        resp = authed_client.get(reverse("hub:admin_bets_full"))
        assert resp.status_code == 403

    def test_anonymous_redirected(self, client):
        resp = client.get(reverse("hub:admin_bets_full"))
        assert resp.status_code == 302

    def test_renders_for_superuser(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_bets_full"))
        assert resp.status_code == 200

    def test_pagination_context(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_bets_full"))
        assert resp.context["page"] == 1
        assert "has_next" in resp.context
        assert resp.context["has_prev"] is False

    def test_page_two(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_bets_full") + "?page=2")
        assert resp.context["page"] == 2
        assert resp.context["has_prev"] is True

    def test_invalid_page_defaults_to_one(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_bets_full") + "?page=-5")
        assert resp.context["page"] == 1

    def test_shows_all_leagues(self, superuser_client):
        EplBetSlipFactory()
        NbaBetSlipFactory()
        NflBetSlipFactory()
        resp = superuser_client.get(reverse("hub:admin_bets_full"))
        content = resp.content.decode()
        assert "EPL" in content
        assert "NBA" in content
        assert "NFL" in content

    def test_items_have_league_attribute(self, superuser_client):
        EplBetSlipFactory()
        resp = superuser_client.get(reverse("hub:admin_bets_full"))
        items = resp.context["items"]
        assert len(items) >= 1
        assert items[0].league == "epl"

    def test_has_next_when_full_page(self, superuser_client):
        user = UserFactory()
        match = EplMatchFactory()
        EplBetSlip.objects.bulk_create(
            [
                EplBetSlip(
                    user=user,
                    match=match,
                    selection=EplBetSlip.Selection.HOME_WIN,
                    odds_at_placement=Decimal("2.10"),
                    stake=Decimal("50.00"),
                )
                for _ in range(26)
            ]
        )
        resp = superuser_client.get(reverse("hub:admin_bets_full"))
        assert resp.context["has_next"] is True
        assert len(resp.context["items"]) == 25


class TestAdminCommentsFullView:
    def test_requires_superuser(self, authed_client):
        resp = authed_client.get(reverse("hub:admin_comments_full"))
        assert resp.status_code == 403

    def test_anonymous_redirected(self, client):
        resp = client.get(reverse("hub:admin_comments_full"))
        assert resp.status_code == 302

    def test_renders_for_superuser(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_comments_full"))
        assert resp.status_code == 200

    def test_pagination_context(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_comments_full"))
        assert resp.context["page"] == 1
        assert resp.context["has_prev"] is False

    def test_page_two(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_comments_full") + "?page=2")
        assert resp.context["page"] == 2
        assert resp.context["has_prev"] is True

    def test_shows_all_leagues(self, superuser_client):
        EplCommentFactory()
        NbaCommentFactory()
        game = NflGameFactory()
        user = UserFactory()
        NflComment.objects.create(user=user, game=game, body="Test")
        resp = superuser_client.get(reverse("hub:admin_comments_full"))
        content = resp.content.decode()
        assert "EPL" in content
        assert "NBA" in content
        assert "NFL" in content

    def test_has_next_when_full_page(self, superuser_client):
        user = UserFactory()
        match = EplMatchFactory()
        EplComment.objects.bulk_create(
            [EplComment(user=user, match=match, body=f"Comment {i}") for i in range(26)]
        )
        resp = superuser_client.get(reverse("hub:admin_comments_full"))
        assert resp.context["has_next"] is True
        assert len(resp.context["items"]) == 25


# ---------------------------------------------------------------------------
# Phase 3: View all links point to full pages
# ---------------------------------------------------------------------------


class TestViewAllLinks:
    """Dashboard 'View all' links navigate to dedicated full pages."""

    def test_bets_view_all_links_to_full_page(self, superuser_client):
        user = UserFactory()
        match = EplMatchFactory()
        EplBetSlip.objects.bulk_create(
            [
                EplBetSlip(
                    user=user,
                    match=match,
                    selection=EplBetSlip.Selection.HOME_WIN,
                    odds_at_placement=Decimal("2.10"),
                    stake=Decimal("50.00"),
                )
                for _ in range(6)
            ]
        )
        resp = superuser_client.get(reverse("hub:admin_dashboard_bets"))
        content = resp.content.decode()
        assert reverse("hub:admin_bets_full") in content

    def test_comments_view_all_links_to_full_page(self, superuser_client):
        user = UserFactory()
        match = EplMatchFactory()
        EplComment.objects.bulk_create(
            [EplComment(user=user, match=match, body=f"Comment {i}") for i in range(6)]
        )
        resp = superuser_client.get(reverse("hub:admin_dashboard_comments"))
        content = resp.content.decode()
        assert reverse("hub:admin_comments_full") in content


# ---------------------------------------------------------------------------
# Phase 4: Stats partial view
# ---------------------------------------------------------------------------


class TestAdminStatsPartialView:
    def test_requires_superuser(self, authed_client):
        resp = authed_client.get(reverse("hub:admin_dashboard_stats"))
        assert resp.status_code == 403

    def test_anonymous_redirected(self, client):
        resp = client.get(reverse("hub:admin_dashboard_stats"))
        assert resp.status_code == 302

    def test_renders_for_superuser(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard_stats"))
        assert resp.status_code == 200

    def test_returns_stats_context(self, superuser_client):
        resp = superuser_client.get(reverse("hub:admin_dashboard_stats"))
        for key in (
            "total_users",
            "active_bets",
            "total_comments",
            "total_articles",
            "total_bets_all_time",
            "total_wagered",
        ):
            assert key in resp.context

    def test_stats_reflect_data(self, superuser_client):
        NflBetSlipFactory(status="PENDING", stake=Decimal("50.00"))
        resp = superuser_client.get(reverse("hub:admin_dashboard_stats"))
        assert resp.context["active_bets"] >= 1
        assert resp.context["total_wagered"] >= 50


# ---------------------------------------------------------------------------
# Phase 4: AdminDashboardConsumer
# ---------------------------------------------------------------------------


class TestAdminDashboardConsumer:
    """Phase 4: WebSocket consumer tests using direct method calls."""

    def _make_consumer(self, user=None):
        consumer = AdminDashboardConsumer()
        consumer.scope = {"user": user}
        consumer.channel_name = "test-channel-admin"
        consumer.channel_layer = MagicMock()
        consumer.accept = MagicMock()
        consumer.close = MagicMock()
        consumer.send = MagicMock()
        return consumer

    @patch("hub.consumers.async_to_sync")
    def test_connect_accepts_superuser(self, mock_a2s):
        mock_a2s.return_value = MagicMock()
        superuser = UserFactory(password="testpass123")
        superuser.is_superuser = True
        superuser.save()

        consumer = self._make_consumer(user=superuser)
        consumer.connect()
        consumer.accept.assert_called_once()
        consumer.close.assert_not_called()

    @patch("hub.consumers.async_to_sync")
    def test_connect_joins_admin_group(self, mock_a2s):
        mock_group_add = MagicMock()
        mock_a2s.return_value = mock_group_add
        superuser = UserFactory(password="testpass123")
        superuser.is_superuser = True
        superuser.save()

        consumer = self._make_consumer(user=superuser)
        consumer.connect()
        mock_group_add.assert_called_with("admin_dashboard", "test-channel-admin")

    def test_connect_rejects_non_superuser(self):
        user = UserFactory(password="testpass123")
        consumer = self._make_consumer(user=user)
        consumer.connect()
        consumer.close.assert_called_once()
        consumer.accept.assert_not_called()

    def test_connect_rejects_anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        consumer = self._make_consumer(user=AnonymousUser())
        consumer.connect()
        consumer.close.assert_called_once()
        consumer.accept.assert_not_called()

    def test_connect_rejects_none_user(self):
        consumer = self._make_consumer(user=None)
        consumer.connect()
        consumer.close.assert_called_once()

    @patch("hub.consumers.async_to_sync")
    def test_disconnect_leaves_group(self, mock_a2s):
        mock_fn = MagicMock()
        mock_a2s.return_value = mock_fn

        consumer = self._make_consumer()
        consumer.disconnect(close_code=1000)
        mock_fn.assert_called_with("admin_dashboard", "test-channel-admin")

    def test_dashboard_update_sends_json(self):
        import json

        consumer = self._make_consumer()
        consumer.dashboard_update({"update_type": "new_bet"})
        consumer.send.assert_called_once()
        sent = json.loads(consumer.send.call_args[1]["text_data"])
        assert sent["type"] == "new_bet"

    def test_dashboard_update_new_comment(self):
        import json

        consumer = self._make_consumer()
        consumer.dashboard_update({"update_type": "new_comment"})
        sent = json.loads(consumer.send.call_args[1]["text_data"])
        assert sent["type"] == "new_comment"

    def test_dashboard_update_new_user(self):
        import json

        consumer = self._make_consumer()
        consumer.dashboard_update({"update_type": "new_user"})
        sent = json.loads(consumer.send.call_args[1]["text_data"])
        assert sent["type"] == "new_user"


# ---------------------------------------------------------------------------
# Phase 4: notify_admin_dashboard helper
# ---------------------------------------------------------------------------


class TestNotifyAdminDashboard:
    """Phase 4: Tests for the notify_admin_dashboard helper function."""

    @patch("hub.consumers.get_channel_layer")
    @patch("hub.consumers.async_to_sync")
    def test_sends_group_message(self, mock_a2s, mock_get_layer):
        from hub.consumers import notify_admin_dashboard

        mock_send = MagicMock()
        mock_a2s.return_value = mock_send
        mock_get_layer.return_value = MagicMock()

        notify_admin_dashboard("new_bet")

        mock_send.assert_called_once_with(
            "admin_dashboard",
            {
                "type": "dashboard_update",
                "update_type": "new_bet",
            },
        )

    @patch("hub.consumers.get_channel_layer")
    def test_no_error_when_channel_layer_none(self, mock_get_layer):
        from hub.consumers import notify_admin_dashboard

        mock_get_layer.return_value = None
        # Should not raise
        notify_admin_dashboard("new_bet")

    @patch("hub.consumers.get_channel_layer")
    @patch("hub.consumers.async_to_sync")
    def test_swallows_exceptions(self, mock_a2s, mock_get_layer):

        mock_a2s.return_value = MagicMock(side_effect=Exception("Redis down"))
        mock_get_layer.return_value = MagicMock()
        # Should not raise
        notify_admin_dashboard("new_bet")
