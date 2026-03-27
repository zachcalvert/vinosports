"""Tests for betting/context_processors.py (bankruptcy, parlay_slip)."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from nba.betting.context_processors import bankruptcy, parlay_slip
from nba.tests.factories import (
    BetSlipFactory,
    GameFactory,
    UserBalanceFactory,
    UserFactory,
)
from vinosports.betting.models import Bankruptcy


@pytest.mark.django_db
class TestBankruptcyContextProcessor:
    def test_unauthenticated_returns_empty(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = AnonymousUser()
        request.league = "nba"
        result = bankruptcy(request)
        assert result == {}

    def test_user_without_balance_returns_empty(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = UserFactory()
        request.league = "nba"
        result = bankruptcy(request)
        assert result == {}

    def test_user_with_sufficient_balance_returns_empty(self):
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("100.00"))
        request.user = user
        request.league = "nba"
        result = bankruptcy(request)
        assert result == {}

    def test_bankrupt_user_returns_context(self):
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("0.10"))
        request.user = user
        request.league = "nba"
        result = bankruptcy(request)
        assert result.get("is_bankrupt") is True
        assert "bankrupt_balance" in result
        assert "bankruptcy_count" in result

    def test_bankrupt_user_with_pending_bets_returns_empty(self):
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("0.10"))
        game = GameFactory()
        BetSlipFactory(user=user, game=game, stake=Decimal("0.10"))
        request.user = user
        request.league = "nba"
        result = bankruptcy(request)
        assert result == {}

    def test_bankruptcy_count_increments(self):
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("0.10"))
        Bankruptcy.objects.create(user=user, balance_at_bankruptcy=Decimal("0.10"))
        Bankruptcy.objects.create(user=user, balance_at_bankruptcy=Decimal("0.05"))
        request.user = user
        request.league = "nba"
        result = bankruptcy(request)
        assert result["bankruptcy_count"] == 2


@pytest.mark.django_db
class TestParlaySlipContextProcessor:
    def test_unauthenticated_returns_defaults(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.user = AnonymousUser()
        request.league = "nba"
        request.session = {}
        result = parlay_slip(request)
        assert result["parlay_leg_count"] == 0
        assert result["parlay_legs"] == []
        assert result["parlay_combined_odds"] is None
        assert "parlay_min_legs" in result
        assert "parlay_max_legs" in result
        assert "parlay_form" in result

    def test_authenticated_no_session_returns_empty_slip(self):
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory()
        request.user = user
        request.league = "nba"
        request.session = {}
        result = parlay_slip(request)
        assert result["parlay_leg_count"] == 0
        assert result["parlay_legs"] == []
        assert result["parlay_combined_odds"] is None

    def test_authenticated_with_session_legs(self):
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory()
        game = GameFactory()
        request.user = user
        request.league = "nba"
        request.session = {
            "parlay_slip": [
                {
                    "game_id": game.pk,
                    "market": "MONEYLINE",
                    "selection": "HOME",
                    "odds": -150,
                    "line": None,
                }
            ]
        }
        result = parlay_slip(request)
        assert result["parlay_leg_count"] == 1
        assert len(result["parlay_legs"]) == 1
        assert result["parlay_combined_odds"] is not None

    def test_combined_odds_calculated_for_multiple_legs(self):
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory()
        g1 = GameFactory()
        g2 = GameFactory()
        request.user = user
        request.league = "nba"
        request.session = {
            "parlay_slip": [
                {
                    "game_id": g1.pk,
                    "market": "MONEYLINE",
                    "selection": "HOME",
                    "odds": -150,
                    "line": None,
                },
                {
                    "game_id": g2.pk,
                    "market": "MONEYLINE",
                    "selection": "AWAY",
                    "odds": 130,
                    "line": None,
                },
            ]
        }
        result = parlay_slip(request)
        assert result["parlay_leg_count"] == 2
        assert result["parlay_combined_odds"] is not None
        assert result["parlay_combined_odds"] > Decimal("1.00")

    def test_legs_needed_calculated_correctly(self):
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory()
        request.user = user
        request.league = "nba"
        request.session = {}
        result = parlay_slip(request)
        min_legs = result["parlay_min_legs"]
        assert result["parlay_legs_needed"] == min_legs

    def test_invalid_game_id_skipped(self):
        factory = RequestFactory()
        request = factory.get("/")
        user = UserFactory()
        request.user = user
        request.league = "nba"
        request.session = {
            "parlay_slip": [
                {
                    "game_id": 999999,
                    "market": "MONEYLINE",
                    "selection": "HOME",
                    "odds": -150,
                    "line": None,
                }
            ]
        }
        result = parlay_slip(request)
        assert result["parlay_leg_count"] == 0
        assert result["parlay_legs"] == []


@pytest.mark.django_db
class TestActivityToastsContextProcessor:
    def test_non_nba_league_returns_empty(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.league = "epl"
        request.user = AnonymousUser()

        from nba.activity.context_processors import activity_toasts

        result = activity_toasts(request)
        assert result == {}

    def test_anonymous_user_returns_toasts_true(self):
        factory = RequestFactory()
        request = factory.get("/")
        request.league = "nba"
        request.user = AnonymousUser()

        from nba.activity.context_processors import activity_toasts

        result = activity_toasts(request)
        assert result == {"show_activity_toasts": True}

    def test_authenticated_user_returns_user_preference(self):
        from nba.activity.context_processors import activity_toasts

        factory = RequestFactory()
        request = factory.get("/")
        request.league = "nba"
        user = UserFactory(show_activity_toasts=False)
        request.user = user
        result = activity_toasts(request)
        assert result == {"show_activity_toasts": False}


@pytest.mark.django_db
class TestUnseenRewardsContextProcessor:
    def test_non_nba_league_returns_empty_list(self):
        from nba.rewards.context_processors import unseen_rewards

        factory = RequestFactory()
        request = factory.get("/")
        request.league = "epl"
        request.user = AnonymousUser()
        result = unseen_rewards(request)
        assert result == {"unseen_rewards": []}

    def test_unauthenticated_returns_empty_list(self):
        from nba.rewards.context_processors import unseen_rewards

        factory = RequestFactory()
        request = factory.get("/")
        request.league = "nba"
        request.user = AnonymousUser()
        result = unseen_rewards(request)
        assert result == {"unseen_rewards": []}


class TestThemeContextProcessor:
    def test_non_nba_league_returns_empty(self):
        from nba.website.context_processors import theme

        factory = RequestFactory()
        request = factory.get("/")
        request.league = "hub"
        result = theme(request)
        assert result == {}


class TestNormalizeTheme:
    def test_invalid_theme_falls_back_to_default(self):
        from nba.website.theme import normalize_theme

        assert normalize_theme("invalid") == "light"

    def test_valid_dark_theme(self):
        from nba.website.theme import normalize_theme

        assert normalize_theme("dark") == "dark"


class TestGetToggleTheme:
    def test_toggle_from_dark_returns_light(self):
        from unittest.mock import MagicMock

        from nba.website.theme import get_toggle_theme

        request = MagicMock()
        request.session = {"theme_preference": "dark"}
        result = get_toggle_theme(request)
        assert result == "light"

    def test_toggle_from_light_returns_dark(self):
        from unittest.mock import MagicMock

        from nba.website.theme import get_toggle_theme

        request = MagicMock()
        request.session = {"theme_preference": "light"}
        result = get_toggle_theme(request)
        assert result == "dark"
