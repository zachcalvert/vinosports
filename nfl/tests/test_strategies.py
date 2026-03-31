"""Tests for NFL bot betting strategies."""

from decimal import Decimal
from unittest.mock import MagicMock

from nfl.bots.strategies import (
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
    ValueHunterStrategy,
)
from vinosports.bots.models import StrategyType


def _make_profile(
    strategy_type="frontrunner",
    risk_multiplier=1.0,
    max_daily_bets=5,
    nfl_team_abbr="",
):
    p = MagicMock()
    p.strategy_type = strategy_type
    p.risk_multiplier = risk_multiplier
    p.max_daily_bets = max_daily_bets
    p.nfl_team_abbr = nfl_team_abbr
    return p


def _make_odds(
    game_id=1,
    home_ml=-150,
    away_ml=130,
    spread_line=-3.0,
    spread_home=-110,
    spread_away=-110,
    total_line=44.5,
    over_odds=-110,
    under_odds=-110,
    home_team_id=100,
    away_team_id=200,
):
    """Create a mock Odds object with NFL-typical defaults."""
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
        assert s._stake_amount(0.05) == Decimal("100.00")

    def test_minimum_stake(self):
        profile = _make_profile(risk_multiplier=0.01)
        s = FrontrunnerStrategy(profile, Decimal("100.00"))
        assert s._stake_amount(0.05) == Decimal("5.00")

    def test_capped_at_balance(self):
        profile = _make_profile(risk_multiplier=100.0)
        s = FrontrunnerStrategy(profile, Decimal("50.00"))
        assert s._stake_amount(0.50) == Decimal("50.00")


# ---------------------------------------------------------------------------
# FrontrunnerStrategy — NFL threshold: ≤ -130 (tighter than NBA's -150)
# ---------------------------------------------------------------------------


class TestFrontrunnerStrategy:
    def test_picks_heavy_home_favorite(self):
        profile = _make_profile()
        s = FrontrunnerStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=-200, away_ml=170)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "HOME"

    def test_picks_at_nfl_threshold(self):
        """NFL-specific: -130 qualifies (NBA would skip this)."""
        profile = _make_profile()
        s = FrontrunnerStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=-130, away_ml=110)]
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
        """Odds of -120 are too close for frontrunner."""
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
# UnderdogStrategy — NFL threshold: ≥ +130 (lower than NBA's +150)
# ---------------------------------------------------------------------------


class TestUnderdogStrategy:
    def test_picks_home_underdog(self):
        profile = _make_profile()
        s = UnderdogStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=200, away_ml=-250)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "HOME"

    def test_picks_at_nfl_threshold(self):
        """NFL-specific: +130 qualifies (NBA would skip this)."""
        profile = _make_profile()
        s = UnderdogStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(home_ml=130, away_ml=-150)]
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
# SpreadSharkStrategy — NFL key numbers (3, 7, 10)
# ---------------------------------------------------------------------------


class TestSpreadSharkStrategy:
    def test_picks_key_number_3(self):
        """Spread at -3 (key number) should be picked."""
        profile = _make_profile()
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=-3.0)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].market == "SPREAD"
        assert picks[0].selection == "HOME"

    def test_picks_key_number_7(self):
        """Spread at -7 (key number) should be picked."""
        profile = _make_profile()
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=-7.0)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "HOME"

    def test_picks_key_number_10(self):
        """Spread at +10 (away favored key number) should pick away."""
        profile = _make_profile()
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=10.0)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "AWAY"

    def test_picks_non_key_in_range(self):
        """Non-key number spread in home range -1 to -7 is still picked."""
        profile = _make_profile()
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=-5.0)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "HOME"

    def test_prioritizes_key_numbers(self):
        """Key number picks should come before non-key picks."""
        profile = _make_profile(max_daily_bets=1)
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [
            _make_odds(game_id=1, spread_line=-5.0),  # Non-key
            _make_odds(game_id=2, spread_line=-3.0),  # Key number
        ]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].line == -3.0  # Key number was prioritized

    def test_skips_null_spread(self):
        profile = _make_profile()
        s = SpreadSharkStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=None, spread_home=None)]
        picks = s.pick_bets(odds)
        assert len(picks) == 0


# ---------------------------------------------------------------------------
# ParlayStrategy — 3-4 legs, mixed markets
# ---------------------------------------------------------------------------


class TestParlayStrategy:
    def test_returns_parlay_instruction(self):
        profile = _make_profile()
        s = ParlayStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(game_id=i) for i in range(6)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert isinstance(picks[0], ParlayInstruction)
        assert 3 <= len(picks[0].legs) <= 4

    def test_returns_empty_with_fewer_than_3_games(self):
        profile = _make_profile()
        s = ParlayStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(game_id=1), _make_odds(game_id=2)]
        picks = s.pick_bets(odds)
        assert picks == []

    def test_no_duplicate_games_in_legs(self):
        """Each leg should be from a different game."""
        profile = _make_profile()
        s = ParlayStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(game_id=i) for i in range(6)]
        picks = s.pick_bets(odds)
        game_ids = [leg.game_id for leg in picks[0].legs]
        assert len(game_ids) == len(set(game_ids))

    def test_leg_stakes_are_zero(self):
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
# HomerStrategy — bets own team SPREAD (NFL-specific)
# ---------------------------------------------------------------------------


