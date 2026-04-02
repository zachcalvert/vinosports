"""Tests for NFL futures odds engine and futures settlement."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from nfl.betting.futures_odds_engine import (
    _championship_strength,
    _generate_odds_from_rankings,
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
from nfl.betting.preseason_rankings import (
    PRESEASON_POWER_RANKINGS,
    RANKINGS_SEASON,
    rank_to_strength,
)
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
# Preseason Rankings & Offseason Fallback
# ---------------------------------------------------------------------------


class TestRankToStrength:
    def test_rank_1_is_strongest(self):
        assert rank_to_strength(1, 32) == 1.0

    def test_rank_32_is_weakest(self):
        assert rank_to_strength(32, 32) == pytest.approx(0.0, abs=0.001)

    def test_midrank(self):
        assert 0.4 < rank_to_strength(16, 32) < 0.6


class TestPreseasonRankings:
    def test_all_32_teams_ranked(self):
        assert len(PRESEASON_POWER_RANKINGS) == 32

    def test_ranks_are_unique(self):
        ranks = list(PRESEASON_POWER_RANKINGS.values())
        assert len(set(ranks)) == 32

    def test_ranks_range_1_to_32(self):
        ranks = sorted(PRESEASON_POWER_RANKINGS.values())
        assert ranks == list(range(1, 33))


@pytest.mark.django_db
class TestGenerateOddsFromRankings:
    def _create_ranked_teams(
        self, abbrevs, conference=Conference.AFC, division=Division.AFC_EAST
    ):
        teams = []
        for abbr in abbrevs:
            teams.append(
                TeamFactory(abbreviation=abbr, conference=conference, division=division)
            )
        return teams

    def test_returns_odds_for_ranked_teams(self):
        teams = self._create_ranked_teams(["SEA", "LAR", "BUF", "NE"])
        results = _generate_odds_from_rankings(teams, 2.0, 0.30)
        assert len(results) == 4

    def test_higher_ranked_team_gets_shorter_odds(self):
        teams = self._create_ranked_teams(["SEA", "CLE"])
        results = _generate_odds_from_rankings(teams, 2.0, 0.30)
        odds_by_id = {r["team_id"]: r["odds"] for r in results}
        # SEA rank 1 should have shorter (lower) odds than CLE rank 32
        assert odds_by_id[teams[0].pk] < odds_by_id[teams[1].pk]

    def test_skips_unranked_teams(self):
        teams = self._create_ranked_teams(["SEA", "ZZZ"])
        results = _generate_odds_from_rankings(teams, 2.0, 0.30)
        assert len(results) == 1

    def test_daily_drift_is_deterministic(self):
        """Same date produces same odds."""
        teams = self._create_ranked_teams(["SEA", "BUF"])
        r1 = _generate_odds_from_rankings(teams, 2.0, 0.30)
        r2 = _generate_odds_from_rankings(teams, 2.0, 0.30)
        assert r1 == r2

    def test_different_day_produces_different_odds(self):
        """Mocking a different date should shift odds."""
        teams = self._create_ranked_teams(["SEA", "BUF", "KC", "CLE"])

        r1 = _generate_odds_from_rankings(teams, 2.0, 0.30)

        with patch("nfl.betting.futures_odds_engine.timezone") as mock_tz:
            mock_now = MagicMock()
            mock_now.date.return_value = date(2099, 1, 1)
            mock_tz.now.return_value = mock_now
            r2 = _generate_odds_from_rankings(teams, 2.0, 0.30)

        # At least one team's odds should differ
        odds1 = {r["team_id"]: r["odds"] for r in r1}
        odds2 = {r["team_id"]: r["odds"] for r in r2}
        assert odds1 != odds2


@pytest.mark.django_db
class TestFuturesOddsPreseasonFallback:
    def _create_all_teams(self):
        """Create teams matching the 32 abbreviations in PRESEASON_POWER_RANKINGS."""
        # Conference/division assignments for test teams
        afc_divs = [
            Division.AFC_EAST,
            Division.AFC_NORTH,
            Division.AFC_SOUTH,
            Division.AFC_WEST,
        ]
        nfc_divs = [
            Division.NFC_EAST,
            Division.NFC_NORTH,
            Division.NFC_SOUTH,
            Division.NFC_WEST,
        ]

        afc_abbrevs = [
            "BUF",
            "NE",
            "MIA",
            "NYJ",
            "BAL",
            "CIN",
            "CLE",
            "PIT",
            "HOU",
            "IND",
            "JAX",
            "TEN",
            "DEN",
            "KC",
            "LV",
            "LAC",
        ]
        nfc_abbrevs = [
            "DAL",
            "NYG",
            "PHI",
            "WAS",
            "CHI",
            "DET",
            "GB",
            "MIN",
            "ATL",
            "CAR",
            "NO",
            "TB",
            "ARI",
            "LAR",
            "SF",
            "SEA",
        ]

        teams = []
        for i, abbr in enumerate(afc_abbrevs):
            teams.append(
                TeamFactory(
                    abbreviation=abbr,
                    conference=Conference.AFC,
                    division=afc_divs[i // 4],
                )
            )
        for i, abbr in enumerate(nfc_abbrevs):
            teams.append(
                TeamFactory(
                    abbreviation=abbr,
                    conference=Conference.NFC,
                    division=nfc_divs[i // 4],
                )
            )
        return teams

    def test_super_bowl_fallback_returns_32_teams(self):
        self._create_all_teams()
        results = generate_futures_odds(
            season=RANKINGS_SEASON, market_type="SUPER_BOWL"
        )
        assert len(results) == 32

    def test_conference_fallback_returns_16_teams(self):
        self._create_all_teams()
        results = generate_futures_odds(
            season=RANKINGS_SEASON, market_type="AFC_CHAMPION"
        )
        assert len(results) == 16

    def test_division_fallback_returns_4_teams(self):
        self._create_all_teams()
        results = generate_futures_odds(
            season=RANKINGS_SEASON,
            market_type="DIVISION",
            division=Division.AFC_EAST,
        )
        assert len(results) == 4

    def test_no_fallback_for_non_rankings_season(self):
        self._create_all_teams()
        results = generate_futures_odds(
            season=RANKINGS_SEASON - 5, market_type="SUPER_BOWL"
        )
        assert results == []

    def test_standings_take_precedence_over_rankings(self):
        """When standings exist, use them instead of preseason rankings."""
        teams = self._create_all_teams()
        # Create standings for just 2 teams
        for t in teams[:2]:
            StandingFactory(team=t, season=RANKINGS_SEASON)
        results = generate_futures_odds(
            season=RANKINGS_SEASON, market_type="SUPER_BOWL"
        )
        # Should use standings (2 teams), not rankings (32 teams)
        assert len(results) == 2


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
