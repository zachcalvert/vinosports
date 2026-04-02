"""Tests for featured parlay opt-in (NBA)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from nba.betting.models import Parlay
from nba.games.models import GameStatus
from vinosports.betting.featured import FeaturedParlay, FeaturedParlayLeg
from vinosports.betting.models import UserBalance

from .factories import GameFactory, OddsFactory, UserBalanceFactory, UserFactory

pytestmark = pytest.mark.django_db


def _create_featured_parlay(games, sponsor=None):
    """Helper to create an active featured parlay with legs for the given games."""
    if sponsor is None:
        sponsor = UserFactory(is_bot=True)
    fp = FeaturedParlay.objects.create(
        league="nba",
        sponsor=sponsor,
        title="Test NBA Parlay",
        description="Test description.",
        expires_at=timezone.now() + timedelta(days=1),
        combined_odds=Decimal("6.00"),
        potential_payout=Decimal("60000.00"),
        reference_stake=Decimal("10000.00"),
    )
    for game in games:
        FeaturedParlayLeg.objects.create(
            featured_parlay=fp,
            event_id=game.pk,
            event_label=f"{game.home_team.name} vs {game.away_team.name}",
            selection="HOME",
            selection_label="Home Win",
            odds_snapshot=Decimal("1.67"),
            extras_json={"market": "MONEYLINE"},
        )
    return fp


def _games_with_odds(n=2):
    games = [GameFactory() for _ in range(n)]
    for g in games:
        OddsFactory(game=g)
    return games


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


class TestPlaceFeaturedParlaySuccess:
    def test_places_parlay_with_default_stake(self, auth_client):
        c, user = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "10.00"})

        assert resp.status_code == 200
        parlay = Parlay.objects.get(user=user)
        assert parlay.featured_parlay == fp
        assert parlay.stake == Decimal("10.00")
        assert parlay.legs.count() == 2

    def test_places_parlay_with_custom_stake(self, auth_client):
        c, user = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "25.00"})

        assert resp.status_code == 200
        parlay = Parlay.objects.get(user=user)
        assert parlay.stake == Decimal("25.00")

    def test_deducts_custom_stake_from_balance(self, auth_client):
        c, user = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        c.post(url, {"stake": "50.00"})

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("950.00")

    def test_renders_confirmation(self, auth_client):
        c, user = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "10.00"})

        assert b"Parlay Placed!" in resp.content

    def test_spread_market_legs(self, auth_client):
        c, user = auth_client
        games = [GameFactory() for _ in range(2)]
        for g in games:
            OddsFactory(game=g, spread_line=-3.5, spread_home=-110, spread_away=-110)
        fp = _create_featured_parlay(games)
        # Override legs to use SPREAD market
        fp.legs.all().delete()
        for game in games:
            FeaturedParlayLeg.objects.create(
                featured_parlay=fp,
                event_id=game.pk,
                event_label=f"{game.home_team.name} vs {game.away_team.name}",
                selection="HOME",
                selection_label="Home -3.5",
                odds_snapshot=Decimal("1.91"),
                extras_json={"market": "SPREAD", "line": -3.5},
            )

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "10.00"})

        assert resp.status_code == 200
        parlay = Parlay.objects.get(user=user)
        assert parlay.legs.count() == 2
        for leg in parlay.legs.all():
            assert leg.market == "SPREAD"
            assert leg.odds_at_placement == -110


class TestPlaceFeaturedParlayStakeValidation:
    def test_missing_stake_returns_error(self, auth_client):
        c, _ = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url)

        assert resp.status_code == 200
        assert b"valid wager" in resp.content
        assert Parlay.objects.count() == 0

    def test_invalid_stake_returns_error(self, auth_client):
        c, _ = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "abc"})

        assert resp.status_code == 200
        assert b"valid wager" in resp.content
        assert Parlay.objects.count() == 0

    def test_stake_below_minimum(self, auth_client):
        c, _ = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "0.10"})

        assert resp.status_code == 200
        assert b"Minimum wager" in resp.content
        assert Parlay.objects.count() == 0

    def test_stake_above_maximum(self, auth_client):
        c, _ = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "200000000"})

        assert resp.status_code == 200
        assert b"Maximum wager" in resp.content
        assert Parlay.objects.count() == 0


class TestPlaceFeaturedParlayErrors:
    def test_duplicate_placement_rejected(self, auth_client):
        c, user = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        c.post(url, {"stake": "10.00"})
        resp = c.post(url, {"stake": "10.00"})

        assert resp.status_code == 200
        assert b"already placed" in resp.content
        assert Parlay.objects.filter(user=user).count() == 1

    def test_expired_parlay_404(self, auth_client):
        c, _ = auth_client
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)
        fp.status = FeaturedParlay.Status.EXPIRED
        fp.save()

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "10.00"})

        assert resp.status_code == 404

    def test_wrong_league_404(self, auth_client):
        c, _ = auth_client
        sponsor = UserFactory(is_bot=True)
        fp = FeaturedParlay.objects.create(
            league="epl",
            sponsor=sponsor,
            title="EPL Parlay",
            expires_at=timezone.now() + timedelta(days=1),
            combined_odds=Decimal("5.00"),
            potential_payout=Decimal("50.00"),
        )

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "10.00"})

        assert resp.status_code == 404

    def test_stale_game_returns_error(self, auth_client):
        c, _ = auth_client
        games = _games_with_odds(2)

        games[0].status = GameStatus.FINAL
        games[0].save()

        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "10.00"})

        assert resp.status_code == 200
        assert b"no longer accepting bets" in resp.content
        assert Parlay.objects.count() == 0

    def test_insufficient_balance(self, auth_client):
        c, user = auth_client
        UserBalance.objects.filter(user=user).update(balance=Decimal("5.00"))

        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "10.00"})

        assert resp.status_code == 200
        assert b"Insufficient balance" in resp.content
        assert Parlay.objects.count() == 0

    def test_no_odds_available(self, auth_client):
        c, _ = auth_client
        games = [GameFactory() for _ in range(2)]
        # No odds created
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "10.00"})

        assert resp.status_code == 200
        assert b"No odds available" in resp.content
        assert Parlay.objects.count() == 0


class TestPlaceFeaturedParlayAuth:
    def test_unauthenticated_redirects(self):
        c = Client()
        games = _games_with_odds(2)
        fp = _create_featured_parlay(games)

        url = reverse("nba_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url, {"stake": "10.00"})

        assert resp.status_code == 302
        assert "/login/" in resp.url
