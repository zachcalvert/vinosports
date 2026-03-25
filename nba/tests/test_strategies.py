"""Tests for the 9 bot betting strategies."""

from decimal import Decimal
from unittest.mock import MagicMock

from nba.bots.strategies import (
    STRATEGY_MAP,
    AllInAliceStrategy,
    AntiHomerStrategy,
    BaseStrategy,
    BetInstruction,
    ChaosAgentStrategy,
    FrontrunnerStrategy,
    HomerStrategy,
    ParlayInstruction,
    ParlayStrategy,
    SpreadSharkStrategy,
    TotalGuruStrategy,
    UnderdogStrategy,
)
from vinosports.bots.models import StrategyType


def _make_profile(
    strategy_type="frontrunner",
    risk_multiplier=1.0,
    max_daily_bets=5,
    nba_team_abbr="",
):
    p = MagicMock()
    p.strategy_type = strategy_type
    p.risk_multiplier = risk_multiplier
    p.max_daily_bets = max_daily_bets
    p.nba_team_abbr = nba_team_abbr
    return p


def _make_odds(
    game_id=1,
    home_ml=-150,
    away_ml=130,
    spread_line=-3.5,
    spread_home=-110,
    spread_away=-110,
    total_line=222.5,
    over_odds=-110,
    under_odds=-110,
    home_team_id=100,
    away_team_id=200,
):
    """Create a mock Odds object."""
    odds = MagicMock()
    odds.game_id = game_id
    odds.home_moneyline = home_ml
    odds.away_moneyline = away_ml
    odds.spread_line = spread_line
    odds.spread_home = spread_home
    odds.spread_away = spread_away
    odds.total_line = total_line
    odds.over_odds = over_odds
    odds.under_odds = under_odds
    odds.game = MagicMock()
    odds.game.home_team_id = home_team_id
    odds.game.away_team_id = away_team_id
    return odds


# ---------------------------------------------------------------------------
# _stake_amount
# ---------------------------------------------------------------------------


class TestStakeAmount:
    def test_respects_risk_multiplier(self):
        profile = _make_profile(risk_multiplier=2.0)
        s = FrontrunnerStrategy(profile, Decimal("1000.00"))
        # base=5%, risk=2.0 → 10% of 1000 = 100
        assert s._stake_amount(0.05) == Decimal("100.00")

    def test_minimum_stake(self):
        profile = _make_profile(risk_multiplier=0.01)
        s = FrontrunnerStrategy(profile, Decimal("100.00"))
        # Would be 100 * 0.05 * 0.01 = 0.05, but min is $5
        assert s._stake_amount(0.05) == Decimal("5.00")

    def test_capped_at_balance(self):
        profile = _make_profile(risk_multiplier=100.0)
        s = FrontrunnerStrategy(profile, Decimal("50.00"))
        assert s._stake_amount(0.50) == Decimal("50.00")


# ---------------------------------------------------------------------------
# FrontrunnerStrategy — favorites (odds ≤ -150)
# ---------------------------------------------------------------------------


class TestFrontrunnerStrategy:
    def test_picks_heavy_home_favorite(self):
        profile = _make_profile()
        s = FrontrunnerStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=-200, away_ml=170)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "HOME"

    def test_picks_heavy_away_favorite(self):
        profile = _make_profile()
        s = FrontrunnerStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=170, away_ml=-200)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "AWAY"

    def test_skips_non_favorites(self):
        profile = _make_profile()
        s = FrontrunnerStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=-120, away_ml=100)]
        picks = s.pick_bets(odds)
        assert len(picks) == 0

    def test_respects_max_daily_bets(self):
        profile = _make_profile(max_daily_bets=2)
        s = FrontrunnerStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(game_id=i, home_ml=-200) for i in range(5)]
        picks = s.pick_bets(odds)
        assert len(picks) == 2

    def test_skips_null_moneylines(self):
        profile = _make_profile()
        s = FrontrunnerStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=None, away_ml=None)]
        picks = s.pick_bets(odds)
        assert len(picks) == 0


# ---------------------------------------------------------------------------
# UnderdogStrategy — underdogs (odds ≥ +150)
# ---------------------------------------------------------------------------


class TestUnderdogStrategy:
    def test_picks_home_underdog(self):
        profile = _make_profile()
        s = UnderdogStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=200, away_ml=-250)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "HOME"

    def test_picks_away_underdog(self):
        profile = _make_profile()
        s = UnderdogStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=-250, away_ml=200)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "AWAY"

    def test_skips_when_no_underdogs(self):
        profile = _make_profile()
        s = UnderdogStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=-120, away_ml=100)]
        picks = s.pick_bets(odds)
        assert len(picks) == 0


# ---------------------------------------------------------------------------
# SpreadSharkStrategy — spreads between -3 and -7
# ---------------------------------------------------------------------------


class TestSpreadSharkStrategy:
    def test_picks_home_in_range(self):
        profile = _make_profile()
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=-5.0)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].market == "SPREAD"
        assert picks[0].selection == "HOME"

    def test_picks_away_in_range(self):
        profile = _make_profile()
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=5.0)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "AWAY"

    def test_skips_out_of_range(self):
        profile = _make_profile()
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=-1.5)]
        picks = s.pick_bets(odds)
        assert len(picks) == 0

    def test_skips_null_spread(self):
        profile = _make_profile()
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=None, spread_home=None)]
        picks = s.pick_bets(odds)
        assert len(picks) == 0


# ---------------------------------------------------------------------------
# ParlayStrategy — 4-5 leg moneyline parlays
# ---------------------------------------------------------------------------


