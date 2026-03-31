"""Tests for NFL futures odds engine and futures settlement."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from nfl.betting.futures_odds_engine import (
    _championship_strength,
    _softmax,
    generate_division_odds,
    generate_futures_odds,
    generate_super_bowl_odds,
)
from nfl.betting.futures_settlement import (
    settle_futures_market,
    void_futures_market,
)
from nfl.betting.models import FuturesBet, FuturesMarket, FuturesOutcome
from nfl.games.models import Conference, Division
from nfl.tests.factories import (
    StandingFactory,
    TeamFactory,
    UserBalanceFactory,
    UserFactory,
)
from vinosports.betting.models import BetStatus, FuturesMarketStatus

# ---------------------------------------------------------------------------
# Futures Odds Engine
# ---------------------------------------------------------------------------


class TestChampionshipStrength:
    def test_high_strength(self):
        standing = MagicMock(win_pct=0.800, point_differential=100)
        strength = _championship_strength(standing)
        assert strength > 0.6

    def test_low_strength(self):
        standing = MagicMock(win_pct=0.200, point_differential=-100)
        strength = _championship_strength(standing)
        assert strength < 0.35


class TestSoftmax:
    def test_sums_to_one(self):
        probs = _softmax([0.8, 0.5, 0.3], 1.0)
        assert abs(sum(probs) - 1.0) < 0.001

    def test_higher_strength_gets_higher_prob(self):
        probs = _softmax([0.9, 0.5, 0.1], 1.0)
        assert probs[0] > probs[1] > probs[2]


class TestGenerateSuperBowlOdds:
    def test_returns_one_entry_per_team(self):
        standings = [
            MagicMock(team_id=i, win_pct=0.5, point_differential=0) for i in range(32)
        ]
        results = generate_super_bowl_odds(standings)
        assert len(results) == 32

    def test_empty_standings(self):
        assert generate_super_bowl_odds([]) == []


class TestGenerateDivisionOdds:
    def test_four_team_division(self):
        standings = [
            MagicMock(team_id=i, win_pct=0.5 + i * 0.1, point_differential=i * 20)
            for i in range(4)
        ]
        results = generate_division_odds(standings)
        assert len(results) == 4

    def test_best_team_has_shortest_odds(self):
        standings = [
            MagicMock(team_id=1, win_pct=0.900, point_differential=150),
            MagicMock(team_id=2, win_pct=0.300, point_differential=-100),
        ]
        results = generate_division_odds(standings)
        # Lower (more negative) American odds = shorter odds = more favored
        best = [r for r in results if r["team_id"] == 1][0]
        worst = [r for r in results if r["team_id"] == 2][0]
        assert best["odds"] < worst["odds"]


@pytest.mark.django_db
class TestGenerateFuturesOdds:
    def test_super_bowl_uses_all_standings(self):
        for i in range(4):
            team = TeamFactory(conference=Conference.AFC, division=Division.AFC_EAST)
            StandingFactory(
                team=team,
                season=2025,
                conference=Conference.AFC,
                division=Division.AFC_EAST,
            )
        results = generate_futures_odds(season=2025, market_type="SUPER_BOWL")
        assert len(results) == 4

    def test_conference_filters_by_conference(self):
        afc_team = TeamFactory(conference=Conference.AFC, division=Division.AFC_EAST)
        nfc_team = TeamFactory(conference=Conference.NFC, division=Division.NFC_EAST)
        StandingFactory(
            team=afc_team,
            season=2025,
            conference=Conference.AFC,
            division=Division.AFC_EAST,
        )
        StandingFactory(
            team=nfc_team,
            season=2025,
            conference=Conference.NFC,
            division=Division.NFC_EAST,
        )
        results = generate_futures_odds(season=2025, market_type="AFC_CHAMPION")
        assert len(results) == 1
        assert results[0]["team_id"] == afc_team.pk

    def test_division_filters_by_division(self):
        t1 = TeamFactory(conference=Conference.AFC, division=Division.AFC_EAST)
        t2 = TeamFactory(conference=Conference.AFC, division=Division.AFC_NORTH)
        StandingFactory(
            team=t1, season=2025, conference=Conference.AFC, division=Division.AFC_EAST
        )
        StandingFactory(
            team=t2, season=2025, conference=Conference.AFC, division=Division.AFC_NORTH
        )
        results = generate_futures_odds(
            season=2025, market_type="DIVISION", division=Division.AFC_EAST
        )
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Futures Settlement
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSettleFuturesMarket:
    def _setup_market(self):
        team1 = TeamFactory()
        team2 = TeamFactory()
        market = FuturesMarket.objects.create(
            name="Super Bowl Winner 2025",
            season="2025",
            market_type="SUPER_BOWL",
            status=FuturesMarketStatus.OPEN,
        )
        outcome1 = FuturesOutcome.objects.create(market=market, team=team1, odds=150)
        outcome2 = FuturesOutcome.objects.create(market=market, team=team2, odds=250)
        return market, team1, team2, outcome1, outcome2

    def test_settling_pays_winner(self):
        market, team1, team2, outcome1, outcome2 = self._setup_market()
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))

        FuturesBet.objects.create(
            user=user,
            outcome=outcome1,
            odds_at_placement=150,
            stake=Decimal("100.00"),
        )

        result = settle_futures_market(market.pk, team1.pk)

        assert result["won"] == 1
        assert result["lost"] == 0

    def test_settling_loses_wrong_pick(self):
        market, team1, team2, outcome1, outcome2 = self._setup_market()
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))

        FuturesBet.objects.create(
            user=user,
            outcome=outcome2,
            odds_at_placement=250,
            stake=Decimal("100.00"),
        )

        result = settle_futures_market(market.pk, team1.pk)

        assert result["won"] == 0
        assert result["lost"] == 1

    def test_raises_for_non_open_market(self):
        market, team1, _, _, _ = self._setup_market()
        market.status = FuturesMarketStatus.SETTLED
        market.save()

        with pytest.raises(ValueError, match="not OPEN"):
            settle_futures_market(market.pk, team1.pk)


@pytest.mark.django_db
class TestVoidFuturesMarket:
    def test_refunds_pending_bets(self):
        team = TeamFactory()
        market = FuturesMarket.objects.create(
            name="AFC Champion 2025",
            season="2025",
            market_type="AFC_CHAMPION",
            status=FuturesMarketStatus.OPEN,
        )
        outcome = FuturesOutcome.objects.create(market=market, team=team, odds=300)
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("900.00"))

        FuturesBet.objects.create(
            user=user,
            outcome=outcome,
            odds_at_placement=300,
            stake=Decimal("100.00"),
        )

        result = void_futures_market(market.pk)

        assert result["refunded"] == 1
        bet = FuturesBet.objects.get(outcome=outcome)
        assert bet.status == BetStatus.VOID

    def test_raises_for_settled_market(self):
        market = FuturesMarket.objects.create(
            name="Test",
            season="2025",
            market_type="SUPER_BOWL",
            status=FuturesMarketStatus.SETTLED,
        )
        with pytest.raises(ValueError, match="cannot void"):
            void_futures_market(market.pk)
