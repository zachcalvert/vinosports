"""Tests for the algorithmic odds engine."""

from unittest.mock import MagicMock

import pytest

from nba.betting.odds_engine import (
    MAX_ML,
    MAX_TOTAL,
    MIN_ML,
    MIN_TOTAL,
    STANDARD_JUICE,
    _moneyline,
    _parse_record,
    _probability_to_american,
    _spread,
    _team_strength,
    _total,
    _win_probability,
    generate_all_upcoming_odds,
    generate_game_odds,
)
from nba.games.models import GameStatus
from nba.tests.factories import GameFactory, StandingFactory, TeamFactory

# ---------------------------------------------------------------------------
# _parse_record
# ---------------------------------------------------------------------------


class TestParseRecord:
    def test_normal(self):
        assert _parse_record("25-10") == (25, 10)

    def test_empty(self):
        assert _parse_record("") == (0, 0)

    def test_bad_format(self):
        assert _parse_record("abc") == (0, 0)

    def test_none(self):
        assert _parse_record(None) == (0, 0)


# ---------------------------------------------------------------------------
# _team_strength
# ---------------------------------------------------------------------------


class TestTeamStrength:
    def test_high_rank_high_winpct(self):
        standing = MagicMock()
        standing.win_pct = 0.800
        standing.conference_rank = 1
        strength = _team_strength(standing)
        assert strength > 0.7

    def test_low_rank_low_winpct(self):
        standing = MagicMock()
        standing.win_pct = 0.200
        standing.conference_rank = 15
        strength = _team_strength(standing)
        assert strength < 0.2

    def test_fallback_on_none_winpct(self):
        standing = MagicMock()
        standing.win_pct = None
        standing.conference_rank = 8
        strength = _team_strength(standing)
        # Should use FALLBACK_WIN_PCT
        assert strength > 0


# ---------------------------------------------------------------------------
# _win_probability
# ---------------------------------------------------------------------------


class TestWinProbability:
    def test_equal_teams(self):
        h = MagicMock(win_pct=0.500, conference_rank=8, home_record="", away_record="")
        a = MagicMock(win_pct=0.500, conference_rank=8, home_record="", away_record="")
        p = _win_probability(h, a)
        # Home court advantage should push slightly above 0.5
        assert p > 0.5

    def test_strong_home_team(self):
        h = MagicMock(
            win_pct=0.800, conference_rank=1, home_record="30-5", away_record=""
        )
        a = MagicMock(
            win_pct=0.300, conference_rank=13, home_record="", away_record="10-20"
        )
        p = _win_probability(h, a)
        assert p > 0.6

    def test_clamped_to_range(self):
        h = MagicMock(
            win_pct=0.950, conference_rank=1, home_record="40-0", away_record=""
        )
        a = MagicMock(
            win_pct=0.050, conference_rank=15, home_record="", away_record="0-40"
        )
        p = _win_probability(h, a)
        assert 0.05 <= p <= 0.95

    def test_none_standings(self):
        p = _win_probability(None, None)
        # Should return ~0.5 (both fallback, plus home court)
        assert 0.45 <= p <= 0.55


# ---------------------------------------------------------------------------
# _probability_to_american
# ---------------------------------------------------------------------------


class TestProbabilityToAmerican:
    def test_coin_flip(self):
        odds = _probability_to_american(0.5)
        assert odds == 100  # decimal 2.0 → +100

    def test_heavy_favorite(self):
        odds = _probability_to_american(0.8)
        assert odds < 0

    def test_underdog(self):
        odds = _probability_to_american(0.25)
        assert odds > 0

    def test_edge_zero(self):
        odds = _probability_to_american(0.0)
        assert odds == -110  # fallback

    def test_edge_one(self):
        odds = _probability_to_american(1.0)
        assert odds == -110  # fallback


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
        assert spread_line < 0  # negative = home favored
        assert home_juice == STANDARD_JUICE
        assert away_juice == STANDARD_JUICE

    def test_even_game(self):
        spread_line, _, _ = _spread(0.5)
        assert spread_line == 0.0

    def test_away_favored(self):
        spread_line, _, _ = _spread(0.3)
        assert spread_line > 0


# ---------------------------------------------------------------------------
# _total
# ---------------------------------------------------------------------------


class TestTotal:
    def test_within_bounds(self):
        h = MagicMock(win_pct=0.600, conference_rank=3)
        a = MagicMock(win_pct=0.600, conference_rank=3)
        total_line, over, under = _total(h, a)
        assert MIN_TOTAL <= total_line <= MAX_TOTAL
        assert over == STANDARD_JUICE
        assert under == STANDARD_JUICE

    def test_none_standings(self):
        total_line, _, _ = _total(None, None)
        assert MIN_TOTAL <= total_line <= MAX_TOTAL


# ---------------------------------------------------------------------------
# generate_game_odds
# ---------------------------------------------------------------------------


class TestGenerateGameOdds:
    def test_returns_all_fields(self):
        h = MagicMock(
            win_pct=0.600, conference_rank=3, home_record="25-10", away_record=""
        )
        a = MagicMock(
            win_pct=0.400, conference_rank=10, home_record="", away_record="10-20"
        )
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