class TestParlayStrategy:
    def test_returns_parlay_instruction(self):
        profile = _make_profile()
        s = ParlayStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(game_id=i) for i in range(6)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert isinstance(picks[0], ParlayInstruction)
        assert 4 <= len(picks[0].legs) <= 5

    def test_returns_empty_with_fewer_than_3_games(self):
        profile = _make_profile()
        s = ParlayStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(game_id=1), _make_odds(game_id=2)]
        picks = s.pick_bets(odds)
        assert picks == []

    def test_leg_stakes_are_zero(self):
        """Individual leg stakes should be 0 (stake is on the parlay)."""
        profile = _make_profile()
        s = ParlayStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(game_id=i) for i in range(5)]
        picks = s.pick_bets(odds)
        for leg in picks[0].legs:
            assert leg.stake == Decimal("0")


# ---------------------------------------------------------------------------
# TotalGuruStrategy — always bets OVER
# ---------------------------------------------------------------------------


class TestTotalGuruStrategy:
    def test_always_bets_over(self):
        profile = _make_profile()
        s = TotalGuruStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds()]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "OVER"
        assert picks[0].market == "TOTAL"

    def test_skips_null_total(self):
        profile = _make_profile()
        s = TotalGuruStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(total_line=None, over_odds=None)]
        picks = s.pick_bets(odds)
        assert len(picks) == 0


# ---------------------------------------------------------------------------
# ChaosAgentStrategy — random picks
# ---------------------------------------------------------------------------


class TestChaosAgentStrategy:
    def test_returns_bets_or_empty(self):
        """ChaosAgent should not crash and should return a list."""
        profile = _make_profile()
        s = ChaosAgentStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(game_id=i) for i in range(3)]
        picks = s.pick_bets(odds)
        assert isinstance(picks, list)
        assert len(picks) <= 5

    def test_empty_odds_returns_empty(self):
        profile = _make_profile()
        s = ChaosAgentStrategy(profile, Decimal("1000.00"))
        picks = s.pick_bets([])
        assert picks == []


# ---------------------------------------------------------------------------
# AllInAliceStrategy — max stakes, one game
# ---------------------------------------------------------------------------


class TestAllInAliceStrategy:
    def test_returns_single_bet(self):
        profile = _make_profile()
        s = AllInAliceStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds()]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert isinstance(picks[0], BetInstruction)

    def test_high_stake(self):
        """AllInAlice stakes 40-60% of balance."""
        profile = _make_profile(risk_multiplier=1.0)
        s = AllInAliceStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds()]
        picks = s.pick_bets(odds)
        assert picks[0].stake >= Decimal("5.00")

    def test_empty_odds(self):
        profile = _make_profile()
        s = AllInAliceStrategy(profile, Decimal("1000.00"))
        picks = s.pick_bets([])
        assert picks == []

    def test_null_moneylines(self):
        profile = _make_profile()
        s = AllInAliceStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=None, away_ml=None)]
        picks = s.pick_bets(odds)
        assert picks == []


# ---------------------------------------------------------------------------
# HomerStrategy — only bets on favorite_team
# ---------------------------------------------------------------------------


class TestHomerStrategy:
    def test_bets_home_for_favorite(self):
        profile = _make_profile(nba_team_abbr="TST")
        s = HomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 100  # Mock the team lookup
        odds = [_make_odds(home_team_id=100, away_team_id=200)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "HOME"

    def test_bets_away_for_favorite(self):
        profile = _make_profile(nba_team_abbr="TST")
        s = HomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 200  # Mock the team lookup
        odds = [_make_odds(home_team_id=100, away_team_id=200)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "AWAY"

    def test_no_favorite_team_returns_empty(self):
        profile = _make_profile(nba_team_abbr="")
        s = HomerStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds()]
        picks = s.pick_bets(odds)
        assert picks == []

    def test_skips_games_without_favorite(self):
        profile = _make_profile(nba_team_abbr="TST")
        s = HomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 999  # Mock — team not in this game
        odds = [_make_odds(home_team_id=100, away_team_id=200)]
        picks = s.pick_bets(odds)
        assert picks == []


# ---------------------------------------------------------------------------
# AntiHomerStrategy — bets against favorite team
# ---------------------------------------------------------------------------


class TestAntiHomerStrategy:
    def test_bets_against_home_favorite(self):
        profile = _make_profile(nba_team_abbr="TST")
        s = AntiHomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 100
        odds = [_make_odds(home_team_id=100, away_team_id=200)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "AWAY"

    def test_bets_against_away_favorite(self):
        profile = _make_profile(nba_team_abbr="TST")
        s = AntiHomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 200
        odds = [_make_odds(home_team_id=100, away_team_id=200)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "HOME"

    def test_no_favorite_returns_empty(self):
        profile = _make_profile(nba_team_abbr="")
        s = AntiHomerStrategy(profile, Decimal("1000.00"))
        picks = s.pick_bets([_make_odds()])
        assert picks == []


# ---------------------------------------------------------------------------
# STRATEGY_MAP completeness
# ---------------------------------------------------------------------------


class TestStrategyMap:
    def test_all_nba_strategy_types_mapped(self):
        """All NBA-relevant strategy types should be in STRATEGY_MAP."""
        nba_strategies = [
            StrategyType.FRONTRUNNER,
            StrategyType.UNDERDOG,
            StrategyType.SPREAD_SHARK,
            StrategyType.PARLAY,
            StrategyType.TOTAL_GURU,
            StrategyType.CHAOS_AGENT,
            StrategyType.ALL_IN_ALICE,
            StrategyType.HOMER,
            StrategyType.ANTI_HOMER,
        ]
        for choice_value in nba_strategies:
            assert choice_value in STRATEGY_MAP, f"{choice_value} not in STRATEGY_MAP"

    def test_all_subclass_base_strategy(self):
        for cls in STRATEGY_MAP.values():
            assert issubclass(cls, BaseStrategy)
