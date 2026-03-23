"""
Bot betting strategies.

Each strategy receives available odds for today's games and the bot's balance,
then returns a list of BetInstruction or ParlayInstruction objects describing
what bets to place.
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from betting.models import BetSlip

from bots.models import BotProfile


@dataclass
class BetInstruction:
    game_id: int
    market: str
    selection: str
    line: float | None
    odds: int
    stake: Decimal


@dataclass
class ParlayInstruction:
    legs: list[BetInstruction] = field(default_factory=list)
    stake: Decimal = Decimal("0.00")


class BaseStrategy(ABC):
    def __init__(self, profile, balance: Decimal):
        self.profile = profile
        self.balance = balance

    @abstractmethod
    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        """Given a queryset of Odds for today's SCHEDULED games, return bet instructions."""
        ...

    def _stake_amount(self, base_pct: float = 0.05) -> Decimal:
        raw = (
            self.balance
            * Decimal(str(base_pct))
            * Decimal(str(self.profile.risk_multiplier))
        )
        return max(Decimal("5.00"), min(raw, self.balance)).quantize(Decimal("0.01"))

    def _cap(self, instructions: list) -> list:
        return instructions[: self.profile.max_daily_bets]


Market = BetSlip.Market
Selection = BetSlip.Selection


class FrontrunnerStrategy(BaseStrategy):
    """Bets moneyline favorites (odds <= -150)."""

    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        picks = []
        stake = self._stake_amount(0.05)
        for odds in odds_qs:
            if odds.home_moneyline is None or odds.away_moneyline is None:
                continue
            if odds.home_moneyline <= -150:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.HOME,
                        line=None,
                        odds=odds.home_moneyline,
                        stake=stake,
                    )
                )
            elif odds.away_moneyline <= -150:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.AWAY,
                        line=None,
                        odds=odds.away_moneyline,
                        stake=stake,
                    )
                )
        return self._cap(picks)


class UnderdogStrategy(BaseStrategy):
    """Bets moneyline underdogs (odds >= +150)."""

    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        picks = []
        stake = self._stake_amount(0.04)
        for odds in odds_qs:
            if odds.home_moneyline is None or odds.away_moneyline is None:
                continue
            if odds.home_moneyline >= 150:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.HOME,
                        line=None,
                        odds=odds.home_moneyline,
                        stake=stake,
                    )
                )
            elif odds.away_moneyline >= 150:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.AWAY,
                        line=None,
                        odds=odds.away_moneyline,
                        stake=stake,
                    )
                )
        return self._cap(picks)


class SpreadSharkStrategy(BaseStrategy):
    """Focuses on spread bets, prefers lines between -3 and -7."""

    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        picks = []
        stake = self._stake_amount(0.05)
        for odds in odds_qs:
            if odds.spread_line is None or odds.spread_home is None:
                continue
            if -7 <= odds.spread_line <= -3:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.SPREAD,
                        selection=Selection.HOME,
                        line=odds.spread_line,
                        odds=odds.spread_home,
                        stake=stake,
                    )
                )
            elif 3 <= odds.spread_line <= 7 and odds.spread_away is not None:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.SPREAD,
                        selection=Selection.AWAY,
                        line=-odds.spread_line,
                        odds=odds.spread_away,
                        stake=stake,
                    )
                )
        return self._cap(picks)


class ParlayStrategy(BaseStrategy):
    """Builds a single 4-5 leg moneyline parlay from favorites."""

    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        candidates = []
        for odds in odds_qs:
            if odds.home_moneyline is None or odds.away_moneyline is None:
                continue
            if odds.home_moneyline < odds.away_moneyline:
                candidates.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.HOME,
                        line=None,
                        odds=odds.home_moneyline,
                        stake=Decimal("0"),
                    )
                )
            else:
                candidates.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.AWAY,
                        line=None,
                        odds=odds.away_moneyline,
                        stake=Decimal("0"),
                    )
                )

        if len(candidates) < 3:
            return []

        leg_count = min(len(candidates), random.randint(4, 5))
        legs = random.sample(candidates, leg_count)
        stake = self._stake_amount(0.03)

        return [ParlayInstruction(legs=legs, stake=stake)]


class TotalGuruStrategy(BaseStrategy):
    """Always bets OVER on totals."""

    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        picks = []
        stake = self._stake_amount(0.04)
        for odds in odds_qs:
            if odds.total_line is None or odds.over_odds is None:
                continue
            picks.append(
                BetInstruction(
                    game_id=odds.game_id,
                    market=Market.TOTAL,
                    selection=Selection.OVER,
                    line=odds.total_line,
                    odds=odds.over_odds,
                    stake=stake,
                )
            )
        return self._cap(picks)


