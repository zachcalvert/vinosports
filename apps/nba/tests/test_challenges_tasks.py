"""Tests for challenges/tasks.py (rotate_daily_challenges, rotate_weekly_challenges, expire_challenges)."""

import random
from datetime import timedelta

import pytest
from django.utils import timezone
from games.models import GameStatus
from website.challenge_tasks import (
    expire_challenges,
    rotate_daily_challenges,
    rotate_weekly_challenges,
)

from tests.factories import GameFactory, UserFactory
from vinosports.challenges.models import Challenge, ChallengeTemplate, UserChallenge


def _make_challenge_template(challenge_type, slug_suffix="", is_active=True):
    """Helper to create a ChallengeTemplate."""
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


@pytest.mark.django_db
class TestRotateDailyChallenges:
    def test_skipped_when_no_games_today(self):
        """rotate_daily_challenges should skip creation if no games today."""
        _make_challenge_template(ChallengeTemplate.ChallengeType.DAILY, "no-games")
        result = rotate_daily_challenges()
        assert result == "skipped: no games"

    def test_creates_challenges_when_games_exist(self):
        """rotate_daily_challenges should create challenges when games are scheduled."""
        GameFactory(status=GameStatus.SCHEDULED, game_date=timezone.localdate())
        _make_challenge_template(ChallengeTemplate.ChallengeType.DAILY, "with-games-1")
        _make_challenge_template(ChallengeTemplate.ChallengeType.DAILY, "with-games-2")
        _make_challenge_template(ChallengeTemplate.ChallengeType.DAILY, "with-games-3")

        result = rotate_daily_challenges()

        assert result.startswith("created:")
        assert Challenge.objects.filter(
            template__challenge_type=ChallengeTemplate.ChallengeType.DAILY
        ).exists()

    def test_expires_active_daily_challenges_before_creating(self):
        """Existing ACTIVE daily challenges should be expired before new ones are created."""
        GameFactory(status=GameStatus.SCHEDULED, game_date=timezone.localdate())
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
        """IN_PROGRESS UserChallenges should be marked FAILED when their challenge expires."""
        GameFactory(status=GameStatus.SCHEDULED, game_date=timezone.localdate())
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "fail-user-challenges"
        )
        old_challenge = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(hours=25),
            ends_at=timezone.now() - timedelta(hours=1),
        )
        user = UserFactory()
        user_challenge = UserChallenge.objects.create(
            user=user,
            challenge=old_challenge,
            status=UserChallenge.Status.IN_PROGRESS,
            progress=1,
            target=3,
        )

        rotate_daily_challenges()

        user_challenge.refresh_from_db()
        assert user_challenge.status == UserChallenge.Status.FAILED

    def test_uses_fallback_when_all_templates_recently_used(self):
        """When all templates were recently used, fall back to using all templates."""
        GameFactory(status=GameStatus.SCHEDULED, game_date=timezone.localdate())
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "recently-used"
        )
        # Simulate recently used
        Challenge.objects.create(
            template=template,
            status=Challenge.Status.EXPIRED,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() - timedelta(hours=1),
        )

        result = rotate_daily_challenges()

        # Should still create challenges using the fallback pool
        assert result == "created: 1"

    def test_creates_at_most_daily_count_challenges(self):
        """Should create at most 3 daily challenges (DAILY_COUNT)."""
        GameFactory(status=GameStatus.SCHEDULED, game_date=timezone.localdate())
        for i in range(5):
            _make_challenge_template(
                ChallengeTemplate.ChallengeType.DAILY, f"daily-max-{i}"
            )

        rotate_daily_challenges()

        count = Challenge.objects.filter(
            template__challenge_type=ChallengeTemplate.ChallengeType.DAILY,
            status=Challenge.Status.ACTIVE,
        ).count()
        assert count <= 3


@pytest.mark.django_db
class TestRotateWeeklyChallenges:
    def test_creates_weekly_challenges(self):
        """rotate_weekly_challenges should create challenges from weekly templates."""
        _make_challenge_template(ChallengeTemplate.ChallengeType.WEEKLY, "weekly-1")
        _make_challenge_template(ChallengeTemplate.ChallengeType.WEEKLY, "weekly-2")

        result = rotate_weekly_challenges()

        assert result.startswith("created:")
        assert Challenge.objects.filter(
            template__challenge_type=ChallengeTemplate.ChallengeType.WEEKLY
        ).exists()

    def test_expires_active_weekly_challenges(self):
        """Existing ACTIVE weekly challenges should be expired before new ones."""
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.WEEKLY, "weekly-expire"
        )
        old_challenge = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(days=8),
            ends_at=timezone.now() - timedelta(hours=1),
        )

        rotate_weekly_challenges()

        old_challenge.refresh_from_db()
        assert old_challenge.status == Challenge.Status.EXPIRED

    def test_creates_at_most_weekly_count_challenges(self):
        """Should create at most 2 weekly challenges (WEEKLY_COUNT)."""
        for i in range(4):
            _make_challenge_template(
                ChallengeTemplate.ChallengeType.WEEKLY, f"weekly-max-{i}"
            )

        rotate_weekly_challenges()

        count = Challenge.objects.filter(
            template__challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
            status=Challenge.Status.ACTIVE,
        ).count()
        assert count <= 2

    def test_no_templates_returns_zero_created(self):
        """With no weekly templates, task should return created: 0."""
        result = rotate_weekly_challenges()
        assert result == "created: 0"

    def test_uses_fallback_when_all_templates_recently_used(self):
        """When all templates recently used, fall back to full pool."""
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.WEEKLY, "weekly-recently-used"
        )
        # Mark as recently used
        Challenge.objects.create(
            template=template,
            status=Challenge.Status.EXPIRED,
            starts_at=timezone.now() - timedelta(days=7),
            ends_at=timezone.now() - timedelta(hours=1),
        )

        result = rotate_weekly_challenges()
        # Should still work via fallback
        assert result.startswith("created:")


@pytest.mark.django_db
class TestExpireChallenges:
    def test_expires_overdue_active_challenges(self):
        """Challenges that have passed their ends_at should be marked EXPIRED."""
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "expire-overdue"
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
        """Challenges with future ends_at should not be expired."""
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

    def test_no_overdue_challenges_returns_zero(self):
        """With no overdue challenges, task should return expired: 0."""
        result = expire_challenges()
        assert result == "expired: 0"

    def test_fails_in_progress_user_challenges_on_expire(self):
        """IN_PROGRESS UserChallenges should be FAILED when challenge expires."""
        template = _make_challenge_template(
            ChallengeTemplate.ChallengeType.DAILY, "expire-user-challenges"
        )
        overdue = Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now() - timedelta(hours=25),
            ends_at=timezone.now() - timedelta(hours=1),
        )
        user = UserFactory()
        user_challenge = UserChallenge.objects.create(
            user=user,
            challenge=overdue,
            status=UserChallenge.Status.IN_PROGRESS,
            progress=2,
            target=3,
        )

        expire_challenges()

        user_challenge.refresh_from_db()
        assert user_challenge.status == UserChallenge.Status.FAILED
