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


def _has_matches_today():
    from matches.models import Match

    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)
    return Match.objects.filter(
        kickoff__date__gte=today,
        kickoff__date__lte=tomorrow,
        status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
    ).exists()


def _get_current_matchday():
    from matches.models import Match

    upcoming = (
        Match.objects.filter(
            status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
        )
        .order_by("kickoff")
        .values_list("matchday", flat=True)
        .first()
    )
    return upcoming


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

    if not _has_matches_today():
        logger.info("No matches today — skipping daily challenge creation.")
        return "skipped: no matches"

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
    tomorrow_5am = now.replace(hour=5, minute=0, second=0, microsecond=0)
    if tomorrow_5am <= now:
        tomorrow_5am += timedelta(days=1)

    created = []
    for template in selected:
        challenge = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=now,
            ends_at=tomorrow_5am,
        )
        created.append(challenge)

    logger.info("Created %d daily challenges: %s", len(created), [c.pk for c in created])
    return f"created: {len(created)}"


@shared_task(max_retries=1)
def rotate_weekly_challenges():
    _expire_and_fail(challenge_type=ChallengeTemplate.ChallengeType.WEEKLY)

    matchday = _get_current_matchday()
    if matchday is None:
        logger.info("No upcoming matchday — skipping weekly challenge creation.")
        return "skipped: no matchday"

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
    days_until_tuesday = (1 - now.weekday()) % 7
    if days_until_tuesday == 0:
        days_until_tuesday = 7
    next_tuesday_5am = (now + timedelta(days=days_until_tuesday)).replace(
        hour=5, minute=0, second=0, microsecond=0
    )

    from matches.models import Match

    matchday_match_count = Match.objects.filter(matchday=matchday).count()

    created = []
    for template in selected:
        if template.criteria_type == ChallengeTemplate.CriteriaType.BET_ALL_MATCHES:
            template.criteria_params = {
                **template.criteria_params,
                "target": matchday_match_count or 10,
            }
            template.save(update_fields=["criteria_params"])

        challenge = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=now,
            ends_at=next_tuesday_5am,
            matchday=matchday,
        )
        created.append(challenge)

    logger.info(
        "Created %d weekly challenges for matchday %s: %s",
        len(created),
        matchday,
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
