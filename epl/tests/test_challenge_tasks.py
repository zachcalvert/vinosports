"""Tests for website/challenge_tasks.py — rotate_daily_challenges, rotate_weekly_challenges, expire_challenges."""

import random
from datetime import timedelta

import pytest
from django.utils import timezone

from epl.matches.models import Match
from epl.website.challenge_tasks import (
    expire_challenges,
    rotate_daily_challenges,
    rotate_weekly_challenges,
)
from vinosports.challenges.models import Challenge, ChallengeTemplate, UserChallenge

from .factories import MatchFactory, UserFactory

pytestmark = pytest.mark.django_db


def _make_challenge_template(challenge_type, slug_suffix="", is_active=True):
    suffix = slug_suffix or str(random.randint(1000, 9999))
    return ChallengeTemplate.objects.create(
        slug=f"test-{challenge_type.lower()}-{suffix}",
        title=f"Test {challenge_type} Challenge {suffix}",
        description="A test challenge",
        icon="star",
        challenge_type=challenge_type,
        criteria_type=ChallengeTemplate.CriteriaType.BET_COUNT,
        criteria_params={"target": 3},
        reward_amount="50.00",
        is_active=is_active,
    )


def _create_match_today():
    """Create a match scheduled for today/tomorrow so _has_matches_today returns True."""
    now = timezone.now()
    return MatchFactory(
        status=Match.Status.SCHEDULED,
        kickoff=now + timedelta(hours=2),
    )


class TestRotateDailyChallenges:
    def test_skipped_when_no_matches_today(self):
        _make_challenge_template(ChallengeTemplate.ChallengeType.DAILY, "no-match")
        result = rotate_daily_challenges()
        assert result == "skipped: no matches"

    def test_creates_challenges_when_matches_exist(self):
        _create_match_today()
        _make_challenge_template(ChallengeTemplate.ChallengeType.DAILY, "d1")
        _make_challenge_template(ChallengeTemplate.ChallengeType.DAILY, "d2")
        _make_challenge_template(ChallengeTemplate.ChallengeType.DAILY, "d3")

        result = rotate_daily_challenges()
        assert result.startswith("created:")
        assert Challenge.objects.filter(
            template__challenge_type=ChallengeTemplate.ChallengeType.DAILY
        ).exists()

    def test_expires_active_daily_challenges_before_creating(self):
        _create_match_today()
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "expire-before"
        )
        old_challenge = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(hours=25),
            ends_at=timezone.now() - timedelta(hours=1),
        )

        rotate_daily_challenges()

        old_challenge.refresh_from_db()
        assert old_challenge.status == Challenge.Status.EXPIRED

    def test_fails_in_progress_user_challenges(self):
        _create_match_today()
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "fail-uc"
        )
        old = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(hours=25),
            ends_at=timezone.now() - timedelta(hours=1),
        )
        user = UserFactory()
        uc = UserChallenge.objects.create(
            user=user,
            challenge=old,
            status=UserChallenge.Status.IN_PROGRESS,
            progress=1,
            target=3,
        )

        rotate_daily_challenges()

        uc.refresh_from_db()
        assert uc.status == UserChallenge.Status.FAILED

    def test_uses_fallback_when_all_templates_recently_used(self):
        _create_match_today()
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "recent"
        )
        # Recently used
        Challenge.objects.create(
            template=template,
            status=Challenge.Status.EXPIRED,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() - timedelta(hours=1),
        )

        result = rotate_daily_challenges()
        assert result == "created: 1"

    def test_creates_at_most_daily_count_challenges(self):
        _create_match_today()
        for i in range(5):
            _make_challenge_template(ChallengeTemplate.ChallengeType.DAILY, f"max-{i}")

        rotate_daily_challenges()

        count = Challenge.objects.filter(
            template__challenge_type=ChallengeTemplate.ChallengeType.DAILY,
            status=Challenge.Status.ACTIVE,
        ).count()
        assert count <= 3


class TestRotateWeeklyChallenges:
    def test_skipped_when_no_upcoming_matchday(self):
        _make_challenge_template(ChallengeTemplate.ChallengeType.WEEKLY, "w1")
        result = rotate_weekly_challenges()
        assert result == "skipped: no matchday"

    def test_creates_weekly_challenges(self):
        # Need a scheduled match for matchday detection
        MatchFactory(status=Match.Status.SCHEDULED)
        _make_challenge_template(ChallengeTemplate.ChallengeType.WEEKLY, "w1")
        _make_challenge_template(ChallengeTemplate.ChallengeType.WEEKLY, "w2")

        result = rotate_weekly_challenges()
        assert result.startswith("created:")
        assert Challenge.objects.filter(
            template__challenge_type=ChallengeTemplate.ChallengeType.WEEKLY
        ).exists()

    def test_expires_active_weekly_challenges(self):
        MatchFactory(status=Match.Status.SCHEDULED)
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.WEEKLY, "w-expire"
        )
        old = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(days=8),
            ends_at=timezone.now() - timedelta(hours=1),
        )

        rotate_weekly_challenges()

        old.refresh_from_db()
        assert old.status == Challenge.Status.EXPIRED

    def test_creates_at_most_weekly_count_challenges(self):
        MatchFactory(status=Match.Status.SCHEDULED)
        for i in range(4):
            _make_challenge_template(
                ChallengeTemplate.ChallengeType.WEEKLY, f"w-max-{i}"
            )

        rotate_weekly_challenges()

        count = Challenge.objects.filter(
            template__challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
            status=Challenge.Status.ACTIVE,
        ).count()
        assert count <= 2

    def test_no_templates_returns_zero(self):
        MatchFactory(status=Match.Status.SCHEDULED)
        result = rotate_weekly_challenges()
        assert result == "created: 0"

    def test_uses_fallback_when_all_recently_used(self):
        MatchFactory(status=Match.Status.SCHEDULED)
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.WEEKLY, "w-recent"
        )
        Challenge.objects.create(
            template=template,
            status=Challenge.Status.EXPIRED,
            starts_at=timezone.now() - timedelta(days=7),
            ends_at=timezone.now() - timedelta(hours=1),
        )

        result = rotate_weekly_challenges()
        assert result.startswith("created:")


class TestExpireChallenges:
    def test_expires_overdue_active_challenges(self):
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "overdue"
        )
        overdue = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(hours=25),
            ends_at=timezone.now() - timedelta(hours=1),
        )

        result = expire_challenges()

        overdue.refresh_from_db()
        assert overdue.status == Challenge.Status.EXPIRED
        assert "1" in result

    def test_keeps_future_challenges_active(self):
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "future"
        )
        future = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=timezone.now() + timedelta(hours=23),
        )

        expire_challenges()

        future.refresh_from_db()
        assert future.status == Challenge.Status.ACTIVE

    def test_no_overdue_returns_zero(self):
        result = expire_challenges()
        assert result == "expired: 0"

    def test_fails_in_progress_user_challenges_on_expire(self):
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "fail-expire"
        )
        overdue = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(hours=25),
            ends_at=timezone.now() - timedelta(hours=1),
        )
        user = UserFactory()
        uc = UserChallenge.objects.create(
            user=user,
            challenge=overdue,
            status=UserChallenge.Status.IN_PROGRESS,
            progress=2,
            target=3,
        )

        expire_challenges()

        uc.refresh_from_db()
        assert uc.status == UserChallenge.Status.FAILED
