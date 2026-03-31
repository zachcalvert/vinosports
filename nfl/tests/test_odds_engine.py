"""Tests for the NFL algorithmic odds engine."""

from unittest.mock import MagicMock

import pytest

from nfl.betting.odds_engine import (
    MAX_ML,
    MAX_TOTAL,
    MIN_ML,
    MIN_TOTAL,
    STANDARD_JUICE,
    _moneyline,
    _norm_point_diff,
    _probability_to_american,
    _snap_to_key_number,
    _spread,
    _team_strength,
    _total,
    _win_probability,
    generate_all_upcoming_odds,
    generate_game_odds,
)
from nfl.games.models import GameStatus
from nfl.tests.factories import GameFactory, StandingFactory, TeamFactory

# ---------------------------------------------------------------------------
# _norm_point_diff
# ---------------------------------------------------------------------------


class TestNormPointDiff:
    def test_zero_diff(self):
        standing = MagicMock()
        standing.point_differential = 0
        assert _norm_point_diff(standing) == 0.5

    def test_positive_diff(self):
        standing = MagicMock()
        standing.point_differential = 100
        assert _norm_point_diff(standing) == 0.75

    def test_extreme_negative_clamped(self):
        standing = MagicMock()
        standing.point_differential = -300
        assert _norm_point_diff(standing) == 0.0


# ---------------------------------------------------------------------------
# _team_strength
# ---------------------------------------------------------------------------


class TestTeamStrength:
    def test_high_winpct_positive_pd(self):
        standing = MagicMock()
        standing.win_pct = 0.800
        standing.point_differential = 100
        strength = _team_strength(standing)
        assert strength > 0.6

    def test_low_winpct_negative_pd(self):
        standing = MagicMock()
        standing.win_pct = 0.200
        standing.point_differential = -100
        strength = _team_strength(standing)
        assert strength < 0.35

    def test_fallback_on_none_winpct(self):
        standing = MagicMock()
        standing.win_pct = None
        standing.point_differential = 0
        strength = _team_strength(standing)
        assert strength > 0


# ---------------------------------------------------------------------------
# _win_probability
# ---------------------------------------------------------------------------


class TestWinProbability:
    def test_equal_teams(self):
        h = MagicMock(win_pct=0.500, point_differential=0)
        a = MagicMock(win_pct=0.500, point_differential=0)
        p = _win_probability(h, a)
        assert p > 0.5  # home field advantage

    def test_strong_home_team(self):
        h = MagicMock(win_pct=0.800, point_differential=150)
        a = MagicMock(win_pct=0.300, point_differential=-100)
        p = _win_probability(h, a)
        assert p > 0.6

    def test_clamped_to_range(self):
        h = MagicMock(win_pct=0.950, point_differential=200)
        a = MagicMock(win_pct=0.050, point_differential=-200)
        p = _win_probability(h, a)
        assert 0.05 <= p <= 0.95

    def test_none_standings(self):
        p = _win_probability(None, None)
        assert 0.45 <= p <= 0.55


# ---------------------------------------------------------------------------
# _snap_to_key_number
# ---------------------------------------------------------------------------


class TestSnapToKeyNumber:
    def test_snap_to_3(self):
        assert _snap_to_key_number(-2.8) == -3.0
        assert _snap_to_key_number(-3.2) == -3.0

    def test_snap_to_7(self):
        assert _snap_to_key_number(-6.5) == -7.0
        assert _snap_to_key_number(-7.5) == -7.0

    def test_snap_to_10(self):
        assert _snap_to_key_number(-9.7) == -10.0

    def test_no_snap_far_from_key(self):
        # 5.0 is not near any key number
        result = _snap_to_key_number(-5.0)
        assert result == -5.0

    def test_preserves_sign(self):
        assert _snap_to_key_number(2.8) == 3.0
        assert _snap_to_key_number(6.5) == 7.0

    def test_zero(self):
        result = _snap_to_key_number(0.0)
        assert result == 0.0


# ---------------------------------------------------------------------------
# _probability_to_american
# ---------------------------------------------------------------------------


class TestProbabilityToAmerican:
    def test_coin_flip(self):
        odds = _probability_to_american(0.5)
        assert odds == 100

    def test_heavy_favorite(self):
        odds = _probability_to_american(0.8)
        assert odds < 0

    def test_underdog(self):
        odds = _probability_to_american(0.25)
        assert odds > 0

    def test_edge_cases(self):
        assert _probability_to_american(0.0) == -110
        assert _probability_to_american(1.0) == -110


