"""
Management command: seed_epl_futures (EPL)

Creates futures markets (Winner, Top 4, Relegation) for the current season
with outcomes for all teams. Runs the odds engine to generate initial odds.

Usage:
  python manage.py seed_epl_futures
  python manage.py seed_epl_futures --season 2025
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from epl.betting.futures_odds_engine import generate_futures_odds
from epl.betting.models import FuturesMarket, FuturesOutcome
from epl.matches.models import Team
from vinosports.betting.models import FuturesMarketStatus

logger = logging.getLogger(__name__)

MARKET_TYPES = [
    ("WINNER", "EPL Winner"),
    ("TOP_4", "Top 4 Finish"),
    ("RELEGATION", "Relegation"),
]


class Command(BaseCommand):
    help = "Seed EPL futures markets with outcomes for all teams"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=str,
            default=None,
            help="Season to create markets for (default: EPL_CURRENT_SEASON)",
        )

    def handle(self, *args, **options):
        season = options["season"] or settings.EPL_CURRENT_SEASON
        teams = list(Team.objects.all())

        if not teams:
            self.stderr.write(self.style.ERROR("No teams found. Run seed first."))
            return

        self.stdout.write(
            f"Seeding EPL futures for season {season} ({len(teams)} teams)..."
        )

        for market_type, name_template in MARKET_TYPES:
            market_name = f"{name_template} {season}"
            market, created = FuturesMarket.objects.update_or_create(
                season=season,
                market_type=market_type,
                defaults={
                    "name": market_name,
                    "status": FuturesMarketStatus.OPEN,
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action} market: {market_name}")

            # Generate odds from standings
            odds_results = generate_futures_odds(season, market_type)
            odds_map = {r["team_id"]: r["odds"] for r in odds_results}

            now = timezone.now()
            for team in teams:
                odds = odds_map.get(team.pk)
                if odds is None:
                    # Fallback for teams without standings
                    from decimal import Decimal

                    odds = Decimal("100.00")

                FuturesOutcome.objects.update_or_create(
                    market=market,
                    team=team,
                    defaults={
                        "odds": odds,
                        "is_active": True,
                        "odds_updated_at": now,
                    },
                )

            self.stdout.write(self.style.SUCCESS(f"    {len(teams)} outcomes seeded"))

        self.stdout.write(self.style.SUCCESS("EPL futures seeding complete."))
