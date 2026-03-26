from decimal import Decimal

from django.db.models import Min

from epl.betting.models import Parlay, ParlayLeg
from epl.matches.models import Match, Odds
from vinosports.betting.parlay_builder import (
    LeagueAdapter,
    LegData,
    ParlayValidationError,
)

SELECTION_TO_ODDS_FIELD = {
    "HOME_WIN": "home_win",
    "DRAW": "draw",
    "AWAY_WIN": "away_win",
}


class EPLParlayAdapter(LeagueAdapter):
    def fetch_events(self, event_ids: list[int]) -> dict[int, Match]:
        return {
            m.pk: m
            for m in Match.objects.filter(pk__in=event_ids).select_related(
                "home_team", "away_team"
            )
        }

    def is_bettable(self, event: Match) -> bool:
        return event.status in (Match.Status.SCHEDULED, Match.Status.TIMED)

    def resolve_odds(self, event: Match, selection: str, extras: dict) -> Decimal:
        odds_field = SELECTION_TO_ODDS_FIELD.get(selection)
        if not odds_field:
            raise ParlayValidationError([f"Invalid EPL selection: {selection}"])

        best = (
            Odds.objects.filter(match=event).aggregate(best=Min(odds_field)).get("best")
        )
        if not best:
            raise ParlayValidationError(
                [f"No odds available for {event} — {selection}"]
            )
        return best  # already decimal

    def create_parlay(self, user, stake, combined_decimal_odds, max_payout):
        return Parlay.objects.create(
            user=user,
            stake=stake,
            combined_odds=combined_decimal_odds,
            max_payout=max_payout,
        )

    def build_leg(self, parlay, event, leg: LegData, decimal_odds: Decimal):
        return ParlayLeg(
            parlay=parlay,
            match=event,
            selection=leg.selection,
            odds_at_placement=decimal_odds,
        )

    def get_leg_model(self):
        return ParlayLeg
