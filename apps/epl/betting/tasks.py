import logging
from decimal import Decimal

from celery import shared_task
from django.db import transaction
from matches.models import Match, Odds

from betting.models import BetSlip, Parlay, ParlayLeg
from betting.odds_engine import generate_all_upcoming_odds
from betting.stats import record_bet_result
from vinosports.betting.balance import log_transaction
from vinosports.betting.models import BalanceTransaction, UserBalance

logger = logging.getLogger(__name__)


def _schedule_stat_update(
    user, won, stake, payout, odds=None, is_parlay=False, leg_count=0
):
    transaction.on_commit(
        lambda: record_bet_result(
            user,
            won=won,
            stake=stake,
            payout=payout,
            odds=odds,
            is_parlay=is_parlay,
            leg_count=leg_count,
        )
    )


def settle_parlay_legs(match, winning_selection):
    pending_legs = ParlayLeg.objects.filter(
        match=match, status=ParlayLeg.Status.PENDING
    ).select_related("parlay")

    if not pending_legs.exists():
        return

    affected_parlay_ids = set()

    for leg in pending_legs:
        if winning_selection is None:
            leg.status = ParlayLeg.Status.VOID
        elif leg.selection == winning_selection:
            leg.status = ParlayLeg.Status.WON
        else:
            leg.status = ParlayLeg.Status.LOST
        leg.save(update_fields=["status"])
        affected_parlay_ids.add(leg.parlay_id)

    for parlay_id in affected_parlay_ids:
        try:
            _evaluate_parlay(parlay_id)
        except Exception:
            logger.exception(
                "settle_parlay_legs: error evaluating parlay %d", parlay_id
            )


def _recalculate_combined_odds(parlay, legs):
    active_legs = [leg for leg in legs if leg.status != ParlayLeg.Status.VOID]
    if not active_legs:
        parlay.combined_odds = Decimal("1.00")
    else:
        combined = Decimal("1.00")
        for leg in active_legs:
            combined *= leg.odds_at_placement
        parlay.combined_odds = combined.quantize(Decimal("0.01"))


def _evaluate_parlay(parlay_id):
    try:
        with transaction.atomic():
            parlay = Parlay.objects.select_for_update().get(pk=parlay_id)
            if parlay.status != Parlay.Status.PENDING:
                return

            legs = list(parlay.legs.all())
            if not legs:
                logger.error(
                    "_evaluate_parlay: parlay %d has no legs — marking LOST", parlay_id
                )
                parlay.status = Parlay.Status.LOST
                parlay.payout = Decimal("0")
                parlay.save(update_fields=["status", "payout"])
                _schedule_stat_update(
                    parlay.user,
                    False,
                    parlay.stake,
                    Decimal("0"),
                    is_parlay=True,
                    leg_count=0,
                )
                return

            statuses = {leg.status for leg in legs}

            if ParlayLeg.Status.LOST in statuses:
                parlay.status = Parlay.Status.LOST
                parlay.payout = Decimal("0")
                parlay.save(update_fields=["status", "payout"])
                logger.info("_evaluate_parlay: parlay %d LOST", parlay_id)
                _schedule_stat_update(
                    parlay.user,
                    False,
                    parlay.stake,
                    Decimal("0"),
                    odds=parlay.combined_odds,
                    is_parlay=True,
                    leg_count=len(legs),
                )
                return

            if ParlayLeg.Status.PENDING in statuses:
                if ParlayLeg.Status.VOID in statuses:
                    _recalculate_combined_odds(parlay, legs)
                    parlay.save(update_fields=["combined_odds"])
                return

            if all(leg.status == ParlayLeg.Status.VOID for leg in legs):
                parlay.status = Parlay.Status.VOID
                parlay.payout = parlay.stake
                parlay.save(update_fields=["status", "payout"])

                balance = UserBalance.objects.select_for_update().get(user=parlay.user)
                log_transaction(
                    balance,
                    parlay.stake,
                    BalanceTransaction.Type.PARLAY_VOID,
                    f"Parlay {parlay.id_hash} voided",
                )
                logger.info(
                    "_evaluate_parlay: parlay %d VOID — refunded %s",
                    parlay_id,
                    parlay.stake,
                )
                return

            _recalculate_combined_odds(parlay, legs)
            payout = min(parlay.stake * parlay.combined_odds, parlay.max_payout)
            parlay.status = Parlay.Status.WON
            parlay.payout = payout
            parlay.save(update_fields=["status", "payout", "combined_odds"])

            balance = UserBalance.objects.select_for_update().get(user=parlay.user)
            log_transaction(
                balance,
                payout,
                BalanceTransaction.Type.PARLAY_WIN,
                f"Parlay {parlay.id_hash} won",
            )
            logger.info(
                "_evaluate_parlay: parlay %d WON — payout %s (combined odds %s)",
                parlay_id,
                payout,
                parlay.combined_odds,
            )
            _schedule_stat_update(
                parlay.user,
                True,
                parlay.stake,
                payout,
                odds=parlay.combined_odds,
                is_parlay=True,
                leg_count=len(legs),
            )

    except Parlay.DoesNotExist:
        logger.error("_evaluate_parlay: parlay %d not found", parlay_id)


