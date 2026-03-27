"""Tests for website/management/commands/seed_challenges.py."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from vinosports.challenges.models import Challenge, ChallengeTemplate

pytestmark = pytest.mark.django_db


def _make_template(challenge_type, slug, is_active=True):
    return ChallengeTemplate.objects.create(
        slug=slug,
        title=f"Test {slug}",
        description="A test challenge",
        icon="star",
        challenge_type=challenge_type,
        criteria_type=ChallengeTemplate.CriteriaType.BET_COUNT,
        criteria_params={"target": 3},
        reward_amount="50.00",
        is_active=is_active,
    )


class TestSeedChallengesCommand:
    def test_creates_daily_challenges_for_epl(self):
        for i in range(4):
            _make_template(ChallengeTemplate.ChallengeType.DAILY, f"daily-epl-{i}")

        call_command("seed_challenges")

        count = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
            template__challenge_type=ChallengeTemplate.ChallengeType.DAILY,
        ).exclude(template__slug__startswith="nba-").count()
        assert count == 3

    def test_creates_daily_challenges_for_nba(self):
        for i in range(4):
            _make_template(ChallengeTemplate.ChallengeType.DAILY, f"nba-daily-{i}")

        call_command("seed_challenges")

        count = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
            template__challenge_type=ChallengeTemplate.ChallengeType.DAILY,
            template__slug__startswith="nba-",
        ).count()
        assert count == 3

    def test_creates_weekly_challenges_for_epl(self):
        for i in range(3):
            _make_template(ChallengeTemplate.ChallengeType.WEEKLY, f"weekly-epl-{i}")

        call_command("seed_challenges")

        count = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
            template__challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
        ).exclude(template__slug__startswith="nba-").count()
        assert count == 2

    def test_creates_weekly_challenges_for_nba(self):
        for i in range(3):
            _make_template(ChallengeTemplate.ChallengeType.WEEKLY, f"nba-weekly-{i}")

        call_command("seed_challenges")

        count = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
            template__challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
            template__slug__startswith="nba-",
        ).count()
        assert count == 2

    def test_skips_epl_daily_when_already_active(self):
        template = _make_template(
            ChallengeTemplate.ChallengeType.DAILY, "daily-epl-skip"
        )
        Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=12),
        )

        call_command("seed_challenges")

        # Should still be exactly 1 (not duplicated)
        count = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
            template__challenge_type=ChallengeTemplate.ChallengeType.DAILY,
        ).exclude(template__slug__startswith="nba-").count()
        assert count == 1

    def test_skips_nba_weekly_when_already_active(self):
        template = _make_template(
            ChallengeTemplate.ChallengeType.WEEKLY, "nba-weekly-skip"
        )
        Challenge.objects.create(
            template=template,
            status=Challenge.Status.ACTIVE,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=5),
        )

        call_command("seed_challenges")

        count = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
            template__challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
            template__slug__startswith="nba-",
        ).count()
        assert count == 1

    def test_no_output_error_when_no_templates(self, capsys):
        call_command("seed_challenges")
        # Should complete without raising an exception
        assert Challenge.objects.count() == 0

    def test_creates_at_most_daily_count_per_league(self):
        for i in range(10):
            _make_template(ChallengeTemplate.ChallengeType.DAILY, f"daily-epl-{i}")
        for i in range(10):
            _make_template(ChallengeTemplate.ChallengeType.DAILY, f"nba-daily-{i}")

        call_command("seed_challenges")

        epl_count = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
            template__challenge_type=ChallengeTemplate.ChallengeType.DAILY,
        ).exclude(template__slug__startswith="nba-").count()
        nba_count = Challenge.objects.filter(
            status=Challenge.Status.ACTIVE,
            template__challenge_type=ChallengeTemplate.ChallengeType.DAILY,
            template__slug__startswith="nba-",
        ).count()
        assert epl_count == 3
        assert nba_count == 3

    def test_created_challenges_are_active(self):
        _make_template(ChallengeTemplate.ChallengeType.DAILY, "daily-epl-active")
        _make_template(ChallengeTemplate.ChallengeType.WEEKLY, "weekly-epl-active")

        call_command("seed_challenges")

        for challenge in Challenge.objects.all():
            assert challenge.status == Challenge.Status.ACTIVE

    def test_idempotent_across_multiple_runs(self):
        for i in range(5):
            _make_template(ChallengeTemplate.ChallengeType.DAILY, f"daily-epl-idem-{i}")
        for i in range(5):
            _make_template(ChallengeTemplate.ChallengeType.WEEKLY, f"weekly-epl-idem-{i}")

        call_command("seed_challenges")
        first_run_count = Challenge.objects.count()

        call_command("seed_challenges")
        second_run_count = Challenge.objects.count()

        assert first_run_count == second_run_count
