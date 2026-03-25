import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from nba.betting.odds_engine import generate_all_upcoming_odds
from nba.games.models import Odds

logger = logging.getLogger(__name__)

BOOKMAKER = "House"
ODDS_FIELDS = [
    "home_moneyline",
    "away_moneyline",
    "spread_line",
    "spread_home",
    "spread_away",
    "total_line",
    "over_odds",
    "under_odds",
    "fetched_at",
]


@shared_task(bind=True, max_retries=3)
def generate_odds(self):
    """Generate algorithmic House odds for all upcoming NBA games."""
    logger.info("generate_odds: starting")
    try:
        results = generate_all_upcoming_odds()
        now = timezone.now()
        created = updated = 0

        game_objs = [r["game"] for r in results]
        existing_by_game = {
            o.game_id: o
            for o in Odds.objects.filter(game__in=game_objs, bookmaker=BOOKMAKER)
        }

        to_create = []
        to_update = []

        for r in results:
            game = r["game"]
            existing = existing_by_game.get(game.pk)

            if existing is None:
                to_create.append(
                    Odds(
                        game=game,
                        bookmaker=BOOKMAKER,
                        home_moneyline=r["home_moneyline"],
                        away_moneyline=r["away_moneyline"],
                        spread_line=r["spread_line"],
                        spread_home=r["spread_home"],
                        spread_away=r["spread_away"],
                        total_line=r["total_line"],
                        over_odds=r["over_odds"],
                        under_odds=r["under_odds"],
                        fetched_at=now,
                    )
                )
                created += 1
            elif _odds_changed(existing, r):
                existing.home_moneyline = r["home_moneyline"]
                existing.away_moneyline = r["away_moneyline"]
                existing.spread_line = r["spread_line"]
                existing.spread_home = r["spread_home"]
                existing.spread_away = r["spread_away"]
                existing.total_line = r["total_line"]
                existing.over_odds = r["over_odds"]
                existing.under_odds = r["under_odds"]
                existing.fetched_at = now
                to_update.append(existing)
                updated += 1

        with transaction.atomic():
            if to_create:
                Odds.objects.bulk_create(to_create)
            if to_update:
                Odds.objects.bulk_update(to_update, ODDS_FIELDS)

        logger.info("generate_odds: done created=%d updated=%d", created, updated)

        if created > 0:
            from nba.activity.services import queue_activity_event

            queue_activity_event(
                "odds_update",
                f"Fresh odds generated ({created} new lines)",
                url="/odds/",
                icon="chart-line-up",
            )
    except Exception as exc:
        logger.exception("generate_odds failed")
        raise self.retry(exc=exc, countdown=120 * (2**self.request.retries))


def _odds_changed(existing: Odds, new: dict) -> bool:
    return (
        existing.home_moneyline != new["home_moneyline"]
        or existing.away_moneyline != new["away_moneyline"]
        or existing.spread_line != new["spread_line"]
        or existing.total_line != new["total_line"]
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def settle_pending_bets(self):
    """Find FINAL games with unsettled bets and settle them."""
    try:
        from nba.betting.models import BetSlip, ParlayLeg
        from nba.betting.settlement import settle_game_bets
        from nba.games.models import GameStatus
        from vinosports.betting.models import BetStatus

        game_pks = set(
            BetSlip.objects.filter(
                status=BetStatus.PENDING, game__status=GameStatus.FINAL
            )
            .values_list("game_id", flat=True)
            .distinct()
        ) | set(
            ParlayLeg.objects.filter(
                status=BetStatus.PENDING, game__status=GameStatus.FINAL
            )
            .values_list("game_id", flat=True)
            .distinct()
        )

        results = {}
        for pk in game_pks:
            result = settle_game_bets(pk)
            result.pop("affected_user_ids", None)
            results[pk] = result

        logger.info("settle_pending_bets: settled %d games", len(results))
        return {"games_settled": len(results), "details": results}
    except Exception as exc:
        logger.error("settle_pending_bets failed: %s", exc)
        raise self.retry(exc=exc)
