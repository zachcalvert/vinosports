"""Tests for epl.betting.odds_engine — algorithmic 1X2 odds generation."""

from decimal import Decimal

import pytest

from epl.betting.odds_engine import (
    MAX_ODDS,
    MIN_ODDS,
    _clamp,
    _team_strength,
    generate_match_odds,
)

from .factories import StandingFactory

pytestmark = pytest.mark.django_db


class TestTeamStrength:
    def test_top_team(self):
        standing = StandingFactory(position=1, points=60, played=20)
        strength = _team_strength(standing)
        assert strength > Decimal("0.7")

    def test_bottom_team(self):
        standing = StandingFactory(position=20, points=10, played=20)
        strength = _team_strength(standing)
        assert strength < Decimal("0.3")

    def test_mid_table_team(self):
        standing = StandingFactory(position=10, points=30, played=20)
        strength = _team_strength(standing)
        assert Decimal("0.3") < strength < Decimal("0.7")


class TestClamp:
    def test_within_range_unchanged(self):
        assert _clamp(Decimal("3.50")) == Decimal("3.50")

    def test_below_min_clamped(self):
        assert _clamp(Decimal("0.50")) == MIN_ODDS

    def test_above_max_clamped(self):
        assert _clamp(Decimal("50.00")) == MAX_ODDS


class TestGenerateMatchOdds:
    def test_returns_three_outcomes(self):
        home = StandingFactory(position=3, points=50, played=20)
        away = StandingFactory(position=15, points=20, played=20)
        odds = generate_match_odds(home, away)
        assert "home_win" in odds
        assert "draw" in odds
        assert "away_win" in odds

    def test_odds_are_positive(self):
        home = StandingFactory(position=1, points=60, played=20)
        away = StandingFactory(position=20, points=10, played=20)
        odds = generate_match_odds(home, away)
        assert odds["home_win"] >= MIN_ODDS
        assert odds["draw"] >= MIN_ODDS
        assert odds["away_win"] >= MIN_ODDS

    def test_strong_home_team_has_lower_odds(self):
        home = StandingFactory(position=1, points=60, played=20)
        away = StandingFactory(position=18, points=15, played=20)
        odds = generate_match_odds(home, away)
        assert odds["home_win"] < odds["away_win"]

    def test_fallback_when_no_standings(self):
        odds = generate_match_odds(None, None)
        assert odds["home_win"] >= MIN_ODDS
        assert odds["draw"] >= MIN_ODDS
        assert odds["away_win"] >= MIN_ODDS

    def test_odds_clamped_to_range(self):
        home = StandingFactory(position=1, points=57, played=20)
        away = StandingFactory(position=20, points=5, played=20)
        odds = generate_match_odds(home, away)
        for key in ("home_win", "draw", "away_win"):
            assert MIN_ODDS <= odds[key] <= MAX_ODDS

    def test_even_teams_produce_close_odds(self):
        home = StandingFactory(position=10, points=30, played=20)
        away = StandingFactory(position=11, points=29, played=20)
        odds = generate_match_odds(home, away)
        # Home advantage means home_win should still be lower
        assert odds["home_win"] < odds["away_win"]
        # But gap should be modest
        assert abs(odds["home_win"] - odds["away_win"]) < Decimal("3.00")
