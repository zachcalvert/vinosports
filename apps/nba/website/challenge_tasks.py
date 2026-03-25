"""Celery tasks for challenge rotation and expiration."""

import logging
import random
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from vinosports.challenges.models import Challenge, ChallengeTemplate, UserChallenge

logger = logging.getLogger(__name__)

DAILY_COUNT = 3
WEEKLY_COUNT = 2
DAILY_LOOKBACK_DAYS = 7
WEEKLY_LOOKBACK_DAYS = 21


def _recently_used_template_ids(challenge_type, lookback_days):
    cutoff = timezone.now() - timedelta(days=lookback_days)
    return set(
        Challenge.objects.filter(
            template__challenge_type=challenge_type,
            starts_at__gte=cutoff,
        ).values_list("template_id", flat=True)
    )


def _has_games_today():
    from games.models import Game, GameStatus

    today = timezone.localdate()
    return Game.objects.filter(
        game_date=today,
        status=GameStatus.SCHEDULED,
    ).exists()


def _expire_and_fail(challenge_type=None, queryset=None):
    if queryset is None:
        queryset = Challenge.objects.filter(
            template__challenge_type=challenge_type,
            status=Challenge.Status.ACTIVE,
        )

    challenge_ids = list(queryset.values_list("pk", flat=True))
    if not challenge_ids:
        return 0

    failed_count = UserChallenge.objects.filter(
        challenge_id__in=challenge_ids,
        status=UserChallenge.Status.IN_PROGRESS,
    ).update(status=UserChallenge.Status.FAILED)

    expired_count = Challenge.objects.filter(pk__in=challenge_ids).update(
        status=Challenge.Status.EXPIRED
    )

    logger.info(
        "Expired %d challenges, failed %d user challenges (type=%s)",
        expired_count,
        failed_count,
        challenge_type,
    )
    return expired_count


@shared_task(max_retries=1)
def rotate_daily_challenges():
    _expire_and_fail(challenge_type=ChallengeTemplate.ChallengeType.DAILY)

    if not _has_games_today():
        logger.info("No games today — skipping daily challenge creation.")
        return "skipped: no games"

    recent_ids = _recently_used_template_ids(
        ChallengeTemplate.ChallengeType.DAILY, DAILY_LOOKBACK_DAYS
    )
    candidates = list(
        ChallengeTemplate.objects.filter(
            challenge_type=ChallengeTemplate.ChallengeType.DAILY,
            is_active=True,
        ).exclude(pk__in=recent_ids)
    )

    if len(candidates) < DAILY_COUNT:
        candidates = list(
            ChallengeTemplate.objects.filter(
                challenge_type=ChallengeTemplate.ChallengeType.DAILY,
                is_active=True,
            )
        )

    selected = random.sample(candidates, min(DAILY_COUNT, len(candidates)))

    now = timezone.now()
    tomorrow_6_30am = now.replace(hour=6, minute=30, second=0, microsecond=0)
    if tomorrow_6_30am <= now:
        tomorrow_6_30am += timedelta(days=1)

    created = []
    for template in selected:
        challenge = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=now,
            ends_at=tomorrow_6_30am,
        )
        created.append(challenge)

    logger.info(
        "Created %d daily challenges: %s", len(created), [c.pk for c in created]
    )
    return f"created: {len(created)}"


@shared_task(max_retries=1)
def rotate_weekly_challenges():
    _expire_and_fail(challenge_type=ChallengeTemplate.ChallengeType.WEEKLY)

    recent_ids = _recently_used_template_ids(
        ChallengeTemplate.ChallengeType.WEEKLY, WEEKLY_LOOKBACK_DAYS
    )
    candidates = list(
        ChallengeTemplate.objects.filter(
            challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
            is_active=True,
        ).exclude(pk__in=recent_ids)
    )

    if len(candidates) < WEEKLY_COUNT:
        candidates = list(
            ChallengeTemplate.objects.filter(
                challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
                is_active=True,
            )
        )

    selected = random.sample(candidates, min(WEEKLY_COUNT, len(candidates)))

    now = timezone.now()
    days_until_monday = (0 - now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday_6_30am = (now + timedelta(days=days_until_monday)).replace(
        hour=6, minute=30, second=0, microsecond=0
    )

    created = []
    for template in selected:
        challenge = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=now,
            ends_at=next_monday_6_30am,
        )
        created.append(challenge)

    logger.info(
        "Created %d weekly challenges: %s",
        len(created),
        [c.pk for c in created],
    )
    return f"created: {len(created)}"


@shared_task(max_retries=1)
def expire_challenges():
    now = timezone.now()
    overdue = Challenge.objects.filter(
        status=Challenge.Status.ACTIVE,
        ends_at__lte=now,
    )
    count = _expire_and_fail(queryset=overdue)
    if count:
        logger.info("expire_challenges: expired %d overdue challenges", count)
    return f"expired: {count}"
