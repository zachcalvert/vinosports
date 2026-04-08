import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def generate_odds():
    """Generate house odds for upcoming UCL matches."""
    from ucl.betting.odds_engine import generate_all_upcoming_odds

    count = generate_all_upcoming_odds()
    logger.info("Generated odds for %d matches", count)


@shared_task
def settle_match_bets(match_pk):
    """Settle all bets for a finished match."""
    from ucl.matches.models import Match

    try:
        match = Match.objects.get(pk=match_pk)
    except Match.DoesNotExist:
        logger.error("Match %s not found for settlement", match_pk)
        return

    if match.status != Match.Status.FINISHED:
        logger.warning("Match %s not finished, skipping settlement", match_pk)
        return

    from ucl.betting.models import BetSlip

    # Settlement on 90-minute result
    if match.home_score is None or match.away_score is None:
        logger.warning("Match %s has no scores, skipping settlement", match_pk)
        return

    if match.home_score > match.away_score:
        winning_selection = BetSlip.Selection.HOME_WIN
    elif match.away_score > match.home_score:
        winning_selection = BetSlip.Selection.AWAY_WIN
    else:
        winning_selection = BetSlip.Selection.DRAW

    from vinosports.betting.models import BetStatus

    pending_bets = BetSlip.objects.filter(match=match, status=BetStatus.PENDING)

    for bet in pending_bets:
        if bet.selection == winning_selection:
            bet.status = BetStatus.WON
            bet.payout = bet.stake * bet.odds_at_placement
        else:
            bet.status = BetStatus.LOST
            bet.payout = 0
        bet.save()

    logger.info(
        "Settled %d bets for %s — winning selection: %s",
        pending_bets.count(),
        match,
        winning_selection,
    )


@shared_task
def update_futures_odds():
    """Recalculate futures odds after results."""
    from ucl.betting.futures_odds_engine import update_all_futures_odds

    update_all_futures_odds()
