"""Tests for epl.bots.strategies — bot betting strategy implementations."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from epl.bots.strategies import (
    AllInAliceStrategy,
    ChaosAgentStrategy,
    DrawSpecialistStrategy,
    FrontrunnerStrategy,
    HomerBotStrategy,
    ParlayStrategy,
    UnderdogStrategy,
    ValueHunterStrategy,
    _clamp_stake,
)
from epl.tests.factories import MatchFactory, TeamFactory


def _make_odds_map(matches, odds_list):
    """Build odds_map from matches and per-match odds dicts."""
    return {m.pk: o for m, o in zip(matches, odds_list)}


# ---------------------------------------------------------------------------
# _clamp_stake helper
# ---------------------------------------------------------------------------


class TestClampStake:
    def test_clamps_below_floor(self):
        assert _clamp_stake(Decimal("0.50")) == Decimal("1.00")

    def test_clamps_above_ceiling(self):
        assert _clamp_stake(Decimal("20000")) == Decimal("10000.00")

    def test_passthrough_in_range(self):
        assert _clamp_stake(Decimal("50.00")) == Decimal("50.00")

    def test_custom_floor_and_ceiling(self):
        assert _clamp_stake(
            Decimal("0.01"), floor=Decimal("5.00"), ceiling=Decimal("100.00")
        ) == Decimal("5.00")


# ---------------------------------------------------------------------------
# FrontrunnerStrategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFrontrunnerStrategy:
    def test_picks_favorite_below_threshold(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.50"),
                "draw": Decimal("3.50"),
                "away_win": Decimal("5.00"),
            }
        }
        strategy = FrontrunnerStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].selection == "HOME_WIN"
        assert picks[0].match_id == match.pk

    def test_skips_when_no_clear_favorite(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("3.50"),
            }
        }
        strategy = FrontrunnerStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 0

    def test_skips_match_without_odds(self):
        match = MatchFactory()
        strategy = FrontrunnerStrategy()
        picks = strategy.pick_bets([match], {}, Decimal("1000.00"))
        assert len(picks) == 0

    def test_stake_within_range(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.40"),
                "draw": Decimal("4.00"),
                "away_win": Decimal("6.00"),
            }
        }
        strategy = FrontrunnerStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert Decimal("1.00") <= picks[0].stake <= Decimal("100.00")

    def test_selects_away_when_away_is_favorite(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("4.00"),
                "draw": Decimal("3.50"),
                "away_win": Decimal("1.60"),
            }
        }
        strategy = FrontrunnerStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].selection == "AWAY_WIN"


# ---------------------------------------------------------------------------
# UnderdogStrategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUnderdogStrategy:
    def test_picks_underdog_above_threshold(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.50"),
                "draw": Decimal("3.50"),
                "away_win": Decimal("5.00"),
            }
        }
        strategy = UnderdogStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].selection == "AWAY_WIN"

    def test_skips_when_no_underdog(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.80"),
                "draw": Decimal("2.50"),
                "away_win": Decimal("2.90"),
            }
        }
        strategy = UnderdogStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 0

    def test_stake_capped_at_50(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.30"),
                "draw": Decimal("4.00"),
                "away_win": Decimal("8.00"),
            }
        }
        strategy = UnderdogStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("10000.00"))
        assert len(picks) == 1
        assert picks[0].stake <= Decimal("50.00")

    def test_picks_draw_as_underdog_when_highest(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.50"),
                "draw": Decimal("6.00"),
                "away_win": Decimal("2.80"),
            }
        }
        strategy = UnderdogStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].selection == "DRAW"


# ---------------------------------------------------------------------------
# DrawSpecialistStrategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDrawSpecialistStrategy:
    def test_picks_draw_in_sweet_spot(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.20"),
                "away_win": Decimal("3.50"),
            }
        }
        strategy = DrawSpecialistStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].selection == "DRAW"

    def test_skips_draw_below_range(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("2.50"),
                "away_win": Decimal("3.50"),
            }
        }
        strategy = DrawSpecialistStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 0

    def test_skips_draw_above_range(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.50"),
                "draw": Decimal("4.00"),
                "away_win": Decimal("5.00"),
            }
        }
        strategy = DrawSpecialistStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 0

    def test_boundary_values_included(self):
        match1 = MatchFactory()
        match2 = MatchFactory()
        odds_map = {
            match1.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("2.80"),
                "away_win": Decimal("3.50"),
            },
            match2.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.80"),
                "away_win": Decimal("3.50"),
            },
        }
        strategy = DrawSpecialistStrategy()
        picks = strategy.pick_bets([match1, match2], odds_map, Decimal("1000.00"))
        assert len(picks) == 2


# ---------------------------------------------------------------------------
# ParlayStrategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestParlayStrategy:
    def test_pick_bets_returns_empty(self):
        match = MatchFactory()
        strategy = ParlayStrategy()
        assert strategy.pick_bets([match], {}, Decimal("1000.00")) == []

    def test_picks_parlay_with_enough_candidates(self):
        matches = [MatchFactory() for _ in range(5)]
        odds_map = {
            m.pk: {
                "home_win": Decimal("1.80"),
                "draw": Decimal("3.50"),
                "away_win": Decimal("4.00"),
            }
            for m in matches
        }
        strategy = ParlayStrategy()
        parlays = strategy.pick_parlays(matches, odds_map, Decimal("1000.00"))
        assert len(parlays) == 1
        assert 3 <= len(parlays[0].legs) <= 5

    def test_returns_empty_when_not_enough_legs(self):
        matches = [MatchFactory(), MatchFactory()]
        # Odds outside the 1.40-2.50 range
        odds_map = {
            m.pk: {
                "home_win": Decimal("3.00"),
                "draw": Decimal("3.50"),
                "away_win": Decimal("4.00"),
            }
            for m in matches
        }
        strategy = ParlayStrategy()
        parlays = strategy.pick_parlays(matches, odds_map, Decimal("1000.00"))
        assert parlays == []

    def test_one_candidate_per_match(self):
        """Even if multiple selections qualify per match, only one is taken."""
        matches = [MatchFactory() for _ in range(4)]
        odds_map = {
            m.pk: {
                "home_win": Decimal("1.50"),
                "draw": Decimal("2.00"),
                "away_win": Decimal("1.80"),
            }
            for m in matches
        }
        strategy = ParlayStrategy()
        parlays = strategy.pick_parlays(matches, odds_map, Decimal("1000.00"))
        assert len(parlays) == 1
        match_ids = [leg["match_id"] for leg in parlays[0].legs]
        # Each match should appear at most once
        assert len(match_ids) == len(set(match_ids))


# ---------------------------------------------------------------------------
# ValueHunterStrategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestValueHunterStrategy:
    def test_picks_when_spread_above_threshold(self):
        match = MatchFactory()
        odds_map = {
            "_full": {
                match.pk: [
                    {
                        "home_win": Decimal("2.00"),
                        "draw": Decimal("3.00"),
                        "away_win": Decimal("3.50"),
                    },
                    {
                        "home_win": Decimal("2.50"),
                        "draw": Decimal("3.00"),
                        "away_win": Decimal("3.50"),
                    },
                ]
            }
        }
        strategy = ValueHunterStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].selection == "HOME_WIN"  # 0.50 spread on home_win

    def test_skips_when_spread_below_threshold(self):
        match = MatchFactory()
        odds_map = {
            "_full": {
                match.pk: [
                    {
                        "home_win": Decimal("2.00"),
                        "draw": Decimal("3.00"),
                        "away_win": Decimal("3.50"),
                    },
                    {
                        "home_win": Decimal("2.10"),
                        "draw": Decimal("3.05"),
                        "away_win": Decimal("3.55"),
                    },
                ]
            }
        }
        strategy = ValueHunterStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 0

    def test_skips_when_single_bookmaker(self):
        match = MatchFactory()
        odds_map = {
            "_full": {
                match.pk: [
                    {
                        "home_win": Decimal("2.00"),
                        "draw": Decimal("3.00"),
                        "away_win": Decimal("3.50"),
                    },
                ]
            }
        }
        strategy = ValueHunterStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 0

    def test_skips_when_no_full_odds(self):
        match = MatchFactory()
        strategy = ValueHunterStrategy()
        picks = strategy.pick_bets([match], {}, Decimal("1000.00"))
        assert len(picks) == 0


# ---------------------------------------------------------------------------
# HomerBotStrategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHomerBotStrategy:
    def test_bets_home_win_when_team_is_home(self):
        team = TeamFactory()
        match = MatchFactory(home_team=team)
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("3.50"),
            }
        }
        strategy = HomerBotStrategy(team_id=team.pk)
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].selection == "HOME_WIN"

    def test_bets_away_win_when_team_is_away_and_not_big_underdog(self):
        team = TeamFactory()
        match = MatchFactory(away_team=team)
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("3.00"),
            }
        }
        strategy = HomerBotStrategy(team_id=team.pk)
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].selection == "AWAY_WIN"

    def test_bets_draw_when_team_is_big_away_underdog(self):
        team = TeamFactory()
        match = MatchFactory(away_team=team)
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.50"),
                "draw": Decimal("3.20"),
                "away_win": Decimal("4.00"),
            }
        }
        strategy = HomerBotStrategy(team_id=team.pk)
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].selection == "DRAW"

    def test_skips_matches_without_team(self):
        team = TeamFactory()
        match = MatchFactory()  # Different teams
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("3.50"),
            }
        }
        strategy = HomerBotStrategy(team_id=team.pk)
        picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 0

    def test_stake_capped_at_150(self):
        team = TeamFactory()
        match = MatchFactory(home_team=team)
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("3.50"),
            }
        }
        strategy = HomerBotStrategy(team_id=team.pk)
        picks = strategy.pick_bets([match], odds_map, Decimal("10000.00"))
        assert len(picks) == 1
        assert picks[0].stake <= Decimal("150.00")


# ---------------------------------------------------------------------------
# AllInAliceStrategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAllInAliceStrategy:
    def test_picks_single_strongest_favorite(self):
        match1 = MatchFactory()
        match2 = MatchFactory()
        odds_map = {
            match1.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("3.50"),
            },
            match2.pk: {
                "home_win": Decimal("1.20"),
                "draw": Decimal("5.00"),
                "away_win": Decimal("10.00"),
            },
        }
        strategy = AllInAliceStrategy()
        picks = strategy.pick_bets([match1, match2], odds_map, Decimal("1000.00"))
        assert len(picks) == 1
        assert picks[0].match_id == match2.pk
        assert picks[0].selection == "HOME_WIN"

    def test_returns_empty_when_no_matches(self):
        strategy = AllInAliceStrategy()
        picks = strategy.pick_bets([], {}, Decimal("1000.00"))
        assert picks == []

    def test_stakes_full_balance(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.50"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("5.00"),
            }
        }
        strategy = AllInAliceStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("500.00"))
        assert len(picks) == 1
        assert picks[0].stake == Decimal("500.00")

    def test_stake_capped_at_10000(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("1.50"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("5.00"),
            }
        }
        strategy = AllInAliceStrategy()
        picks = strategy.pick_bets([match], odds_map, Decimal("50000.00"))
        assert len(picks) == 1
        assert picks[0].stake == Decimal("10000.00")


# ---------------------------------------------------------------------------
# ChaosAgentStrategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChaosAgentStrategy:
    def test_places_bets_on_matches_with_odds(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("3.50"),
            }
        }
        strategy = ChaosAgentStrategy()
        # Run many times — at least one should produce a pick
        found_pick = False
        for _ in range(50):
            picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
            if len(picks) > 0:
                found_pick = True
                assert picks[0].selection in ("HOME_WIN", "DRAW", "AWAY_WIN")
                break
        assert found_pick, "ChaosAgent should eventually place a bet"

    def test_skips_match_by_coin_flip(self):
        """With random < 0.5 the coin flip triggers continue (skip)."""
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("3.50"),
            }
        }
        strategy = ChaosAgentStrategy()
        # random() < 0.5 means the match is skipped
        with patch("epl.bots.strategies.random.random", return_value=0.2):
            picks = strategy.pick_bets([match], odds_map, Decimal("1000.00"))
        assert len(picks) == 0

    def test_skips_match_without_odds(self):
        match = MatchFactory()
        strategy = ChaosAgentStrategy()
        picks = strategy.pick_bets([match], {}, Decimal("1000.00"))
        assert len(picks) == 0

    def test_respects_minimum_stake(self):
        match = MatchFactory()
        odds_map = {
            match.pk: {
                "home_win": Decimal("2.00"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("3.50"),
            }
        }
        strategy = ChaosAgentStrategy()
        # Very low balance — stake < 1.00 should be skipped
        with patch("epl.bots.strategies.random.random", return_value=0.3):
            with patch("epl.bots.strategies.random.randint", return_value=5):
                picks = strategy.pick_bets([match], odds_map, Decimal("0.50"))
        # Stake min(5, 0.50) = 0.50 < 1.00, so skipped
        assert len(picks) == 0