class TestHomerStrategy:
    def test_bets_home_spread_for_favorite_team(self):
        """Homer bets spread (not ML) when team is home."""
        profile = _make_profile(nfl_team_abbr="KC")
        s = HomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 100
        odds = [_make_odds(home_team_id=100, away_team_id=200, spread_line=-3.0)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].market == "SPREAD"
        assert picks[0].selection == "HOME"

    def test_bets_away_spread_for_favorite_team(self):
        """Homer bets spread when team is away."""
        profile = _make_profile(nfl_team_abbr="KC")
        s = HomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 200
        odds = [_make_odds(home_team_id=100, away_team_id=200, spread_line=-3.0)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].market == "SPREAD"
        assert picks[0].selection == "AWAY"

    def test_falls_back_to_moneyline(self):
        """If no spread available, homer falls back to ML."""
        profile = _make_profile(nfl_team_abbr="KC")
        s = HomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 100
        odds = [
            _make_odds(
                home_team_id=100,
                away_team_id=200,
                spread_line=None,
                spread_home=None,
                spread_away=None,
                home_ml=-150,
            )
        ]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].market == "MONEYLINE"

    def test_no_favorite_team_returns_empty(self):
        profile = _make_profile(nfl_team_abbr="")
        s = HomerStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds()]
        picks = s.pick_bets(odds)
        assert picks == []

    def test_skips_games_without_favorite(self):
        profile = _make_profile(nfl_team_abbr="KC")
        s = HomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 999
        odds = [_make_odds(home_team_id=100, away_team_id=200)]
        picks = s.pick_bets(odds)
        assert picks == []


# ---------------------------------------------------------------------------
# AntiHomerStrategy — bets against favorite team
# ---------------------------------------------------------------------------


class TestAntiHomerStrategy:
    def test_bets_against_home_favorite(self):
        profile = _make_profile(nfl_team_abbr="CLE")
        s = AntiHomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 100
        odds = [_make_odds(home_team_id=100, away_team_id=200)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "AWAY"

    def test_bets_against_away_favorite(self):
        profile = _make_profile(nfl_team_abbr="CLE")
        s = AntiHomerStrategy(profile, Decimal("1000.00"))
        s._team_id_cache = 200
        odds = [_make_odds(home_team_id=100, away_team_id=200)]
        picks = s.pick_bets(odds)
        assert len(picks) == 1
        assert picks[0].selection == "HOME"

    def test_no_favorite_returns_empty(self):
        profile = _make_profile(nfl_team_abbr="")
        s = AntiHomerStrategy(profile, Decimal("1000.00"))
        picks = s.pick_bets([_make_odds()])
        assert picks == []


# ---------------------------------------------------------------------------
# ValueHunterStrategy — NFL-specific value hunting
# ---------------------------------------------------------------------------


class TestValueHunterStrategy:
    def test_picks_spread_adjacent_to_key_number(self):
        """Spread at -2.5 (hook next to 3) should be a value pick."""
        profile = _make_profile()
        s = ValueHunterStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=-2.5)]
        picks = s.pick_bets(odds)
        spread_picks = [p for p in picks if p.market == "SPREAD"]
        assert len(spread_picks) == 1
        assert spread_picks[0].selection == "AWAY"  # Taking the underdog side

    def test_picks_under_on_high_total(self):
        """Total ≥47 should trigger UNDER bet."""
        profile = _make_profile()
        s = ValueHunterStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(total_line=48.5, spread_line=-5.0)]  # Non-hook spread
        picks = s.pick_bets(odds)
        total_picks = [p for p in picks if p.market == "TOTAL"]
        assert len(total_picks) == 1
        assert total_picks[0].selection == "UNDER"

    def test_picks_over_on_low_total(self):
        """Total ≤41 should trigger OVER bet."""
        profile = _make_profile()
        s = ValueHunterStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(total_line=39.5, spread_line=-5.0)]
        picks = s.pick_bets(odds)
        total_picks = [p for p in picks if p.market == "TOTAL"]
        assert len(total_picks) == 1
        assert total_picks[0].selection == "OVER"

    def test_skips_normal_total(self):
        """Total between 42-46 should not trigger a total bet."""
        profile = _make_profile()
        s = ValueHunterStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(total_line=44.5, spread_line=-5.0)]
        picks = s.pick_bets(odds)
        total_picks = [p for p in picks if p.market == "TOTAL"]
        assert len(total_picks) == 0

    def test_skips_non_hook_spread(self):
        """Spread at -5.0 is not a hook — should not generate a spread pick."""
        profile = _make_profile()
        s = ValueHunterStrategy(profile, Decimal("1000.00"))
        odds = [_make_odds(spread_line=-5.0, total_line=44.5)]
        picks = s.pick_bets(odds)
        spread_picks = [p for p in picks if p.market == "SPREAD"]
        assert len(spread_picks) == 0


# ---------------------------------------------------------------------------
# STRATEGY_MAP completeness
# ---------------------------------------------------------------------------


class TestStrategyMap:
    def test_all_nfl_strategy_types_mapped(self):
        """All NFL-relevant strategy types should be in STRATEGY_MAP."""
        nfl_strategies = [
            StrategyType.FRONTRUNNER,
            StrategyType.UNDERDOG,
            StrategyType.SPREAD_SHARK,
            StrategyType.PARLAY,
            StrategyType.TOTAL_GURU,
            StrategyType.CHAOS_AGENT,
            StrategyType.ALL_IN_ALICE,
            StrategyType.HOMER,
            StrategyType.ANTI_HOMER,
            StrategyType.VALUE_HUNTER,
        ]
        for choice_value in nfl_strategies:
            assert choice_value in STRATEGY_MAP, f"{choice_value} not in STRATEGY_MAP"

    def test_all_subclass_base_strategy(self):
        for cls in STRATEGY_MAP.values():
            assert issubclass(cls, BaseStrategy)
