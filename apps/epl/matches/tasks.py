import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from betting.tasks import settle_match_bets
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings
from django.utils import timezone

from matches.models import Match
from matches.services import (
    FootballDataClient,
    fetch_match_hype_data,
    sync_matches,
    sync_standings,
    sync_teams,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def fetch_teams(self):
    logger.info("fetch_teams: starting")
    try:
        created, updated = sync_teams(settings.CURRENT_SEASON)
        logger.info("fetch_teams: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_teams failed")
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@shared_task(bind=True, max_retries=3)
def fetch_fixtures(self):
    logger.info("fetch_fixtures: starting")
    try:
        created, updated = sync_matches(settings.CURRENT_SEASON)
        logger.info("fetch_fixtures: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_fixtures failed")
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@shared_task(bind=True, max_retries=3)
def fetch_standings(self):
    logger.info("fetch_standings: starting")
    try:
        created, updated = sync_standings(settings.CURRENT_SEASON)
        logger.info("fetch_standings: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_standings failed")
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@shared_task(bind=True, max_retries=3)
def fetch_live_scores(self):
    logger.info("fetch_live_scores: starting")
    try:
        pre_sync = {
            m["pk"]: (m["home_score"], m["away_score"], m["status"])
            for m in Match.objects.filter(
                status__in=["IN_PLAY", "PAUSED", "FINISHED"],
                season=settings.CURRENT_SEASON,
            ).values("pk", "home_score", "away_score", "status")
        }

        from datetime import date

        created, updated = sync_matches(settings.CURRENT_SEASON, game_date=date.today())
        logger.info("fetch_live_scores: done created=%d updated=%d", created, updated)

        still_live_pks = Match.objects.filter(
            status__in=["IN_PLAY", "PAUSED"],
            season=settings.CURRENT_SEASON,
        ).values_list("pk", "external_id")

        stale_matches = [
            (pk, ext_id) for pk, ext_id in still_live_pks if pk in pre_sync
        ]
        if stale_matches:
            stale_updated = _refresh_stale_matches(stale_matches)
            updated += stale_updated

        if updated > 0 or created > 0:
            _broadcast_score_changes(pre_sync)

    except Exception as exc:
        logger.exception("fetch_live_scores failed")
        raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))


def _refresh_stale_matches(stale_matches):
    updated = 0
    with FootballDataClient() as client:
        for pk, ext_id in stale_matches:
            try:
                data = client.get_match(ext_id)
                Match.objects.filter(pk=pk).update(
                    status=data["status"],
                    home_score=data["home_score"],
                    away_score=data["away_score"],
                )
                logger.info(
                    "Refreshed stale match %d (ext %d): status=%s",
                    pk,
                    ext_id,
                    data["status"],
                )
                updated += 1
            except Exception:
                logger.exception("Failed to refresh stale match %d", pk)
    return updated


def _broadcast_score_changes(pre_sync):
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("No channel layer configured, skipping broadcast")
        return

    send = async_to_sync(channel_layer.group_send)

    current = (
        Match.objects.filter(pk__in=list(pre_sync.keys()))
        .union(
            Match.objects.filter(
                status__in=["IN_PLAY", "PAUSED"],
                season=settings.CURRENT_SEASON,
            )
        )
        .values("pk", "home_score", "away_score", "status")
    )

    for m in current:
        pk = m["pk"]
        old = pre_sync.get(pk)
        new_state = (m["home_score"], m["away_score"], m["status"])

        if old is None or old != new_state:
            logger.info("Broadcasting score update for match %d", pk)
            send("live_scores", {"type": "score_update", "match_id": pk})
            send(f"match_{pk}", {"type": "match_score_update", "match_id": pk})

            if old and (old[0] != m["home_score"] or old[1] != m["away_score"]):
                from activity.services import queue_activity_event

                match_obj = (
                    Match.objects.filter(pk=pk)
                    .select_related("home_team", "away_team")
                    .first()
                )
                if match_obj:
                    queue_activity_event(
                        "score_change",
                        f"GOAL! {match_obj.home_team.short_name} "
                        f"{m['home_score']}-{m['away_score']} "
                        f"{match_obj.away_team.short_name}",
                        url=match_obj.get_absolute_url(),
                        icon="soccer-ball",
                    )

            old_status = old[2] if old else None
            new_status = m["status"]
            if (
                new_status in ("FINISHED", "CANCELLED", "POSTPONED")
                and old_status != new_status
            ):
                logger.info(
                    "Triggering bet settlement for match %d (status: %s)",
                    pk,
                    new_status,
                )
                settle_match_bets.delay(pk)


@shared_task
def prefetch_upcoming_hype_data():
    now = timezone.now()
    cutoff = now + timedelta(hours=48)
    upcoming = (
        Match.objects.filter(
            status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
            kickoff__gte=now,
            kickoff__lte=cutoff,
            season=settings.CURRENT_SEASON,
        )
        .select_related("home_team", "away_team")
        .prefetch_related("hype_stats")
    )

    refreshed = skipped = 0
    for match in upcoming:
        try:
            stats = match.hype_stats
        except match.__class__.hype_stats.RelatedObjectDoesNotExist:
            stats = None

        if stats and not stats.is_stale():
            skipped += 1
            continue

        fetch_match_hype_data(match)
        refreshed += 1

    logger.info(
        "prefetch_upcoming_hype_data: refreshed=%d skipped=%d", refreshed, skipped
    )