class ChaosAgentStrategy(BaseStrategy):
    """Random picks, random stakes, chaotic energy."""

    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        odds_list = list(odds_qs)
        if not odds_list:
            return []

        picks = []
        num_bets = random.randint(1, min(5, len(odds_list)))
        chosen = random.sample(odds_list, num_bets)

        for odds in chosen:
            pct = random.uniform(0.02, 0.15)
            stake = self._stake_amount(pct)
            market = random.choice([Market.MONEYLINE, Market.SPREAD, Market.TOTAL])

            if (
                market == Market.MONEYLINE
                and odds.home_moneyline
                and odds.away_moneyline
            ):
                sel = random.choice([Selection.HOME, Selection.AWAY])
                line_odds = (
                    odds.home_moneyline
                    if sel == Selection.HOME
                    else odds.away_moneyline
                )
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=market,
                        selection=sel,
                        line=None,
                        odds=line_odds,
                        stake=stake,
                    )
                )
            elif (
                market == Market.SPREAD
                and odds.spread_line
                and odds.spread_home
                and odds.spread_away
            ):
                sel = random.choice([Selection.HOME, Selection.AWAY])
                line_odds = (
                    odds.spread_home if sel == Selection.HOME else odds.spread_away
                )
                line = odds.spread_line if sel == Selection.HOME else -odds.spread_line
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=market,
                        selection=sel,
                        line=line,
                        odds=line_odds,
                        stake=stake,
                    )
                )
            elif (
                market == Market.TOTAL
                and odds.total_line
                and odds.over_odds
                and odds.under_odds
            ):
                sel = random.choice([Selection.OVER, Selection.UNDER])
                line_odds = odds.over_odds if sel == Selection.OVER else odds.under_odds
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=market,
                        selection=sel,
                        line=odds.total_line,
                        odds=line_odds,
                        stake=stake,
                    )
                )
            else:
                if odds.home_moneyline and odds.away_moneyline:
                    sel = random.choice([Selection.HOME, Selection.AWAY])
                    line_odds = (
                        odds.home_moneyline
                        if sel == Selection.HOME
                        else odds.away_moneyline
                    )
                    picks.append(
                        BetInstruction(
                            game_id=odds.game_id,
                            market=Market.MONEYLINE,
                            selection=sel,
                            line=None,
                            odds=line_odds,
                            stake=stake,
                        )
                    )

        return self._cap(picks)


class AllInAliceStrategy(BaseStrategy):
    """Max stakes on one game. YOLO."""

    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        odds_list = list(odds_qs)
        if not odds_list:
            return []

        odds = random.choice(odds_list)
        if odds.home_moneyline is None or odds.away_moneyline is None:
            return []

        pct = random.uniform(0.40, 0.60)
        stake = self._stake_amount(pct)

        if odds.home_moneyline < odds.away_moneyline:
            return [
                BetInstruction(
                    game_id=odds.game_id,
                    market=Market.MONEYLINE,
                    selection=Selection.HOME,
                    line=None,
                    odds=odds.home_moneyline,
                    stake=stake,
                )
            ]
        else:
            return [
                BetInstruction(
                    game_id=odds.game_id,
                    market=Market.MONEYLINE,
                    selection=Selection.AWAY,
                    line=None,
                    odds=odds.away_moneyline,
                    stake=stake,
                )
            ]


class HomerStrategy(BaseStrategy):
    """Always bets on the favorite team regardless of odds."""

    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        if not self.profile.favorite_team_id:
            return []

        picks = []
        stake = self._stake_amount(0.05)
        fav_team_id = self.profile.favorite_team_id

        for odds in odds_qs:
            game = odds.game
            if game.home_team_id == fav_team_id and odds.home_moneyline is not None:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.HOME,
                        line=None,
                        odds=odds.home_moneyline,
                        stake=stake,
                    )
                )
            elif game.away_team_id == fav_team_id and odds.away_moneyline is not None:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.AWAY,
                        line=None,
                        odds=odds.away_moneyline,
                        stake=stake,
                    )
                )

        return self._cap(picks)


class AntiHomerStrategy(BaseStrategy):
    """Bets AGAINST the favorite team every time. Revenge homer."""

    def pick_bets(self, odds_qs) -> list[BetInstruction | ParlayInstruction]:
        if not self.profile.favorite_team_id:
            return []

        picks = []
        stake = self._stake_amount(0.06)
        fav_team_id = self.profile.favorite_team_id

        for odds in odds_qs:
            game = odds.game
            if game.home_team_id == fav_team_id and odds.away_moneyline is not None:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.AWAY,
                        line=None,
                        odds=odds.away_moneyline,
                        stake=stake,
                    )
                )
            elif game.away_team_id == fav_team_id and odds.home_moneyline is not None:
                picks.append(
                    BetInstruction(
                        game_id=odds.game_id,
                        market=Market.MONEYLINE,
                        selection=Selection.HOME,
                        line=None,
                        odds=odds.home_moneyline,
                        stake=stake,
                    )
                )

        return self._cap(picks)


STRATEGY_MAP: dict[str, type[BaseStrategy]] = {
    BotProfile.StrategyType.FRONTRUNNER: FrontrunnerStrategy,
    BotProfile.StrategyType.UNDERDOG: UnderdogStrategy,
    BotProfile.StrategyType.SPREAD_SHARK: SpreadSharkStrategy,
    BotProfile.StrategyType.PARLAY: ParlayStrategy,
    BotProfile.StrategyType.TOTAL_GURU: TotalGuruStrategy,
    BotProfile.StrategyType.CHAOS_AGENT: ChaosAgentStrategy,
    BotProfile.StrategyType.ALL_IN_ALICE: AllInAliceStrategy,
    BotProfile.StrategyType.HOMER: HomerStrategy,
    BotProfile.StrategyType.ANTI_HOMER: AntiHomerStrategy,
}
