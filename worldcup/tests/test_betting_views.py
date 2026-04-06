"""Tests for worldcup/betting/views.py — odds board, bet placement, quick bet form."""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from vinosports.betting.models import BalanceTransaction, UserBalance
from worldcup.betting.models import BetSlip
from worldcup.matches.models import Match

from .factories import (
    MatchFactory,
    OddsFactory,
    UserBalanceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user_with_balance():
    user = UserFactory(password="testpass123")
    UserBalanceFactory(user=user, balance=Decimal("1000.00"))
    return user


@pytest.fixture
def auth_client(user_with_balance):
    c = Client()
    c.login(email=user_with_balance.email, password="testpass123")
    return c, user_with_balance


# ---------------------------------------------------------------------------
# OddsBoardView
# ---------------------------------------------------------------------------


class TestOddsBoardView:
    def test_renders_publicly(self, client):
        resp = client.get(reverse("worldcup_betting:odds_board"))
        assert resp.status_code == 200

    def test_context_has_matches_with_odds(self, client):
        resp = client.get(reverse("worldcup_betting:odds_board"))
        assert "matches_with_odds" in resp.context

    def test_partial_renders(self, client):
        resp = client.get(reverse("worldcup_betting:odds_board_partial"))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PlaceBetView
# ---------------------------------------------------------------------------


class TestPlaceBetView:
    def test_unauthenticated_redirected(self, client):
        match = MatchFactory()
        resp = client.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 302

    def test_valid_bet_creates_betslip(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        count_before = BetSlip.objects.count()
        c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert BetSlip.objects.count() == count_before + 1

    def test_valid_bet_deducts_balance(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        balance_before = UserBalance.objects.get(user=user).balance
        c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        balance_after = UserBalance.objects.get(user=user).balance
        assert balance_after == balance_before - Decimal("50.00")

    def test_valid_bet_creates_transaction(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        txn = BalanceTransaction.objects.filter(
            user=user, transaction_type=BalanceTransaction.Type.BET_PLACEMENT
        ).first()
        assert txn is not None
        assert txn.amount == Decimal("-50.00")

    def test_confirmation_context(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match, home_win=Decimal("2.10"))
        resp = c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 200
        assert "bet" in resp.context
        assert "potential_payout" in resp.context
        assert resp.context["potential_payout"] == Decimal("50.00") * Decimal("2.10")

    def test_draw_selection(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match, draw=Decimal("3.40"))
        c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "DRAW", "stake": "25.00"},
        )
        bet = BetSlip.objects.filter(user=user).first()
        assert bet is not None
        assert bet.selection == BetSlip.Selection.DRAW

    def test_away_win_selection(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match, away_win=Decimal("3.20"))
        c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "AWAY_WIN", "stake": "25.00"},
        )
        bet = BetSlip.objects.filter(user=user).first()
        assert bet is not None
        assert bet.selection == BetSlip.Selection.AWAY_WIN

    def test_insufficient_balance(self, auth_client):
        c, user = auth_client
        UserBalance.objects.filter(user=user).update(balance=Decimal("5.00"))
        match = MatchFactory()
        OddsFactory(match=match)
        resp = c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 200
        assert "Insufficient balance" in resp.content.decode()
        assert BetSlip.objects.filter(user=user).count() == 0

    def test_no_odds_available(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        resp = c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 200
        assert "No odds available" in resp.content.decode()

    def test_match_not_bettable(self, auth_client):
        c, user = auth_client
        match = MatchFactory(status=Match.Status.FINISHED)
        OddsFactory(match=match)
        resp = c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 200
        assert "no longer accepting bets" in resp.content.decode()

    def test_invalid_selection_returns_200(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        resp = c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "INVALID", "stake": "50.00"},
        )
        assert resp.status_code in (200, 422)

    def test_match_not_found(self, auth_client):
        c, user = auth_client
        resp = c.post(
            reverse("worldcup_betting:place_bet", args=["nonexistent-match"]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 404

    def test_container_id_uses_quick_bet_template(self, auth_client):
        """Posting with container_id on a finished match returns quick_bet template."""
        c, user = auth_client
        match = MatchFactory(status=Match.Status.FINISHED)
        OddsFactory(match=match)
        resp = c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {
                "selection": "HOME_WIN",
                "stake": "50.00",
                "container_id": "bet-container",
            },
        )
        assert resp.status_code == 200

    def test_balance_not_deducted_on_insufficient_funds(self, auth_client):
        c, user = auth_client
        UserBalance.objects.filter(user=user).update(balance=Decimal("10.00"))
        match = MatchFactory()
        OddsFactory(match=match)
        c.post(
            reverse("worldcup_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert UserBalance.objects.get(user=user).balance == Decimal("10.00")


# ---------------------------------------------------------------------------
# QuickBetFormView
# ---------------------------------------------------------------------------


class TestQuickBetFormView:
    def test_requires_login(self, client):
        match = MatchFactory()
        resp = client.get(reverse("worldcup_betting:quick_bet_form", args=[match.slug]))
        assert resp.status_code == 302

    def test_renders_form(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        resp = c.get(
            reverse("worldcup_betting:quick_bet_form", args=[match.slug])
            + "?selection=HOME_WIN&container=bet-container"
        )
        assert resp.status_code == 200
        assert "form" in resp.context
        assert resp.context["selection"] == "HOME_WIN"

    def test_selected_odds_in_context(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match, home_win=Decimal("2.10"))
        resp = c.get(
            reverse("worldcup_betting:quick_bet_form", args=[match.slug])
            + "?selection=HOME_WIN&container=bet-container"
        )
        assert resp.context["selected_odds"] == Decimal("2.10")

    def test_draw_odds_in_context(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match, draw=Decimal("3.40"))
        resp = c.get(
            reverse("worldcup_betting:quick_bet_form", args=[match.slug])
            + "?selection=DRAW&container=bet-container"
        )
        assert resp.context["selected_odds"] == Decimal("3.40")

    def test_no_selection_gives_none_odds(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        resp = c.get(reverse("worldcup_betting:quick_bet_form", args=[match.slug]))
        assert resp.status_code == 200
        assert resp.context["selected_odds"] is None

    def test_match_not_found(self, auth_client):
        c, user = auth_client
        resp = c.get(
            reverse("worldcup_betting:quick_bet_form", args=["nonexistent-match"])
        )
        assert resp.status_code == 404

    def test_container_id_passed_to_context(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        resp = c.get(
            reverse("worldcup_betting:quick_bet_form", args=[match.slug])
            + "?selection=AWAY_WIN&container=my-container"
        )
        assert resp.context["container_id"] == "my-container"
