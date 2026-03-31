from decimal import Decimal

from django.db.models import Max, Min

from nfl.betting.models import BetSlip, Odds, Parlay, ParlayLeg
from nfl.betting.settlement import american_to_decimal, decimal_to_american
from nfl.games.models import Game, GameStatus
from vinosports.betting.parlay_builder import (
    LeagueAdapter,
    LegData,
    ParlayValidationError,
)

# Map (market, selection) → (odds_field, line_field)
_ODDS_FIELD_MAP = {
    ("MONEYLINE", "HOME"): ("home_moneyline", None),
    ("MONEYLINE", "AWAY"): ("away_moneyline", None),
    ("SPREAD", "HOME"): ("spread_home", "spread_line"),
    ("SPREAD", "AWAY"): ("spread_away", "spread_line"),
    ("TOTAL", "OVER"): ("over_odds", "total_line"),
    ("TOTAL", "UNDER"): ("under_odds", "total_line"),
}


class NFLParlayAdapter(LeagueAdapter):
    def fetch_events(self, event_ids: list[int]) -> dict[int, Game]:
        return {
            g.pk: g
            for g in Game.objects.filter(pk__in=event_ids).select_related(
                "home_team", "away_team"
            )
        }

    def is_bettable(self, event: Game) -> bool:
        return event.status == GameStatus.SCHEDULED

    def resolve_odds(self, event: Game, selection: str, extras: dict) -> Decimal:
        market = extras.get("market")
        if not market:
            raise ParlayValidationError(["NFL legs require a 'market' extra."])

        key = (market, selection)
        mapping = _ODDS_FIELD_MAP.get(key)
        if not mapping:
            raise ParlayValidationError([f"Invalid NFL market/selection: {key}"])

        odds_field, line_field = mapping

        agg = Odds.objects.filter(game=event).aggregate(
            best_odds=Max(odds_field),
            **({"line": Min(line_field)} if line_field else {}),
        )

        best_odds = agg.get("best_odds")
        if best_odds is None:
            raise ParlayValidationError(
                [f"No odds available for {event} — {market} {selection}"]
            )

        if line_field:
            extras["line"] = agg.get("line")

        return american_to_decimal(best_odds)

    def create_parlay(self, user, stake, combined_decimal_odds, max_payout):
        combined_american = decimal_to_american(combined_decimal_odds)
        return Parlay.objects.create(
            user=user,
            stake=stake,
            combined_odds=combined_american,
            max_payout=max_payout,
        )

    def build_leg(self, parlay, event, leg: LegData, decimal_odds: Decimal):
        american_odds = decimal_to_american(decimal_odds)
        return ParlayLeg(
            parlay=parlay,
            game=event,
            market=leg.extras.get("market", BetSlip.Market.MONEYLINE),
            selection=leg.selection,
            odds_at_placement=american_odds,
            line=leg.extras.get("line"),
        )

    def get_leg_model(self):
        return ParlayLeg
