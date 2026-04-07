"""Bot betting strategies for World Cup.

World Cup uses decimal 1X2 odds (home win / draw / away win) only — no spread
or moneyline. Strategy calibration reflects the nature of international football:
draws are common (~25%), upsets are frequent, and home advantage is negligible
at a neutral-site tournament.

Each strategy receives available odds for upcoming matches and the bot's balance,
then returns a list of BetInstruction objects describing what bets to place.
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from vinosports.bots.models import StrategyType
from worldcup.betting.models import BetSlip

Selection = BetSlip.Selection


@dataclass
class BetInstruction:
    match_id: int
    selection: str  # BetSlip.Selection value
    odds: Decimal
    stake: Decimal


class BaseStrategy(ABC):
    def __init__(self, profile, balance: Decimal):
        self.profile = profile
        self.balance = balance

    @abstractmethod
    def pick_bets(self, odds_qs) -> list[BetInstruction]:
        """Given a queryset of Odds for upcoming SCHEDULED matches, return bet instructions."""
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


class FrontrunnerStrategy(BaseStrategy):
    """Bets on the match favourite — whichever side has the lower decimal odds."""

    def pick_bets(self, odds_qs) -> list[BetInstruction]:
        picks = []
        stake = self._stake_amount(0.05)
        for odds in odds_qs:
            if odds.home_win is None or odds.away_win is None:
                continue
            if odds.home_win < odds.away_win:
                picks.append(
                    BetInstruction(
                        match_id=odds.match_id,
                        selection=Selection.HOME_WIN,
                        odds=odds.home_win,
                        stake=stake,
                    )
                )
            elif odds.away_win < odds.home_win:
                picks.append(
                    BetInstruction(
                        match_id=odds.match_id,
                        selection=Selection.AWAY_WIN,
                        odds=odds.away_win,
                        stake=stake,
                    )
                )
        return self._cap(picks)


class UnderdogStrategy(BaseStrategy):
    """Bets on longshots — the side with the highest decimal odds (≥ 3.50)."""

    THRESHOLD = Decimal("3.50")

    def pick_bets(self, odds_qs) -> list[BetInstruction]:
        picks = []
        stake = self._stake_amount(0.04)
        for odds in odds_qs:
            if odds.home_win is None or odds.away_win is None:
                continue
            best_side_odds = max(odds.home_win, odds.away_win)
            if best_side_odds < self.THRESHOLD:
                continue
            if odds.home_win >= odds.away_win:
                picks.append(
                    BetInstruction(
                        match_id=odds.match_id,
                        selection=Selection.HOME_WIN,
                        odds=odds.home_win,
                        stake=stake,
                    )
                )
            else:
                picks.append(
                    BetInstruction(
                        match_id=odds.match_id,
                        selection=Selection.AWAY_WIN,
                        odds=odds.away_win,
                        stake=stake,
                    )
                )
        return self._cap(picks)


class DrawSpecialistStrategy(BaseStrategy):
    """Always bets the draw — draws occur ~25% of the time in international football."""

    def pick_bets(self, odds_qs) -> list[BetInstruction]:
        picks = []
        stake = self._stake_amount(0.04)
        for odds in odds_qs:
            if odds.draw is None:
                continue
            picks.append(
                BetInstruction(
                    match_id=odds.match_id,
                    selection=Selection.DRAW,
                    odds=odds.draw,
                    stake=stake,
                )
            )
        return self._cap(picks)


class ValueHunterStrategy(BaseStrategy):
    """Hunts value on draws priced ≥ 3.20 — the draw is chronically undervalued."""

    VALUE_THRESHOLD = Decimal("3.20")

    def pick_bets(self, odds_qs) -> list[BetInstruction]:
        picks = []
        stake = self._stake_amount(0.04)
        for odds in odds_qs:
            if odds.draw is None:
                continue
            if odds.draw >= self.VALUE_THRESHOLD:
                picks.append(
                    BetInstruction(
                        match_id=odds.match_id,
                        selection=Selection.DRAW,
                        odds=odds.draw,
                        stake=stake,
                    )
                )
        return self._cap(picks)


class ChaosAgentStrategy(BaseStrategy):
    """Picks a random outcome for every match."""

    def pick_bets(self, odds_qs) -> list[BetInstruction]:
        picks = []
        stake = self._stake_amount(0.03)
        all_selections = [Selection.HOME_WIN, Selection.DRAW, Selection.AWAY_WIN]
        for odds in odds_qs:
            selection = random.choice(all_selections)
            odds_value = {
                Selection.HOME_WIN: odds.home_win,
                Selection.DRAW: odds.draw,
                Selection.AWAY_WIN: odds.away_win,
            }.get(selection)
            if odds_value is None:
                continue
            picks.append(
                BetInstruction(
                    match_id=odds.match_id,
                    selection=selection,
                    odds=odds_value,
                    stake=stake,
                )
            )
        return self._cap(picks)


class AllInAliceStrategy(BaseStrategy):
    """Goes all-in on a single match favourite each day."""

    def pick_bets(self, odds_qs) -> list[BetInstruction]:
        candidates = []
        for odds in odds_qs:
            if odds.home_win is None or odds.away_win is None:
                continue
            if odds.home_win <= odds.away_win:
                candidates.append(
                    BetInstruction(
                        match_id=odds.match_id,
                        selection=Selection.HOME_WIN,
                        odds=odds.home_win,
                        stake=Decimal("0"),  # set below
                    )
                )
            else:
                candidates.append(
                    BetInstruction(
                        match_id=odds.match_id,
                        selection=Selection.AWAY_WIN,
                        odds=odds.away_win,
                        stake=Decimal("0"),
                    )
                )
        if not candidates:
            return []
        pick = min(candidates, key=lambda b: b.odds)
        pick.stake = self._stake_amount(0.20)
        return [pick]


class HomerStrategy(BaseStrategy):
    """Bets on the bot's favourite national team every time they play.

    Uses ``profile.worldcup_country_code`` (ISO 3166-1 alpha-3) to identify
    the team via ``worldcup_matches.Team.country_code``.
    """

    def _resolve_team_id(self):
        if not self.profile.worldcup_country_code:
            return None
        if not hasattr(self, "_team_id_cache"):
            from worldcup.matches.models import Team

            team = Team.objects.filter(
                country_code=self.profile.worldcup_country_code
            ).first()
            self._team_id_cache = team.pk if team else None
        return self._team_id_cache

    def pick_bets(self, odds_qs) -> list[BetInstruction]:
        fav_team_id = self._resolve_team_id()
        if not fav_team_id:
            return []

        picks = []
        stake = self._stake_amount(0.05)
        for odds in odds_qs:
            match = odds.match
            if match.home_team_id == fav_team_id and odds.home_win is not None:
                picks.append(
                    BetInstruction(
                        match_id=odds.match_id,
                        selection=Selection.HOME_WIN,
                        odds=odds.home_win,
                        stake=stake,
                    )
                )
            elif match.away_team_id == fav_team_id and odds.away_win is not None:
                picks.append(
                    BetInstruction(
                        match_id=odds.match_id,
                        selection=Selection.AWAY_WIN,
                        odds=odds.away_win,
                        stake=stake,
                    )
                )
        return self._cap(picks)


class AntiHomerStrategy(BaseStrategy):
    """Bets AGAINST the bot's national team every time they play.

    Uses ``profile.worldcup_country_code`` to find the team, then backs the
    opposing side (or the draw when odds favour it over the straight win).
    """

    def _resolve_team_id(self):
        if not self.profile.worldcup_country_code:
            return None
        if not hasattr(self, "_team_id_cache"):
            from worldcup.matches.models import Team

            team = Team.objects.filter(
                country_code=self.profile.worldcup_country_code
            ).first()
            self._team_id_cache = team.pk if team else None
        return self._team_id_cache

    def pick_bets(self, odds_qs) -> list[BetInstruction]:
        fav_team_id = self._resolve_team_id()
        if not fav_team_id:
            return []

        picks = []
        stake = self._stake_amount(0.05)
        for odds in odds_qs:
            match = odds.match
            if match.home_team_id == fav_team_id:
                # Bet the away win (or draw if draw odds are lower)
                away = odds.away_win
                draw = odds.draw
                if away is not None and draw is not None:
                    if draw <= away:
                        picks.append(
                            BetInstruction(
                                match_id=odds.match_id,
                                selection=Selection.DRAW,
                                odds=draw,
                                stake=stake,
                            )
                        )
                    else:
                        picks.append(
                            BetInstruction(
                                match_id=odds.match_id,
                                selection=Selection.AWAY_WIN,
                                odds=away,
                                stake=stake,
                            )
                        )
                elif away is not None:
                    picks.append(
                        BetInstruction(
                            match_id=odds.match_id,
                            selection=Selection.AWAY_WIN,
                            odds=away,
                            stake=stake,
                        )
                    )
            elif match.away_team_id == fav_team_id:
                # Bet the home win (or draw if draw odds are lower)
                home = odds.home_win
                draw = odds.draw
                if home is not None and draw is not None:
                    if draw <= home:
                        picks.append(
                            BetInstruction(
                                match_id=odds.match_id,
                                selection=Selection.DRAW,
                                odds=draw,
                                stake=stake,
                            )
                        )
                    else:
                        picks.append(
                            BetInstruction(
                                match_id=odds.match_id,
                                selection=Selection.HOME_WIN,
                                odds=home,
                                stake=stake,
                            )
                        )
                elif home is not None:
                    picks.append(
                        BetInstruction(
                            match_id=odds.match_id,
                            selection=Selection.HOME_WIN,
                            odds=home,
                            stake=stake,
                        )
                    )
        return self._cap(picks)


STRATEGY_MAP: dict[str, type[BaseStrategy]] = {
    StrategyType.FRONTRUNNER: FrontrunnerStrategy,
    StrategyType.UNDERDOG: UnderdogStrategy,
    StrategyType.DRAW_SPECIALIST: DrawSpecialistStrategy,
    StrategyType.VALUE_HUNTER: ValueHunterStrategy,
    StrategyType.CHAOS_AGENT: ChaosAgentStrategy,
    StrategyType.ALL_IN_ALICE: AllInAliceStrategy,
    StrategyType.HOMER: HomerStrategy,
    StrategyType.ANTI_HOMER: AntiHomerStrategy,
}
