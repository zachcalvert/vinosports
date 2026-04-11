"""Tests for prop bets — creation, placement, settlement, cancellation, and views."""

from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client, RequestFactory
from django.urls import reverse

from hub.tests.factories import UserBalanceFactory, UserFactory
from vinosports.activity.models import Notification
from vinosports.betting.admin import PropBetAdmin
from vinosports.betting.models import (
    BalanceTransaction,
    BetStatus,
    PropBet,
    PropBetSlip,
    PropBetStatus,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user():
    return UserFactory(password="testpass123")


@pytest.fixture
def user_balance(user):
    return UserBalanceFactory(user=user, balance=Decimal("100000.00"))


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
def superuser_balance(superuser):
    return UserBalanceFactory(user=superuser, balance=Decimal("100000.00"))


@pytest.fixture
def open_prop(user):
    return PropBet.objects.create(
        title="Will it rain tomorrow?",
        description="Simple weather prop",
        creator=user,
        status=PropBetStatus.OPEN,
        yes_odds=Decimal("2.000"),
        no_odds=Decimal("1.800"),
    )


@pytest.fixture
def admin_instance():
    return PropBetAdmin(model=PropBet, admin_site=AdminSite())


def _admin_request(rf, user):
    """Build a request with messages support for admin action tests."""
    request = rf.post("/admin/")
    request.user = user
    setattr(request, "session", "session")
    messages = FallbackStorage(request)
    setattr(request, "_messages", messages)
    return request


@pytest.fixture
def rf():
    return RequestFactory()


# ---------------------------------------------------------------------------
# Model basics
# ---------------------------------------------------------------------------


class TestPropBetModel:
    def test_str(self, open_prop):
        assert str(open_prop) == "Will it rain tomorrow?"

    def test_default_status_is_draft(self, user):
        prop = PropBet.objects.create(title="Test", creator=user)
        assert prop.status == PropBetStatus.DRAFT

    def test_id_hash_generated(self, open_prop):
        assert open_prop.id_hash
        assert len(open_prop.id_hash) == 8


class TestPropBetSlipModel:
    def test_str(self, open_prop, user, user_balance):
        slip = PropBetSlip.objects.create(
            user=user,
            prop=open_prop,
            selection="YES",
            odds=Decimal("2.000"),
            stake=Decimal("100.00"),
        )
        assert user.email in str(slip)
        assert "YES" in str(slip)

    def test_default_status_is_pending(self, open_prop, user, user_balance):
        slip = PropBetSlip.objects.create(
            user=user,
            prop=open_prop,
            selection="NO",
            odds=Decimal("1.800"),
            stake=Decimal("50.00"),
        )
        assert slip.status == BetStatus.PENDING


# ---------------------------------------------------------------------------
# Prop bets page
# ---------------------------------------------------------------------------


class TestPropBetsPageView:
    def test_requires_login(self, client):
        resp = client.get(reverse("hub:prop_bets"))
        assert resp.status_code == 302

    def test_renders_for_authed_user(self, authed_client, user_balance):
        resp = authed_client.get(reverse("hub:prop_bets"))
        assert resp.status_code == 200
        assert "hub/prop_bets.html" in [t.name for t in resp.templates]

    def test_shows_open_props(self, authed_client, user_balance, open_prop):
        resp = authed_client.get(reverse("hub:prop_bets"))
        assert open_prop.title in resp.content.decode()


# ---------------------------------------------------------------------------
# HTMX create partial
# ---------------------------------------------------------------------------


class TestPropBetCreatePartial:
    def test_get_returns_form(self, authed_client, user_balance):
        resp = authed_client.get(reverse("hub:prop_bet_create_partial"))
        assert resp.status_code == 200
        assert b"Create Prop" in resp.content

    def test_post_creates_prop(self, authed_client, user, user_balance):
        resp = authed_client.post(
            reverse("hub:prop_bet_create_partial"),
            {"title": "Test Prop", "yes_odds": "2.50", "no_odds": "1.60"},
        )
        assert resp.status_code == 200
        prop = PropBet.objects.get(title="Test Prop")
        assert prop.creator == user
        assert prop.status == PropBetStatus.OPEN
        assert prop.yes_odds == Decimal("2.50")

    def test_post_requires_title(self, authed_client, user_balance):
        resp = authed_client.post(
            reverse("hub:prop_bet_create_partial"),
            {"title": "", "yes_odds": "2.00", "no_odds": "2.00"},
        )
        assert resp.status_code == 400

    def test_post_invalid_odds(self, authed_client, user_balance):
        resp = authed_client.post(
            reverse("hub:prop_bet_create_partial"),
            {"title": "Test", "yes_odds": "abc", "no_odds": "2.00"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# HTMX place bet partial
# ---------------------------------------------------------------------------


class TestPropBetPlacePartial:
    def test_get_returns_form(self, authed_client, user_balance, open_prop):
        resp = authed_client.get(
            reverse("hub:prop_bet_place_partial", args=[open_prop.pk])
        )
        assert resp.status_code == 200
        assert open_prop.title.encode() in resp.content

    def test_post_places_bet(self, authed_client, user, user_balance, open_prop):
        resp = authed_client.post(
            reverse("hub:prop_bet_place_partial", args=[open_prop.pk]),
            {"selection": "YES", "stake": "500.00"},
        )
        assert resp.status_code == 200
        slip = PropBetSlip.objects.get(user=user, prop=open_prop)
        assert slip.selection == "YES"
        assert slip.odds == Decimal("2.000")
        assert slip.stake == Decimal("500.00")
        # Balance deducted
        user_balance.refresh_from_db()
        assert user_balance.balance == Decimal("99500.00")
        # Prop totals updated
        open_prop.refresh_from_db()
        assert open_prop.total_stake_yes == Decimal("500.00")

    def test_post_no_selection_places_bet(
        self, authed_client, user, user_balance, open_prop
    ):
        resp = authed_client.post(
            reverse("hub:prop_bet_place_partial", args=[open_prop.pk]),
            {"selection": "NO", "stake": "250.00"},
        )
        assert resp.status_code == 200
        slip = PropBetSlip.objects.get(user=user, prop=open_prop)
        assert slip.selection == "NO"
        assert slip.odds == Decimal("1.800")
        open_prop.refresh_from_db()
        assert open_prop.total_stake_no == Decimal("250.00")

    def test_insufficient_balance(self, authed_client, user_balance, open_prop):
        user_balance.balance = Decimal("10.00")
        user_balance.save()
        resp = authed_client.post(
            reverse("hub:prop_bet_place_partial", args=[open_prop.pk]),
            {"selection": "YES", "stake": "500.00"},
        )
        assert resp.status_code == 400
        assert not PropBetSlip.objects.exists()

    def test_invalid_selection(self, authed_client, user_balance, open_prop):
        resp = authed_client.post(
            reverse("hub:prop_bet_place_partial", args=[open_prop.pk]),
            {"selection": "MAYBE", "stake": "100.00"},
        )
        assert resp.status_code == 400

    def test_closed_market(self, authed_client, user_balance, open_prop):
        open_prop.status = PropBetStatus.CLOSED
        open_prop.save()
        resp = authed_client.post(
            reverse("hub:prop_bet_place_partial", args=[open_prop.pk]),
            {"selection": "YES", "stake": "100.00"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------


class TestPropBetListCreateAPI:
    def test_get_lists_open_props(self, authed_client, user_balance, open_prop):
        resp = authed_client.get(reverse("hub:prop_bets_api"))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["props"]) == 1
        assert data["props"][0]["title"] == open_prop.title

    def test_post_creates_prop(self, authed_client, user, user_balance):
        resp = authed_client.post(
            reverse("hub:prop_bets_api"),
            {"title": "API Prop", "yes_odds": "3.00", "no_odds": "1.40"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "API Prop"

    def test_requires_auth(self, client):
        resp = client.get(reverse("hub:prop_bets_api"))
        assert resp.status_code == 302


class TestPropBetPlaceBetAPI:
    def test_places_bet(self, authed_client, user, user_balance, open_prop):
        resp = authed_client.post(
            reverse("hub:prop_bet_place_api", args=[open_prop.pk]),
            {"selection": "YES", "stake": "1000.00"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payout"] == 2000.0
        assert PropBetSlip.objects.filter(user=user, prop=open_prop).exists()


# ---------------------------------------------------------------------------
# Settlement (admin actions)
# ---------------------------------------------------------------------------


class TestPropBetSettlement:
    def _make_bets(self, prop, users_and_balances):
        """Create YES and NO bets for testing settlement."""
        bets = []
        for user, balance, selection in users_and_balances:
            slip = PropBetSlip.objects.create(
                user=user,
                prop=prop,
                selection=selection,
                odds=prop.yes_odds if selection == "YES" else prop.no_odds,
                stake=Decimal("1000.00"),
            )
            bets.append(slip)
        return bets

    def test_settle_yes_pays_yes_bettors(
        self, rf, admin_instance, open_prop, superuser, superuser_balance
    ):
        user2 = UserFactory()
        bal2 = UserBalanceFactory(user=user2, balance=Decimal("100000.00"))

        self._make_bets(
            open_prop,
            [
                (superuser, superuser_balance, "YES"),
                (user2, bal2, "NO"),
            ],
        )

        request = _admin_request(rf, superuser)
        admin_instance.settle_yes(request, PropBet.objects.filter(pk=open_prop.pk))

        open_prop.refresh_from_db()
        assert open_prop.status == "SETTLED"
        assert open_prop.settled_outcome is True
        assert open_prop.settled_by == superuser

        yes_bet = PropBetSlip.objects.get(prop=open_prop, selection="YES")
        assert yes_bet.status == BetStatus.WON
        assert yes_bet.payout == Decimal("2000.000")

        no_bet = PropBetSlip.objects.get(prop=open_prop, selection="NO")
        assert no_bet.status == BetStatus.LOST
        assert no_bet.payout == 0

        # Balance credited for winner
        superuser_balance.refresh_from_db()
        assert superuser_balance.balance == Decimal("102000.000")

        # Balance unchanged for loser
        bal2.refresh_from_db()
        assert bal2.balance == Decimal("100000.00")

    def test_settle_no_pays_no_bettors(
        self, rf, admin_instance, open_prop, superuser, superuser_balance
    ):
        user2 = UserFactory()
        bal2 = UserBalanceFactory(user=user2, balance=Decimal("100000.00"))

        self._make_bets(
            open_prop,
            [
                (superuser, superuser_balance, "YES"),
                (user2, bal2, "NO"),
            ],
        )

        request = _admin_request(rf, superuser)
        admin_instance.settle_no(request, PropBet.objects.filter(pk=open_prop.pk))

        open_prop.refresh_from_db()
        assert open_prop.status == "SETTLED"
        assert open_prop.settled_outcome is False

        yes_bet = PropBetSlip.objects.get(prop=open_prop, selection="YES")
        assert yes_bet.status == BetStatus.LOST

        no_bet = PropBetSlip.objects.get(prop=open_prop, selection="NO")
        assert no_bet.status == BetStatus.WON
        assert no_bet.payout == Decimal("1800.000")

        bal2.refresh_from_db()
        assert bal2.balance == Decimal("101800.000")

    def test_settle_skips_already_settled(
        self, rf, admin_instance, open_prop, superuser, superuser_balance
    ):
        open_prop.status = "SETTLED"
        open_prop.save()

        request = _admin_request(rf, superuser)
        admin_instance.settle_yes(request, PropBet.objects.filter(pk=open_prop.pk))
        # No bets should have changed — already settled
        assert not PropBetSlip.objects.filter(prop=open_prop).exists()

    def test_non_superuser_cannot_settle(
        self, rf, admin_instance, open_prop, user, user_balance
    ):
        request = _admin_request(rf, user)
        admin_instance.settle_yes(request, PropBet.objects.filter(pk=open_prop.pk))
        open_prop.refresh_from_db()
        assert open_prop.status == PropBetStatus.OPEN  # unchanged

    def test_creates_balance_transactions(
        self, rf, admin_instance, open_prop, superuser, superuser_balance
    ):
        PropBetSlip.objects.create(
            user=superuser,
            prop=open_prop,
            selection="YES",
            odds=Decimal("2.000"),
            stake=Decimal("500.00"),
        )

        request = _admin_request(rf, superuser)
        admin_instance.settle_yes(request, PropBet.objects.filter(pk=open_prop.pk))

        txn = BalanceTransaction.objects.get(
            user=superuser,
            transaction_type=BalanceTransaction.Type.BET_WIN,
        )
        assert txn.amount == Decimal("1000.000")
        assert "Prop bet won" in txn.description

    def test_settlement_creates_notifications(
        self, rf, admin_instance, open_prop, superuser, superuser_balance
    ):
        user2 = UserFactory()
        UserBalanceFactory(user=user2, balance=Decimal("100000.00"))

        PropBetSlip.objects.create(
            user=superuser,
            prop=open_prop,
            selection="YES",
            odds=Decimal("2.000"),
            stake=Decimal("500.00"),
        )
        PropBetSlip.objects.create(
            user=user2,
            prop=open_prop,
            selection="NO",
            odds=Decimal("1.800"),
            stake=Decimal("500.00"),
        )

        request = _admin_request(rf, superuser)
        admin_instance.settle_yes(request, PropBet.objects.filter(pk=open_prop.pk))

        win_notif = Notification.objects.get(
            recipient=superuser, category=Notification.Category.BET_SETTLEMENT
        )
        assert "won" in win_notif.title
        assert "paid out" in win_notif.body

        lose_notif = Notification.objects.get(
            recipient=user2, category=Notification.Category.BET_SETTLEMENT
        )
        assert "lost" in lose_notif.title


# ---------------------------------------------------------------------------
# Cancellation (admin action)
# ---------------------------------------------------------------------------


class TestPropBetCancellation:
    def test_cancel_refunds_bets(
        self, rf, admin_instance, open_prop, superuser, superuser_balance
    ):
        user2 = UserFactory()
        bal2 = UserBalanceFactory(user=user2, balance=Decimal("50000.00"))

        PropBetSlip.objects.create(
            user=superuser,
            prop=open_prop,
            selection="YES",
            odds=Decimal("2.000"),
            stake=Decimal("1000.00"),
        )
        PropBetSlip.objects.create(
            user=user2,
            prop=open_prop,
            selection="NO",
            odds=Decimal("1.800"),
            stake=Decimal("500.00"),
        )

        request = _admin_request(rf, superuser)
        admin_instance.cancel_prop(request, PropBet.objects.filter(pk=open_prop.pk))

        open_prop.refresh_from_db()
        assert open_prop.status == "CANCELLED"

        for slip in PropBetSlip.objects.filter(prop=open_prop):
            assert slip.status == BetStatus.VOID
            assert slip.payout == slip.stake

        superuser_balance.refresh_from_db()
        assert superuser_balance.balance == Decimal("101000.00")

        bal2.refresh_from_db()
        assert bal2.balance == Decimal("50500.00")

        void_txns = BalanceTransaction.objects.filter(
            transaction_type=BalanceTransaction.Type.BET_VOID,
        )
        assert void_txns.count() == 2

        # Both users notified
        cancel_notifs = Notification.objects.filter(
            category=Notification.Category.BET_SETTLEMENT
        )
        assert cancel_notifs.count() == 2
        assert all("cancelled" in n.title.lower() for n in cancel_notifs)

    def test_cancel_skips_settled(
        self, rf, admin_instance, open_prop, superuser, superuser_balance
    ):
        open_prop.status = "SETTLED"
        open_prop.save()

        request = _admin_request(rf, superuser)
        admin_instance.cancel_prop(request, PropBet.objects.filter(pk=open_prop.pk))

        open_prop.refresh_from_db()
        assert open_prop.status == "SETTLED"  # unchanged

    def test_non_superuser_cannot_cancel(
        self, rf, admin_instance, open_prop, user, user_balance
    ):
        request = _admin_request(rf, user)
        admin_instance.cancel_prop(request, PropBet.objects.filter(pk=open_prop.pk))

        open_prop.refresh_from_db()
        assert open_prop.status == PropBetStatus.OPEN  # unchanged


# ---------------------------------------------------------------------------
# My Bets integration
# ---------------------------------------------------------------------------


class TestMyBetsIncludesPropBets:
    def test_prop_bets_in_activity(self, authed_client, user, user_balance, open_prop):
        PropBetSlip.objects.create(
            user=user,
            prop=open_prop,
            selection="YES",
            odds=Decimal("2.000"),
            stake=Decimal("100.00"),
        )
        resp = authed_client.get(reverse("hub:my_bets"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "PROP" in content
        assert open_prop.title in content
