"""Tests for one-click featured parlay opt-in (EPL)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from epl.betting.models import Parlay
from vinosports.betting.featured import FeaturedParlay, FeaturedParlayLeg
from vinosports.betting.models import UserBalance

from .factories import MatchFactory, OddsFactory, UserBalanceFactory, UserFactory

pytestmark = pytest.mark.django_db


def _create_featured_parlay(matches, sponsor=None):
    """Helper to create an active featured parlay with legs for the given matches."""
    if sponsor is None:
        sponsor = UserFactory(is_bot=True)
    fp = FeaturedParlay.objects.create(
        league="epl",
        sponsor=sponsor,
        title="Test Parlay",
        description="Test description.",
        expires_at=timezone.now() + timedelta(days=1),
        combined_odds=Decimal("6.00"),
        potential_payout=Decimal("60.00"),
        reference_stake=Decimal("10.00"),
    )
    selections = ["HOME_WIN", "AWAY_WIN", "DRAW"]
    for i, match in enumerate(matches):
        FeaturedParlayLeg.objects.create(
            featured_parlay=fp,
            event_id=match.pk,
            event_label=f"{match.home_team.name} vs {match.away_team.name}",
            selection=selections[i % len(selections)],
            selection_label=selections[i % len(selections)].replace("_", " ").title(),
            odds_snapshot=Decimal("2.00"),
        )
    return fp


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
    def test_places_parlay(self, auth_client):
        c, user = auth_client
        matches = [MatchFactory() for _ in range(3)]
        for m in matches:
            OddsFactory(
                match=m,
                home_win=Decimal("2.00"),
                draw=Decimal("3.00"),
                away_win=Decimal("4.00"),
            )
        fp = _create_featured_parlay(matches)

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url)

        assert resp.status_code == 200
        parlay = Parlay.objects.get(user=user)
        assert parlay.featured_parlay == fp
        assert parlay.stake == Decimal("10.00")
        assert parlay.legs.count() == 3

    def test_deducts_balance(self, auth_client):
        c, user = auth_client
        matches = [MatchFactory() for _ in range(2)]
        for m in matches:
            OddsFactory(
                match=m,
                home_win=Decimal("2.00"),
                draw=Decimal("3.00"),
                away_win=Decimal("4.00"),
            )
        fp = _create_featured_parlay(matches)

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        c.post(url)

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("990.00")

    def test_uses_current_odds_not_snapshot(self, auth_client):
        c, user = auth_client
        matches = [MatchFactory() for _ in range(2)]
        for m in matches:
            OddsFactory(
                match=m,
                home_win=Decimal("3.00"),
                draw=Decimal("5.00"),
                away_win=Decimal("6.00"),
            )
        fp = _create_featured_parlay(matches)

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        c.post(url)

        parlay = Parlay.objects.get(user=user)
        # Odds should be the live odds (3.00 and 6.00), not the snapshot (2.00)
        assert parlay.combined_odds != Decimal("4.00")  # 2.00 * 2.00 snapshot

    def test_renders_confirmation(self, auth_client):
        c, user = auth_client
        matches = [MatchFactory() for _ in range(2)]
        for m in matches:
            OddsFactory(
                match=m,
                home_win=Decimal("2.00"),
                draw=Decimal("3.00"),
                away_win=Decimal("4.00"),
            )
        fp = _create_featured_parlay(matches)

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url)

        assert b"Parlay Placed!" in resp.content


class TestPlaceFeaturedParlayErrors:
    def test_duplicate_placement_rejected(self, auth_client):
        c, user = auth_client
        matches = [MatchFactory() for _ in range(2)]
        for m in matches:
            OddsFactory(
                match=m,
                home_win=Decimal("2.00"),
                draw=Decimal("3.00"),
                away_win=Decimal("4.00"),
            )
        fp = _create_featured_parlay(matches)

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        c.post(url)
        resp = c.post(url)

        assert resp.status_code == 200
        assert b"already placed" in resp.content
        assert Parlay.objects.filter(user=user).count() == 1

    def test_expired_parlay_404(self, auth_client):
        c, user = auth_client
        matches = [MatchFactory() for _ in range(2)]
        for m in matches:
            OddsFactory(match=m)
        fp = _create_featured_parlay(matches)
        fp.status = FeaturedParlay.Status.EXPIRED
        fp.save()

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url)

        assert resp.status_code == 404

    def test_wrong_league_404(self, auth_client):
        c, _ = auth_client
        sponsor = UserFactory(is_bot=True)
        fp = FeaturedParlay.objects.create(
            league="nba",
            sponsor=sponsor,
            title="NBA Parlay",
            expires_at=timezone.now() + timedelta(days=1),
            combined_odds=Decimal("5.00"),
            potential_payout=Decimal("50.00"),
        )

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url)

        assert resp.status_code == 404

    def test_stale_match_returns_error(self, auth_client):
        from epl.matches.models import Match

        c, _ = auth_client
        matches = [MatchFactory() for _ in range(2)]
        for m in matches:
            OddsFactory(
                match=m,
                home_win=Decimal("2.00"),
                draw=Decimal("3.00"),
                away_win=Decimal("4.00"),
            )

        # Start one match so it's no longer bettable
        matches[0].status = Match.Status.IN_PLAY
        matches[0].save()

        fp = _create_featured_parlay(matches)

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url)

        assert resp.status_code == 200
        assert b"no longer accepting bets" in resp.content
        assert Parlay.objects.count() == 0

    def test_insufficient_balance(self, auth_client):
        c, user = auth_client
        UserBalance.objects.filter(user=user).update(balance=Decimal("5.00"))

        matches = [MatchFactory() for _ in range(2)]
        for m in matches:
            OddsFactory(
                match=m,
                home_win=Decimal("2.00"),
                draw=Decimal("3.00"),
                away_win=Decimal("4.00"),
            )
        fp = _create_featured_parlay(matches)

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url)

        assert resp.status_code == 200
        assert b"Insufficient balance" in resp.content
        assert Parlay.objects.count() == 0

    def test_no_odds_available(self, auth_client):
        c, _ = auth_client
        matches = [MatchFactory() for _ in range(2)]
        # Don't create any odds
        fp = _create_featured_parlay(matches)

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url)

        assert resp.status_code == 200
        assert b"No odds available" in resp.content
        assert Parlay.objects.count() == 0


class TestPlaceFeaturedParlayAuth:
    def test_unauthenticated_redirects(self):
        c = Client()
        matches = [MatchFactory() for _ in range(2)]
        for m in matches:
            OddsFactory(match=m)
        fp = _create_featured_parlay(matches)

        url = reverse("epl_betting:place_featured_parlay", args=[fp.pk])
        resp = c.post(url)

        assert resp.status_code == 302
        assert "/login/" in resp.url