# ---------------------------------------------------------------------------
# _moneyline
# ---------------------------------------------------------------------------


class TestMoneyline:
    def test_returns_two_ints(self):
        home_ml, away_ml = _moneyline(0.6)
        assert isinstance(home_ml, int)
        assert isinstance(away_ml, int)

    def test_clamped(self):
        home_ml, away_ml = _moneyline(0.99)
        assert home_ml >= MIN_ML
        assert away_ml <= MAX_ML

    def test_favorite_negative_underdog_positive(self):
        home_ml, away_ml = _moneyline(0.7)
        assert home_ml < 0
        assert away_ml > 0


# ---------------------------------------------------------------------------
# _spread
# ---------------------------------------------------------------------------


class TestSpread:
    def test_home_favored(self):
        spread_line, home_juice, away_juice = _spread(0.7)
        assert spread_line < 0
        assert home_juice == STANDARD_JUICE
        assert away_juice == STANDARD_JUICE

    def test_even_game(self):
        spread_line, _, _ = _spread(0.5)
        assert spread_line == 0.0

    def test_away_favored(self):
        spread_line, _, _ = _spread(0.3)
        assert spread_line > 0

    def test_snaps_to_key_numbers(self):
        """A probability that produces a ~3-point spread should snap to 3."""
        # p=0.5 + small offset to produce ~3 point raw spread
        # raw = -(p - 0.5) * 28; for raw = -3, p = 0.5 + 3/28 ≈ 0.607
        spread_line, _, _ = _spread(0.607)
        assert spread_line == -3.0


# ---------------------------------------------------------------------------
# _total
# ---------------------------------------------------------------------------


class TestTotal:
    def test_within_bounds(self):
        h = MagicMock(win_pct=0.600, point_differential=50)
        a = MagicMock(win_pct=0.600, point_differential=50)
        total_line, over, under = _total(h, a)
        assert MIN_TOTAL <= total_line <= MAX_TOTAL
        assert over == STANDARD_JUICE
        assert under == STANDARD_JUICE

    def test_none_standings(self):
        total_line, _, _ = _total(None, None)
        assert MIN_TOTAL <= total_line <= MAX_TOTAL

    def test_nfl_range(self):
        """NFL totals should be in the 35-60 range, not NBA's 195-250."""
        h = MagicMock(win_pct=0.500, point_differential=0)
        a = MagicMock(win_pct=0.500, point_differential=0)
        total_line, _, _ = _total(h, a)
        assert 35 <= total_line <= 60


# ---------------------------------------------------------------------------
# generate_game_odds
# ---------------------------------------------------------------------------


class TestGenerateGameOdds:
    def test_returns_all_fields(self):
        h = MagicMock(win_pct=0.600, point_differential=50)
        a = MagicMock(win_pct=0.400, point_differential=-50)
        result = generate_game_odds(h, a)
        assert "home_moneyline" in result
        assert "away_moneyline" in result
        assert "spread_line" in result
        assert "total_line" in result
        assert isinstance(result["home_moneyline"], int)
        assert isinstance(result["total_line"], float)

    def test_none_standings(self):
        result = generate_game_odds(None, None)
        assert "home_moneyline" in result


# ---------------------------------------------------------------------------
# generate_all_upcoming_odds (integration)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGenerateAllUpcomingOdds:
    def test_generates_odds_for_scheduled_games(self):
        team1 = TeamFactory()
        team2 = TeamFactory()
        GameFactory(
            home_team=team1,
            away_team=team2,
            status=GameStatus.SCHEDULED,
            season=2026,
        )
        StandingFactory(team=team1, season=2026)
        StandingFactory(team=team2, season=2026)

        results = generate_all_upcoming_odds(season=2026)
        assert len(results) == 1
        assert "home_moneyline" in results[0]

    def test_skips_non_scheduled_games(self):
        team1 = TeamFactory()
        team2 = TeamFactory()
        GameFactory(
            home_team=team1,
            away_team=team2,
            status=GameStatus.FINAL,
            season=2026,
        )

        results = generate_all_upcoming_odds(season=2026)
        assert len(results) == 0
