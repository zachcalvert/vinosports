"""Management command to seed active Challenge instances for development.

Creates daily and weekly Challenge instances from existing ChallengeTemplate
records for both EPL and NBA leagues. Safe to run multiple times — each
league section is skipped when active challenges already exist for it.
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from vinosports.challenges.models import Challenge, ChallengeTemplate

DAILY_COUNT = 3
WEEKLY_COUNT = 2

LEAGUES = [
    {
        "label": "EPL",
        "template_filter": ~Q(slug__startswith="nba-"),
        "challenge_filter": ~Q(template__slug__startswith="nba-"),
    },
    {
        "label": "NBA",
        "template_filter": Q(slug__startswith="nba-"),
        "challenge_filter": Q(template__slug__startswith="nba-"),
    },
]


class Command(BaseCommand):
    help = "Seed active daily and weekly Challenge instances for EPL and NBA"

    def handle(self, *args, **options):
        for league in LEAGUES:
            self._seed_daily(league)
            self._seed_weekly(league)

    def _seed_daily(self, league):
        label = league["label"]
        template_filter = league["template_filter"]
        challenge_filter = league["challenge_filter"]

        existing = (
            Challenge.objects.filter(
                status=Challenge.Status.ACTIVE,
                template__challenge_type=ChallengeTemplate.ChallengeType.DAILY,
            )
            .filter(challenge_filter)
            .count()
        )

        if existing:
            self.stdout.write(
                f"  [{label}] Daily challenges: {existing} already active, skipping"
            )
            return

        templates = list(
            ChallengeTemplate.objects.filter(
                challenge_type=ChallengeTemplate.ChallengeType.DAILY,
                is_active=True,
            ).filter(template_filter)
        )

        if not templates:
            self.stdout.write(
                self.style.WARNING(
                    f"  [{label}] No daily templates found — run seed_challenge_templates first"
                )
            )
            return

        selected = random.sample(templates, min(DAILY_COUNT, len(templates)))

        now = timezone.now()
        ends_at = (now + timedelta(days=1)).replace(
            hour=5, minute=0, second=0, microsecond=0
        )

        for template in selected:
            Challenge.objects.create(
                template=template,
                status=Challenge.Status.ACTIVE,
                starts_at=now,
                ends_at=ends_at,
            )

        self.stdout.write(
            self.style.SUCCESS(f"  [{label}] Daily challenges: {len(selected)} created")
        )

    def _seed_weekly(self, league):
        label = league["label"]
        template_filter = league["template_filter"]
        challenge_filter = league["challenge_filter"]

        existing = (
            Challenge.objects.filter(
                status=Challenge.Status.ACTIVE,
                template__challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
            )
            .filter(challenge_filter)
            .count()
        )

        if existing:
            self.stdout.write(
                f"  [{label}] Weekly challenges: {existing} already active, skipping"
            )
            return

        templates = list(
            ChallengeTemplate.objects.filter(
                challenge_type=ChallengeTemplate.ChallengeType.WEEKLY,
                is_active=True,
            ).filter(template_filter)
        )

        if not templates:
            self.stdout.write(
                self.style.WARNING(
                    f"  [{label}] No weekly templates found — run seed_challenge_templates first"
                )
            )
            return

        selected = random.sample(templates, min(WEEKLY_COUNT, len(templates)))

        now = timezone.now()
        days_until_tuesday = (1 - now.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        ends_at = (now + timedelta(days=days_until_tuesday)).replace(
            hour=5, minute=0, second=0, microsecond=0
        )

        for template in selected:
            Challenge.objects.create(
                template=template,
                status=Challenge.Status.ACTIVE,
                starts_at=now,
                ends_at=ends_at,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"  [{label}] Weekly challenges: {len(selected)} created"
            )
        )
