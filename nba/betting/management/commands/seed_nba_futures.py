"""
Management command: seed_futures (NBA)

Creates futures markets (Champion, Conference Winner) for the current season
with outcomes for all teams. Runs the odds engine to generate initial odds.

Usage:
  python manage.py seed_futures
  python manage.py seed_futures --season 2025
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from nba.betting.futures_odds_engine import generate_futures_odds
from nba.betting.models import FuturesMarket, FuturesOutcome
from nba.games.models import Standing, Team
from vinosports.betting.models import FuturesMarketStatus

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Seed NBA futures markets with outcomes for all teams"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            default=None,
            help="Season to create markets for (default: current season)",
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        season = options["season"] or (
            today.year if today.month >= 10 else today.year - 1
        )
        season_str = str(season)

        teams = list(Team.objects.all())
        if not teams:
            self.stderr.write(self.style.ERROR("No teams found. Run seed_nba first."))
            return

        self.stdout.write(
            f"Seeding NBA futures for season {season} ({len(teams)} teams)..."
        )

        # Champion market — all teams
        self._seed_market(
            season_str,
            season,
            "CHAMPION",
            f"NBA Champion {season}-{str(season + 1)[-2:]}",
            teams,
            conference="",
        )

        # Conference markets — filtered by conference
        for conf in ["EAST", "WEST"]:
            conf_teams = [
                t
                for t in teams
                if Standing.objects.filter(
                    team=t, season=season, conference=conf
                ).exists()
            ]
            if not conf_teams:
                # Fallback: include all teams if standings not available
                conf_teams = teams

            self._seed_market(
                season_str,
                season,
                "CONFERENCE",
                f"{conf.title()}ern Conference Winner {season}-{str(season + 1)[-2:]}",
                conf_teams,
                conference=conf,
            )

        self.stdout.write(self.style.SUCCESS("NBA futures seeding complete."))

    def _seed_market(
        self, season_str, season_int, market_type, name, teams, conference
    ):
        market, created = FuturesMarket.objects.update_or_create(
            season=season_str,
            market_type=market_type,
            conference=conference,
            defaults={
                "name": name,
                "status": FuturesMarketStatus.OPEN,
            },
        )
        action = "Created" if created else "Updated"
        self.stdout.write(f"  {action} market: {name}")

        odds_results = generate_futures_odds(season_int, market_type, conference)
        odds_map = {r["team_id"]: r["odds"] for r in odds_results}

        now = timezone.now()
        for team in teams:
            odds = odds_map.get(team.pk, 5000)  # fallback long-shot odds

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
