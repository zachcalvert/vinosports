"""Tests for betting/views.py (PlaceBetView, MyBetsView, BailoutView, parlay views)."""

from decimal import Decimal

import pytest
from betting.context_processors import PARLAY_SESSION_KEY
from betting.models import BetSlip, Parlay
from django.test import Client
from games.models import GameStatus

from tests.factories import (
    BetSlipFactory,
    GameFactory,
    UserBalanceFactory,
    UserFactory,
)


@pytest.fixture
def user_with_balance(db):
    user = UserFactory()
    UserBalanceFactory(user=user, balance=Decimal("1000.00"))
    return user


@pytest.fixture
def auth_client(user_with_balance):
    c = Client()
    c.force_login(user_with_balance)
    return c, user_with_balance


@pytest.mark.django_db
class TestPlaceBetView:
    def test_unauthenticated_redirected(self):
        c = Client()
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.post(
            f"/odds/place/{game.id_hash}/",
            {
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "stake": "50.00",
            },
        )
        assert response.status_code in (301, 302)

    def test_valid_bet_creates_betslip(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        count_before = BetSlip.objects.count()
        c.post(
            f"/odds/place/{game.id_hash}/",
            {
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "stake": "50.00",
            },
        )
        assert BetSlip.objects.count() == count_before + 1

    def test_valid_bet_deducts_balance(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        from vinosports.betting.models import UserBalance

        balance_before = UserBalance.objects.get(user=user).balance
        c.post(
            f"/odds/place/{game.id_hash}/",
            {
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "stake": "50.00",
            },
        )
        balance_after = UserBalance.objects.get(user=user).balance
        assert balance_after == balance_before - Decimal("50.00")

    def test_invalid_form_returns_400(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.post(
            f"/odds/place/{game.id_hash}/",
            {"market": "INVALID", "selection": "HOME", "odds": -150, "stake": "50.00"},
        )
        assert response.status_code == 400

    def test_insufficient_balance_returns_400(self, auth_client):
        c, user = auth_client
        from vinosports.betting.models import UserBalance

        UserBalance.objects.filter(user=user).update(balance=Decimal("5.00"))
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.post(
            f"/odds/place/{game.id_hash}/",
            {
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "stake": "50.00",
            },
        )
        assert response.status_code == 400

    def test_game_not_found_returns_404(self, auth_client):
        c, user = auth_client
        response = c.post(
            "/odds/place/nonexistent/",
            {
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "stake": "50.00",
            },
        )
        assert response.status_code == 404

    def test_non_scheduled_game_returns_404(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.FINAL)
        response = c.post(
            f"/odds/place/{game.id_hash}/",
            {
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "stake": "50.00",
            },
        )
        assert response.status_code == 404

    def test_valid_bet_redirects(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.post(
            f"/odds/place/{game.id_hash}/",
            {
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "stake": "50.00",
            },
        )
        assert response.status_code in (301, 302)


@pytest.mark.django_db
class TestMyBetsView:
    def test_unauthenticated_redirected(self):
        c = Client()
        response = c.get("/odds/my-bets/")
        assert response.status_code in (301, 302)

    def test_renders_my_bets_template(self, auth_client):
        c, user = auth_client
        response = c.get("/odds/my-bets/")
        assert response.status_code == 200
        assert "betting/my_bets.html" in [t.name for t in response.templates]

    def test_default_tab_is_pending(self, auth_client):
        c, user = auth_client
        response = c.get("/odds/my-bets/")
        assert response.context["tab"] == "pending"

    def test_pending_tab_shows_pending_bets(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        BetSlipFactory(user=user, game=game, status="PENDING")
        BetSlipFactory(user=user, game=game, status="WON")
        response = c.get("/odds/my-bets/?tab=pending")
        bets = list(response.context["bets"])
        assert all(b.status == "PENDING" for b in bets)

    def test_won_tab_shows_won_bets(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        BetSlipFactory(user=user, game=game, status="WON")
        BetSlipFactory(user=user, game=game, status="PENDING")
        response = c.get("/odds/my-bets/?tab=won")
        bets = list(response.context["bets"])
        assert all(b.status == "WON" for b in bets)

    def test_lost_tab_shows_lost_bets(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        BetSlipFactory(user=user, game=game, status="LOST")
        response = c.get("/odds/my-bets/?tab=lost")
        bets = list(response.context["bets"])
        assert all(b.status == "LOST" for b in bets)

    def test_unknown_tab_shows_all_bets(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        BetSlipFactory(user=user, game=game, status="WON")
        BetSlipFactory(user=user, game=game, status="LOST")
        response = c.get("/odds/my-bets/?tab=all")
        bets = list(response.context["bets"])
        assert len(bets) == 2

    def test_context_has_parlays(self, auth_client):
        c, user = auth_client
        response = c.get("/odds/my-bets/")
        assert "parlays" in response.context


@pytest.mark.django_db
class TestBailoutView:
    def test_unauthenticated_redirected(self):
        c = Client()
        response = c.post("/odds/bailout/")
        assert response.status_code in (301, 302)

    def test_eligible_user_gets_bailout(self, db):
        from vinosports.betting.models import Bankruptcy

        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("0.10"))
        # grant_bailout requires a Bankruptcy record to link to
        Bankruptcy.objects.create(user=user, balance_at_bankruptcy=Decimal("0.10"))
        c = Client()
        c.force_login(user)
        response = c.post("/odds/bailout/")
        assert response.status_code in (301, 302)

    def test_ineligible_user_returns_400(self, auth_client):
        c, user = auth_client
        # User has $1000 — not eligible for bailout
        response = c.post("/odds/bailout/")
        assert response.status_code == 400


@pytest.mark.django_db
class TestAddToParlayView:
    def test_unauthenticated_redirected(self):
        c = Client()
        game = GameFactory()
        response = c.post(
            "/odds/parlay/add/",
            {
                "game_id": game.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
            },
        )
        assert response.status_code in (301, 302)

    def test_adds_leg_to_session(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        c.post(
            "/odds/parlay/add/",
            {
                "game_id": game.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
            },
        )
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert len(slip) == 1
        assert slip[0]["game_id"] == game.pk

    def test_duplicate_game_returns_400(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        c.post(
            "/odds/parlay/add/",
            {
                "game_id": game.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
            },
        )
        response = c.post(
            "/odds/parlay/add/",
            {
                "game_id": game.pk,
                "market": "MONEYLINE",
                "selection": "AWAY",
                "odds": 130,
            },
        )
        assert response.status_code == 400

    def test_max_legs_returns_400(self, auth_client):
        from vinosports.betting.constants import PARLAY_MAX_LEGS

        c, user = auth_client
        # Fill parlay to max
        slip = [
            {
                "game_id": i,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "line": None,
            }
            for i in range(1, PARLAY_MAX_LEGS + 1)
        ]
        session = c.session
        session[PARLAY_SESSION_KEY] = slip
        session.save()
        game = GameFactory()
        response = c.post(
            "/odds/parlay/add/",
            {
                "game_id": game.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
            },
        )
        assert response.status_code == 400

    def test_redirects_without_htmx(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        response = c.post(
            "/odds/parlay/add/",
            {
                "game_id": game.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
            },
        )
        assert response.status_code in (301, 302)


@pytest.mark.django_db
class TestRemoveFromParlayView:
    def test_unauthenticated_redirected(self):
        c = Client()
        response = c.post("/odds/parlay/remove/", {"game_id": 1})
        assert response.status_code in (301, 302)

    def test_removes_leg_from_session(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {
                "game_id": game.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "line": None,
            }
        ]
        session.save()
        c.post("/odds/parlay/remove/", {"game_id": game.pk})
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert len(slip) == 0

    def test_remove_nonexistent_game_is_noop(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {
                "game_id": game.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "line": None,
            }
        ]
        session.save()
        c.post("/odds/parlay/remove/", {"game_id": 999999})
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert len(slip) == 1


@pytest.mark.django_db
class TestClearParlayView:
    def test_unauthenticated_redirected(self):
        c = Client()
        response = c.post("/odds/parlay/clear/")
        assert response.status_code in (301, 302)

    def test_clears_session_slip(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {
                "game_id": game.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "line": None,
            }
        ]
        session.save()
        c.post("/odds/parlay/clear/")
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert len(slip) == 0

    def test_clear_empty_slip_is_noop(self, auth_client):
        c, user = auth_client
        c.post("/odds/parlay/clear/")
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert slip == []


@pytest.mark.django_db
class TestPlaceParlayView:
    def test_unauthenticated_redirected(self):
        c = Client()
        response = c.post("/odds/parlay/place/", {"stake": "30.00"})
        assert response.status_code in (301, 302)

    def test_invalid_stake_returns_400(self, auth_client):
        c, user = auth_client
        game1 = GameFactory(status=GameStatus.SCHEDULED)
        game2 = GameFactory(status=GameStatus.SCHEDULED)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {
                "game_id": game1.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "line": None,
            },
            {
                "game_id": game2.pk,
                "market": "MONEYLINE",
                "selection": "AWAY",
                "odds": 130,
                "line": None,
            },
        ]
        session.save()
        response = c.post("/odds/parlay/place/", {"stake": "0.01"})
        assert response.status_code == 400

    def test_too_few_legs_returns_400(self, auth_client):
        c, user = auth_client
        session = c.session
        session[PARLAY_SESSION_KEY] = []
        session.save()
        response = c.post("/odds/parlay/place/", {"stake": "30.00"})
        assert response.status_code == 400

    def test_valid_parlay_creates_record(self, auth_client):
        c, user = auth_client
        game1 = GameFactory(status=GameStatus.SCHEDULED)
        game2 = GameFactory(status=GameStatus.SCHEDULED)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {
                "game_id": game1.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "line": None,
            },
            {
                "game_id": game2.pk,
                "market": "MONEYLINE",
                "selection": "AWAY",
                "odds": 130,
                "line": None,
            },
        ]
        session.save()
        count_before = Parlay.objects.count()
        c.post("/odds/parlay/place/", {"stake": "30.00"})
        assert Parlay.objects.count() == count_before + 1

    def test_valid_parlay_deducts_balance(self, auth_client):
        c, user = auth_client
        game1 = GameFactory(status=GameStatus.SCHEDULED)
        game2 = GameFactory(status=GameStatus.SCHEDULED)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {
                "game_id": game1.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "line": None,
            },
            {
                "game_id": game2.pk,
                "market": "MONEYLINE",
                "selection": "AWAY",
                "odds": 130,
                "line": None,
            },
        ]
        session.save()
        from vinosports.betting.models import UserBalance

        balance_before = UserBalance.objects.get(user=user).balance
        c.post("/odds/parlay/place/", {"stake": "30.00"})
        balance_after = UserBalance.objects.get(user=user).balance
        assert balance_after == balance_before - Decimal("30.00")

    def test_valid_parlay_clears_session(self, auth_client):
        c, user = auth_client
        game1 = GameFactory(status=GameStatus.SCHEDULED)
        game2 = GameFactory(status=GameStatus.SCHEDULED)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {
                "game_id": game1.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "line": None,
            },
            {
                "game_id": game2.pk,
                "market": "MONEYLINE",
                "selection": "AWAY",
                "odds": 130,
                "line": None,
            },
        ]
        session.save()
        c.post("/odds/parlay/place/", {"stake": "30.00"})
        slip = c.session.get(PARLAY_SESSION_KEY, [])
        assert slip == []

    def test_insufficient_balance_returns_400(self, auth_client):
        c, user = auth_client
        from vinosports.betting.models import UserBalance

        UserBalance.objects.filter(user=user).update(balance=Decimal("5.00"))
        game1 = GameFactory(status=GameStatus.SCHEDULED)
        game2 = GameFactory(status=GameStatus.SCHEDULED)
        session = c.session
        session[PARLAY_SESSION_KEY] = [
            {
                "game_id": game1.pk,
                "market": "MONEYLINE",
                "selection": "HOME",
                "odds": -150,
                "line": None,
            },
            {
                "game_id": game2.pk,
                "market": "MONEYLINE",
                "selection": "AWAY",
                "odds": 130,
                "line": None,
            },
        ]
        session.save()
        response = c.post("/odds/parlay/place/", {"stake": "30.00"})
        assert response.status_code == 400
