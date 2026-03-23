import logging

from celery import shared_task

from betting.services import sync_odds

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_odds(self):
    """Fetch current NBA odds from The Odds API."""
    try:
        count = sync_odds()
        return {"synced": count}
    except Exception as exc:
        logger.error("fetch_odds failed: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def settle_pending_bets(self):
    """Find FINAL games with unsettled bets and settle them."""
    try:
        from games.models import GameStatus

        from betting.models import BetSlip, ParlayLeg
        from betting.settlement import settle_game_bets
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