@shared_task(bind=True, max_retries=3)
def generate_odds(self):
    logger.info("generate_odds: starting")
    try:
        from django.conf import settings as django_settings
        from django.utils import timezone as tz

        results = generate_all_upcoming_odds(django_settings.CURRENT_SEASON)
        now = tz.now()
        created = updated = 0

        match_objs = [r["match"] for r in results]
        existing_by_match_id = {
            o.match_id: o
            for o in Odds.objects.filter(match__in=match_objs, bookmaker="House")
        }

        to_create = []
        to_update = []

        for r in results:
            match = r["match"]
            home_win, draw, away_win = r["home_win"], r["draw"], r["away_win"]
            existing = existing_by_match_id.get(match.pk)

            if existing is None:
                to_create.append(
                    Odds(
                        match=match,
                        bookmaker="House",
                        home_win=home_win,
                        draw=draw,
                        away_win=away_win,
                        fetched_at=now,
                    )
                )
                created += 1
            elif (
                existing.home_win != home_win
                or existing.draw != draw
                or existing.away_win != away_win
            ):
                existing.home_win = home_win
                existing.draw = draw
                existing.away_win = away_win
                existing.fetched_at = now
                to_update.append(existing)
                updated += 1

        with transaction.atomic():
            if to_create:
                Odds.objects.bulk_create(to_create)
            if to_update:
                Odds.objects.bulk_update(
                    to_update, ["home_win", "draw", "away_win", "fetched_at"]
                )

        logger.info("generate_odds: done created=%d updated=%d", created, updated)

        if created > 0:
            from activity.services import queue_activity_event

            queue_activity_event(
                "odds_update",
                f"Fresh odds generated ({created} new lines)",
                url="/odds/",
                icon="chart-line-up",
            )
    except Exception as exc:
        logger.exception("generate_odds failed")
        raise self.retry(exc=exc, countdown=120 * (2**self.request.retries))


@shared_task(bind=True, max_retries=3)
def settle_match_bets(self, match_id):
    logger.info("settle_match_bets: starting for match %d", match_id)

    try:
        match = Match.objects.select_related("home_team", "away_team").get(pk=match_id)
    except Match.DoesNotExist:
        logger.error("settle_match_bets: match %d not found", match_id)
        return

    pending_bets = BetSlip.objects.filter(match=match, status=BetSlip.Status.PENDING)
    pending_parlay_legs = ParlayLeg.objects.filter(
        match=match, status=ParlayLeg.Status.PENDING
    )
    if not pending_bets.exists() and not pending_parlay_legs.exists():
        logger.info(
            "settle_match_bets: no pending bets or parlay legs for match %d", match_id
        )
        return

    if match.status in (Match.Status.CANCELLED, Match.Status.POSTPONED):
        for bet in pending_bets.select_related("user"):
            with transaction.atomic():
                bet.status = BetSlip.Status.VOID
                bet.payout = bet.stake
                bet.save(update_fields=["status", "payout"])

                balance = UserBalance.objects.select_for_update().get(user=bet.user)
                log_transaction(
                    balance,
                    bet.stake,
                    BalanceTransaction.Type.BET_VOID,
                    f"Bet {bet.id_hash} voided",
                )

        logger.info(
            "settle_match_bets: voided %d bets for %s match %d",
            pending_bets.count(),
            match.status,
            match_id,
        )
        settle_parlay_legs(match, winning_selection=None)
        return

    if match.status != Match.Status.FINISHED:
        logger.warning(
            "settle_match_bets: match %d status is %s, not FINISHED",
            match_id,
            match.status,
        )
        return

    if match.home_score is None or match.away_score is None:
        logger.error("settle_match_bets: match %d has no scores", match_id)
        return

    if match.home_score > match.away_score:
        winning_selection = BetSlip.Selection.HOME_WIN
    elif match.home_score < match.away_score:
        winning_selection = BetSlip.Selection.AWAY_WIN
    else:
        winning_selection = BetSlip.Selection.DRAW

    won_count = 0
    lost_count = 0

    for bet in pending_bets.select_related("user"):
        with transaction.atomic():
            if bet.selection == winning_selection:
                payout = bet.stake * bet.odds_at_placement
                bet.status = BetSlip.Status.WON
                bet.payout = payout
                bet.save(update_fields=["status", "payout"])

                balance = UserBalance.objects.select_for_update().get(user=bet.user)
                log_transaction(
                    balance,
                    payout,
                    BalanceTransaction.Type.BET_WIN,
                    f"Bet {bet.id_hash} won",
                )
                won_count += 1
            else:
                payout = Decimal("0")
                bet.status = BetSlip.Status.LOST
                bet.payout = payout
                bet.save(update_fields=["status", "payout"])
                lost_count += 1

        record_bet_result(
            bet.user,
            won=(bet.status == BetSlip.Status.WON),
            stake=bet.stake,
            payout=bet.payout or Decimal("0"),
            odds=bet.odds_at_placement,
            matchday=match.matchday,
        )

    logger.info(
        "settle_match_bets: match %d settled — %d won, %d lost",
        match_id,
        won_count,
        lost_count,
    )
    settle_parlay_legs(match, winning_selection)

    total = won_count + lost_count
    if total > 0:
        from activity.services import queue_activity_event

        queue_activity_event(
            "bet_settlement",
            f"{total} bets settled on {match.home_team.short_name} vs {match.away_team.short_name}",
            url=match.get_absolute_url(),
            icon="check-circle",
        )
