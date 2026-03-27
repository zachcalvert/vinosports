"""Tests for epl/betting/views.py — odds board, bet placement, parlays, my bets, bailout."""

from decimal import Decimal

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from epl.betting.models import BetSlip, Parlay
from epl.matches.models import Match
from vinosports.betting.models import (
    BalanceTransaction,
    BetStatus,
    UserBalance,
)

from .factories import (
    BetSlipFactory,
    MatchFactory,
    OddsFactory,
    ParlayFactory,
    ParlayLegFactory,
    UserBalanceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

PARLAY_SESSION_KEY = "parlay_slip"


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
        resp = client.get(reverse("epl_betting:odds"))
        assert resp.status_code == 200

    def test_context_has_matches(self, client):
        resp = client.get(reverse("epl_betting:odds"))
        assert "matches" in resp.context

    def test_only_matches_with_odds_shown(self, client):
        match_with_odds = MatchFactory(season=settings.EPL_CURRENT_SEASON)
        OddsFactory(match=match_with_odds)
        MatchFactory(season=settings.EPL_CURRENT_SEASON)  # no odds
        resp = client.get(reverse("epl_betting:odds"))
        matches = resp.context["matches"]
        assert len(matches) == 1
        assert matches[0].pk == match_with_odds.pk

    def test_context_has_last_odds_refresh(self, client):
        match = MatchFactory(season=settings.EPL_CURRENT_SEASON)
        OddsFactory(match=match)
        resp = client.get(reverse("epl_betting:odds"))
        assert resp.context["last_odds_refresh"] is not None

    def test_best_odds_aggregated(self, client):
        match = MatchFactory(season=settings.EPL_CURRENT_SEASON)
        OddsFactory(
            match=match,
            bookmaker="BookA",
            home_win=Decimal("2.50"),
            draw=Decimal("3.40"),
            away_win=Decimal("3.20"),
        )
        OddsFactory(
            match=match,
            bookmaker="BookB",
            home_win=Decimal("2.10"),
            draw=Decimal("3.60"),
            away_win=Decimal("2.90"),
        )
        resp = client.get(reverse("epl_betting:odds"))
        m = resp.context["matches"][0]
        assert m.best_home_odds == Decimal("2.10")  # min
        assert m.best_draw_odds == Decimal("3.40")  # min
        assert m.best_away_odds == Decimal("2.90")  # min


class TestOddsBoardPartialView:
    def test_renders(self, client):
        resp = client.get(reverse("epl_betting:odds_partial"))
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PlaceBetView
# ---------------------------------------------------------------------------


class TestPlaceBetView:
    def test_unauthenticated_redirected(self, client):
        match = MatchFactory()
        resp = client.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 302

    def test_valid_bet_creates_betslip(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        count_before = BetSlip.objects.count()
        c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert BetSlip.objects.count() == count_before + 1

    def test_valid_bet_deducts_balance(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        balance_before = UserBalance.objects.get(user=user).balance
        c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        balance_after = UserBalance.objects.get(user=user).balance
        assert balance_after == balance_before - Decimal("50.00")

    def test_valid_bet_creates_transaction(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        txn = BalanceTransaction.objects.filter(
            user=user, transaction_type=BalanceTransaction.Type.BET_PLACEMENT
        ).first()
        assert txn is not None
        assert txn.amount == Decimal("-50.00")

    def test_insufficient_balance(self, auth_client):
        c, user = auth_client
        UserBalance.objects.filter(user=user).update(balance=Decimal("5.00"))
        match = MatchFactory()
        OddsFactory(match=match)
        resp = c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 200
        assert "Insufficient balance" in resp.content.decode()

    def test_no_odds_available(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        # No odds created
        resp = c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 200
        assert "No odds available" in resp.content.decode()

    def test_match_not_scheduled(self, auth_client):
        c, user = auth_client
        match = MatchFactory(status=Match.Status.FINISHED)
        OddsFactory(match=match)
        resp = c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 200
        assert "no longer accepting bets" in resp.content.decode()

    def test_invalid_form(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        resp = c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "INVALID", "stake": "50.00"},
        )
        assert resp.status_code == 200

    def test_match_not_found(self, auth_client):
        c, user = auth_client
        resp = c.post(
            reverse("epl_betting:place_bet", args=["nonexistent-match"]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert resp.status_code == 404

    def test_bet_confirmation_context(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match, home_win=Decimal("2.10"))
        resp = c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00"},
        )
        assert "bet" in resp.context
        assert "potential_payout" in resp.context

    def test_draw_selection(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match, draw=Decimal("3.40"))
        c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
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
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "AWAY_WIN", "stake": "25.00"},
        )
        bet = BetSlip.objects.filter(user=user).first()
        assert bet is not None
        assert bet.selection == BetSlip.Selection.AWAY_WIN

    def test_container_id_uses_quick_bet_template(self, auth_client):
        c, user = auth_client
        match = MatchFactory(status=Match.Status.FINISHED)
        OddsFactory(match=match)
        resp = c.post(
            reverse("epl_betting:place_bet", args=[match.slug]),
            {"selection": "HOME_WIN", "stake": "50.00", "container_id": "qb-1"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# MyBetsView (EPL)
# ---------------------------------------------------------------------------


class TestMyBetsView:
    def test_requires_login(self, client):
        resp = client.get(reverse("epl_betting:my_bets"))
        assert resp.status_code == 302

    def test_renders(self, auth_client):
        c, user = auth_client
        resp = c.get(reverse("epl_betting:my_bets"))
        assert resp.status_code == 200

    def test_context_has_totals(self, auth_client):
        c, user = auth_client
        resp = c.get(reverse("epl_betting:my_bets"))
        assert "total_staked" in resp.context
        assert "total_payout" in resp.context
        assert "net_pnl" in resp.context
        assert "current_balance" in resp.context

    def test_shows_user_bets(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        BetSlipFactory(user=user, match=match, stake=Decimal("50.00"))
        resp = c.get(reverse("epl_betting:my_bets"))
        assert resp.context["total_staked"] == Decimal("50.00")

    def test_shows_user_parlays(self, auth_client):
        c, user = auth_client
        parlay = ParlayFactory(user=user, stake=Decimal("30.00"))
        match = MatchFactory()
        ParlayLegFactory(parlay=parlay, match=match)
        resp = c.get(reverse("epl_betting:my_bets"))
        activity = resp.context["activity"]
        assert any(a["type"] == "parlay" for a in activity)

    def test_default_balance_when_no_balance(self, auth_client):
        c, user = auth_client
        UserBalance.objects.filter(user=user).delete()
        resp = c.get(reverse("epl_betting:my_bets"))
        assert resp.context["current_balance"] == Decimal("1000.00")

    def test_activity_sorted_by_date(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory()
        BetSlipFactory(user=user, match=match1)
        BetSlipFactory(user=user, match=match2)
        resp = c.get(reverse("epl_betting:my_bets"))
        activity = resp.context["activity"]
        dates = [a["date"] for a in activity]
        assert dates == sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# QuickBetFormView
# ---------------------------------------------------------------------------


class TestQuickBetFormView:
    def test_requires_login(self, client):
        match = MatchFactory()
        resp = client.get(reverse("epl_betting:quick_bet_form", args=[match.slug]))
        assert resp.status_code == 302

    def test_renders_form(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        resp = c.get(
            reverse("epl_betting:quick_bet_form", args=[match.slug])
            + "?selection=HOME_WIN&container=qb-1"
        )
        assert resp.status_code == 200
        assert "form" in resp.context
        assert resp.context["selection"] == "HOME_WIN"

    def test_selected_odds_in_context(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match, home_win=Decimal("2.10"))
        resp = c.get(
            reverse("epl_betting:quick_bet_form", args=[match.slug])
            + "?selection=HOME_WIN&container=qb-1"
        )
        assert resp.context["selected_odds"] == Decimal("2.10")

    def test_no_selection_no_odds(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        OddsFactory(match=match)
        resp = c.get(reverse("epl_betting:quick_bet_form", args=[match.slug]))
        assert resp.status_code == 200
        assert resp.context["selected_odds"] is None

    def test_match_not_found(self, auth_client):
        c, user = auth_client
        resp = c.get(reverse("epl_betting:quick_bet_form", args=["nonexistent-match"]))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# BailoutView
# ---------------------------------------------------------------------------


class TestBailoutView:
    def test_requires_login(self, client):
        resp = client.post(reverse("epl_betting:bailout"))
        assert resp.status_code == 302

    def test_not_bankrupt(self, auth_client):
        c, user = auth_client
        resp = c.post(reverse("epl_betting:bailout"))
        assert resp.status_code == 400
        data = resp.json()
        assert "not bankrupt" in data["error"].lower()

    def test_eligible_for_bailout(self):
        user = UserFactory(password="testpass123")
        UserBalanceFactory(user=user, balance=Decimal("0.00"))
        c = Client()
        c.login(email=user.email, password="testpass123")

        resp = c.post(reverse("epl_betting:bailout"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert int(data["amount"]) >= 1000

    def test_bailout_credits_balance(self):
        user = UserFactory(password="testpass123")
        UserBalanceFactory(user=user, balance=Decimal("0.00"))
        c = Client()
        c.login(email=user.email, password="testpass123")

        c.post(reverse("epl_betting:bailout"))
        bal = UserBalance.objects.get(user=user)
        assert bal.balance > Decimal("0")

    def test_pending_bets_block_bailout(self, auth_client):
        c, user = auth_client
        UserBalance.objects.filter(user=user).update(balance=Decimal("0.00"))
        match = MatchFactory()
        BetSlipFactory(user=user, match=match, status=BetStatus.PENDING)

        resp = c.post(reverse("epl_betting:bailout"))
        assert resp.status_code == 400

    def test_no_balance_returns_error(self):
        user = UserFactory(password="testpass123")
        c = Client()
        c.login(email=user.email, password="testpass123")
        resp = c.post(reverse("epl_betting:bailout"))
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Parlay views — add, remove, clear, place
# ---------------------------------------------------------------------------


class TestAddToParlayView:
    def test_requires_login(self, client):
        resp = client.post(
            reverse("epl_betting:parlay_add"),
            {"match_id": 1, "selection": "HOME_WIN"},
        )
        assert resp.status_code == 302

    def test_adds_leg_to_slip(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        c.post(
            reverse("epl_betting:parlay_add"),
            {"match_id": match.pk, "selection": "HOME_WIN"},
        )
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert len(slip) == 1
        assert slip[0]["match_id"] == match.pk

    def test_invalid_selection(self, auth_client):
        c, user = auth_client
        resp = c.post(
            reverse("epl_betting:parlay_add"),
            {"match_id": 1, "selection": "INVALID"},
        )
        assert resp.status_code == 200
        assert "parlay_error" in resp.context

    def test_duplicate_match_rejected(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        c.post(
            reverse("epl_betting:parlay_add"),
            {"match_id": match.pk, "selection": "HOME_WIN"},
        )
        resp = c.post(
            reverse("epl_betting:parlay_add"),
            {"match_id": match.pk, "selection": "DRAW"},
        )
        assert "parlay_error" in resp.context

    def test_max_legs_enforced(self, auth_client):
        from vinosports.betting.constants import PARLAY_MAX_LEGS

        c, user = auth_client
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": i, "selection": "HOME_WIN"}
            for i in range(1, PARLAY_MAX_LEGS + 1)
        ]
        session.save()
        match = MatchFactory()
        resp = c.post(
            reverse("epl_betting:parlay_add"),
            {"match_id": match.pk, "selection": "HOME_WIN"},
        )
        assert "parlay_error" in resp.context

    def test_non_bettable_match_rejected(self, auth_client):
        c, user = auth_client
        match = MatchFactory(status=Match.Status.FINISHED)
        resp = c.post(
            reverse("epl_betting:parlay_add"),
            {"match_id": match.pk, "selection": "HOME_WIN"},
        )
        assert "parlay_error" in resp.context

    def test_invalid_match_id(self, auth_client):
        c, user = auth_client
        resp = c.post(
            reverse("epl_betting:parlay_add"),
            {"match_id": "abc", "selection": "HOME_WIN"},
        )
        assert "parlay_error" in resp.context


class TestRemoveFromParlayView:
    def test_requires_login(self, client):
        resp = client.post(reverse("epl_betting:parlay_remove"), {"match_id": 1})
        assert resp.status_code == 302

    def test_removes_leg(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        session = c.session
        session[PARLAY_SESSION_KEY] = [{"match_id": match.pk, "selection": "HOME_WIN"}]
        session.save()
        c.post(reverse("epl_betting:parlay_remove"), {"match_id": match.pk})
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert len(slip) == 0

    def test_remove_nonexistent_is_noop(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        session = c.session
        session[PARLAY_SESSION_KEY] = [{"match_id": match.pk, "selection": "HOME_WIN"}]
        session.save()
        c.post(reverse("epl_betting:parlay_remove"), {"match_id": 999999})
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert len(slip) == 1


class TestClearParlayView:
    def test_requires_login(self, client):
        resp = client.post(reverse("epl_betting:parlay_clear"))
        assert resp.status_code == 302

    def test_clears_slip(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        session = c.session
        session[PARLAY_SESSION_KEY] = [{"match_id": match.pk, "selection": "HOME_WIN"}]
        session.save()
        c.post(reverse("epl_betting:parlay_clear"))
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert len(slip) == 0

    def test_clear_empty_is_noop(self, auth_client):
        c, user = auth_client
        c.post(reverse("epl_betting:parlay_clear"))
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert slip == []


class TestParlaySlipPartialView:
    def test_requires_login(self, client):
        resp = client.get(reverse("epl_betting:parlay_slip"))
        assert resp.status_code == 302

    def test_renders_empty_slip(self, auth_client):
        c, user = auth_client
        resp = c.get(reverse("epl_betting:parlay_slip"))
        assert resp.status_code == 200


class TestPlaceParlayView:
    def test_requires_login(self, client):
        resp = client.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        assert resp.status_code == 302

    def test_too_few_legs(self, auth_client):
        c, user = auth_client
        session = c.session
        session[PARLAY_SESSION_KEY] = []
        session.save()
        resp = c.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        assert resp.status_code == 200
        assert "parlay_error" in resp.context

    def test_valid_parlay_creates_record(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory()
        OddsFactory(match=match1)
        OddsFactory(match=match2)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": match1.pk, "selection": "HOME_WIN"},
            {"match_id": match2.pk, "selection": "AWAY_WIN"},
        ]
        session.save()
        count_before = Parlay.objects.count()
        c.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        assert Parlay.objects.count() == count_before + 1

    def test_valid_parlay_deducts_balance(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory()
        OddsFactory(match=match1)
        OddsFactory(match=match2)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": match1.pk, "selection": "HOME_WIN"},
            {"match_id": match2.pk, "selection": "AWAY_WIN"},
        ]
        session.save()
        balance_before = UserBalance.objects.get(user=user).balance
        c.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        balance_after = UserBalance.objects.get(user=user).balance
        assert balance_after == balance_before - Decimal("30.00")

    def test_valid_parlay_clears_session(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory()
        OddsFactory(match=match1)
        OddsFactory(match=match2)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": match1.pk, "selection": "HOME_WIN"},
            {"match_id": match2.pk, "selection": "AWAY_WIN"},
        ]
        session.save()
        c.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert slip == []

    def test_insufficient_balance(self, auth_client):
        c, user = auth_client
        UserBalance.objects.filter(user=user).update(balance=Decimal("5.00"))
        match1 = MatchFactory()
        match2 = MatchFactory()
        OddsFactory(match=match1)
        OddsFactory(match=match2)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": match1.pk, "selection": "HOME_WIN"},
            {"match_id": match2.pk, "selection": "AWAY_WIN"},
        ]
        session.save()
        resp = c.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        assert resp.status_code == 200
        assert "parlay_error" in resp.context

    def test_invalid_stake(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory()
        OddsFactory(match=match1)
        OddsFactory(match=match2)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": match1.pk, "selection": "HOME_WIN"},
            {"match_id": match2.pk, "selection": "AWAY_WIN"},
        ]
        session.save()
        resp = c.post(reverse("epl_betting:parlay_place"), {"stake": "0.01"})
        assert resp.status_code == 200
        assert "parlay_error" in resp.context

    def test_match_no_longer_bettable(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory(status=Match.Status.FINISHED)
        OddsFactory(match=match1)
        OddsFactory(match=match2)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": match1.pk, "selection": "HOME_WIN"},
            {"match_id": match2.pk, "selection": "AWAY_WIN"},
        ]
        session.save()
        resp = c.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        assert resp.status_code == 200
        assert "parlay_error" in resp.context

    def test_match_no_odds(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory()
        OddsFactory(match=match1)
        # match2 has no odds
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": match1.pk, "selection": "HOME_WIN"},
            {"match_id": match2.pk, "selection": "AWAY_WIN"},
        ]
        session.save()
        resp = c.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        assert resp.status_code == 200
        assert "parlay_error" in resp.context

    def test_creates_parlay_legs(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory()
        OddsFactory(match=match1)
        OddsFactory(match=match2)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": match1.pk, "selection": "HOME_WIN"},
            {"match_id": match2.pk, "selection": "DRAW"},
        ]
        session.save()
        c.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        parlay = Parlay.objects.filter(user=user).first()
        assert parlay is not None
        assert parlay.legs.count() == 2

    def test_parlay_confirmation_context(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory()
        OddsFactory(match=match1)
        OddsFactory(match=match2)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {"match_id": match1.pk, "selection": "HOME_WIN"},
            {"match_id": match2.pk, "selection": "AWAY_WIN"},
        ]
        session.save()
        resp = c.post(reverse("epl_betting:parlay_place"), {"stake": "30.00"})
        assert "parlay" in resp.context
        assert "combined_odds" in resp.context
        assert "potential_payout" in resp.context
