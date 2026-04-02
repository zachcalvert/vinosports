"""Bot betting strategies.

Each strategy implements pick_bets() and optionally pick_parlays() to decide
what bets a bot should place given the available matches and odds.
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class BetPick:
    match_id: int
    selection: str  # "HOME_WIN" / "DRAW" / "AWAY_WIN"
    stake: Decimal


@dataclass
class ParlayPick:
    legs: list = field(default_factory=list)  # [{"match_id": int, "selection": str}]
    stake: Decimal = Decimal("0")


def _clamp_stake(stake, floor=Decimal("1.00"), ceiling=Decimal("100000000.00")):
    return max(floor, min(stake, ceiling))


class BotStrategy(ABC):
    """Base class for bot betting strategies."""

    @abstractmethod
    def pick_bets(self, available_matches, odds_map, balance) -> list[BetPick]:
        """Return single bet picks.

        Args:
            available_matches: QuerySet of bettable Match objects (not yet bet on).
            odds_map: {match_id: {"home_win": Decimal, "draw": Decimal, "away_win": Decimal}}
            balance: Current bot balance as Decimal.
        """
        ...

    def pick_parlays(self, available_matches, odds_map, balance) -> list[ParlayPick]:
        """Return parlay picks. Default: none."""
        return []


class FrontrunnerStrategy(BotStrategy):
    """Always bets on the favorite (lowest odds outcome).

    Skips matches where no outcome has odds below 1.80 (no clear favorite).
    Moderate stakes: 5-15% of balance, max 100.
    """

    FAVORITE_THRESHOLD = Decimal("1.80")

    def pick_bets(self, available_matches, odds_map, balance):
        picks = []
        for match in available_matches:
            odds = odds_map.get(match.pk)
            if not odds:
                continue

            outcomes = {
                "HOME_WIN": odds["home_win"],
                "DRAW": odds["draw"],
                "AWAY_WIN": odds["away_win"],
            }
            favorite = min(outcomes, key=outcomes.get)
            favorite_odds = outcomes[favorite]

            if favorite_odds >= self.FAVORITE_THRESHOLD:
                continue  # No clear favorite

            pct = Decimal(str(random.uniform(0.05, 0.15)))
            stake = _clamp_stake(
                (balance * pct).quantize(Decimal("0.01")), ceiling=Decimal("100")
            )

            picks.append(BetPick(match_id=match.pk, selection=favorite, stake=stake))

        return picks


class UnderdogStrategy(BotStrategy):
    """Always bets on the underdog (highest odds outcome).

    Skips matches where no outcome has odds >= 3.00 (no clear underdog).
    Conservative stakes: 2-5% of balance, max 50.
    """

    UNDERDOG_THRESHOLD = Decimal("3.00")

    def pick_bets(self, available_matches, odds_map, balance):
        picks = []
        for match in available_matches:
            odds = odds_map.get(match.pk)
            if not odds:
                continue

            outcomes = {
                "HOME_WIN": odds["home_win"],
                "DRAW": odds["draw"],
                "AWAY_WIN": odds["away_win"],
            }
            underdog = max(outcomes, key=outcomes.get)
            underdog_odds = outcomes[underdog]

            if underdog_odds < self.UNDERDOG_THRESHOLD:
                continue

            pct = Decimal(str(random.uniform(0.02, 0.05)))
            stake = _clamp_stake(
                (balance * pct).quantize(Decimal("0.01")), ceiling=Decimal("50")
            )

            picks.append(BetPick(match_id=match.pk, selection=underdog, stake=stake))

        return picks


class ParlayStrategy(BotStrategy):
    """Picks one parlay per matchweek with 3-5 legs in the 1.40-2.50 odds range.

    Stake: 3-8% of balance, max 30.
    """

    MIN_ODDS = Decimal("1.40")
    MAX_ODDS = Decimal("2.50")
    MIN_LEGS = 3
    MAX_LEGS = 5

    def pick_bets(self, available_matches, odds_map, balance):
        return []  # ParlayBot only places parlays

    def pick_parlays(self, available_matches, odds_map, balance):
        candidates = []
        for match in available_matches:
            odds = odds_map.get(match.pk)
            if not odds:
                continue

            for selection, key in [
                ("HOME_WIN", "home_win"),
                ("DRAW", "draw"),
                ("AWAY_WIN", "away_win"),
            ]:
                val = odds[key]
                if self.MIN_ODDS <= val <= self.MAX_ODDS:
                    candidates.append(
                        {"match_id": match.pk, "selection": selection, "odds": val}
                    )
                    break  # One candidate per match

        if len(candidates) < self.MIN_LEGS:
            return []

        num_legs = min(random.randint(self.MIN_LEGS, self.MAX_LEGS), len(candidates))
        legs = random.sample(candidates, num_legs)

        pct = Decimal(str(random.uniform(0.03, 0.08)))
        stake = _clamp_stake(
            (balance * pct).quantize(Decimal("0.01")), ceiling=Decimal("30")
        )

        return [
            ParlayPick(
                legs=[
                    {"match_id": lg["match_id"], "selection": lg["selection"]}
                    for lg in legs
                ],
                stake=stake,
            )
        ]


class DrawSpecialistStrategy(BotStrategy):
    """Only bets on draws, and only when draw odds are 2.80-3.80 (the sweet spot).

    Stake: 5-10% of balance, max 75.
    """

    MIN_DRAW_ODDS = Decimal("2.80")
    MAX_DRAW_ODDS = Decimal("3.80")

    def pick_bets(self, available_matches, odds_map, balance):
        picks = []
        for match in available_matches:
            odds = odds_map.get(match.pk)
            if not odds:
                continue

            draw_odds = odds["draw"]
            if not (self.MIN_DRAW_ODDS <= draw_odds <= self.MAX_DRAW_ODDS):
                continue

            pct = Decimal(str(random.uniform(0.05, 0.10)))
            stake = _clamp_stake(
                (balance * pct).quantize(Decimal("0.01")), ceiling=Decimal("75")
            )

            picks.append(BetPick(match_id=match.pk, selection="DRAW", stake=stake))

        return picks


class ValueHunterStrategy(BotStrategy):
    """Bets where the bookmaker odds spread is largest (> 0.30 gap).

    Requires full per-bookmaker odds (passed via odds_map["_full"][match_id]).
    Skips matches where full data is unavailable or only one bookmaker is present.
    Stake: 8-12% of balance, max 80.
    """

    MIN_SPREAD = Decimal("0.30")

    def pick_bets(self, available_matches, odds_map, balance):
        full_odds = odds_map.get("_full", {})
        picks = []

        for match in available_matches:
            match_full = full_odds.get(match.pk)
            if not match_full or len(match_full) < 2:
                continue

            best_spread = Decimal("0")
            best_selection = None

            for key, selection in [
                ("home_win", "HOME_WIN"),
                ("draw", "DRAW"),
                ("away_win", "AWAY_WIN"),
            ]:
                values = [row[key] for row in match_full]
                spread = max(values) - min(values)
                if spread > best_spread:
                    best_spread = spread
                    best_selection = selection

            if best_spread < self.MIN_SPREAD or best_selection is None:
                continue

            pct = Decimal(str(random.uniform(0.08, 0.12)))
            stake = _clamp_stake(
                (balance * pct).quantize(Decimal("0.01")), ceiling=Decimal("80")
            )

            picks.append(
                BetPick(match_id=match.pk, selection=best_selection, stake=stake)
            )

        return picks


class HomerBotStrategy(BotStrategy):
    """Bets exclusively on one team, every match they play.

    - Home: always HOME_WIN, 15–25% of balance, max 150.
    - Away, not a big underdog (away_win odds < draw_underdog_threshold): AWAY_WIN, 10–20% of balance, max 150.
    - Away, big underdog (away_win odds >= draw_underdog_threshold): DRAW, 10–20% of balance, max 150.
    - Skips all matches where the supported team is not involved.
    - No odds ceiling — blind loyalty doesn't do expected-value calculations.
    """

    HOME_PCT = (0.15, 0.25)
    AWAY_PCT = (0.10, 0.20)
    MAX_STAKE = Decimal("15000")

    def __init__(
        self, team_id: int, draw_underdog_threshold: Decimal = Decimal("3.50")
    ):
        self.team_id = team_id
        self.draw_underdog_threshold = draw_underdog_threshold

    def pick_bets(self, available_matches, odds_map, balance):
        picks = []
        for match in available_matches:
            odds = odds_map.get(match.pk)
            if not odds:
                continue

            is_home = match.home_team_id == self.team_id
            is_away = match.away_team_id == self.team_id

            if not (is_home or is_away):
                continue

            if is_home:
                selection = "HOME_WIN"
                pct = Decimal(str(random.uniform(*self.HOME_PCT)))
            else:
                if odds["away_win"] >= self.draw_underdog_threshold:
                    selection = "DRAW"
                else:
                    selection = "AWAY_WIN"
                pct = Decimal(str(random.uniform(*self.AWAY_PCT)))

            stake = _clamp_stake(
                (balance * pct).quantize(Decimal("0.01")),
                ceiling=self.MAX_STAKE,
            )
            picks.append(BetPick(match_id=match.pk, selection=selection, stake=stake))

        return picks


class AllInAliceStrategy(BotStrategy):
    """Picks the single strongest favorite of the week and goes all in.

    One bet per run — the match with the lowest odds (most likely outcome).
    Stakes entire balance, capped at 10,000.
    """

    MAX_STAKE = Decimal("100000000")

    def pick_bets(self, available_matches, odds_map, balance):
        best_match_id = None
        best_selection = None
        best_odds = None

        for match in available_matches:
            odds = odds_map.get(match.pk)
            if not odds:
                continue

            outcomes = {
                "HOME_WIN": odds["home_win"],
                "DRAW": odds["draw"],
                "AWAY_WIN": odds["away_win"],
            }
            favorite = min(outcomes, key=outcomes.get)
            favorite_odds = outcomes[favorite]

            if best_odds is None or favorite_odds < best_odds:
                best_odds = favorite_odds
                best_selection = favorite
                best_match_id = match.pk

        if best_match_id is None:
            return []

        stake = _clamp_stake(balance, ceiling=self.MAX_STAKE)
        return [BetPick(match_id=best_match_id, selection=best_selection, stake=stake)]


class ChaosAgentStrategy(BotStrategy):
    """Random match, random selection, random stake. Pure chaos.

    50% chance of betting on each match. Stake: random 5-100.
    """

    SELECTIONS = ["HOME_WIN", "DRAW", "AWAY_WIN"]

    def pick_bets(self, available_matches, odds_map, balance):
        picks = []
        for match in available_matches:
            if match.pk not in odds_map:
                continue
            if random.random() < 0.5:
                continue

            selection = random.choice(self.SELECTIONS)
            stake = Decimal(str(random.randint(5, 100)))
            stake = min(stake, balance)

            if stake < Decimal("1.00"):
                continue

            picks.append(BetPick(match_id=match.pk, selection=selection, stake=stake))

        return picks
