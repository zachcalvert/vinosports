"""
Management command: seed_nba

Usage:
  python manage.py seed_nba              # fetch from live API
  python manage.py seed_nba --offline    # load from static_data fixtures (no API key needed)
  python manage.py seed_nba --season 2024
"""

import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

STATIC_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "static_data"


class Command(BaseCommand):
    help = (
        "Seed NBA teams, schedule, and standings from the data API or static fixtures."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Load from static fixture files instead of hitting the API.",
        )
        parser.add_argument(
            "--season",
            type=int,
            default=None,
            help="Season year to sync (default: current season).",
        )
        parser.add_argument(
            "--teams-only",
            action="store_true",
            help="Only sync teams.",
        )
        parser.add_argument(
            "--skip-odds",
            action="store_true",
            help="Skip house odds generation.",
        )

    def handle(self, *args, **options):
        offline = options["offline"]
        season = options["season"] or self._current_season()
        teams_only = options["teams_only"]
        skip_odds = options["skip_odds"]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Seeding NBA data (season={season}, offline={offline})"
            )
        )

        if offline:
            self._seed_offline(season, teams_only)
        else:
            self._seed_live(season, teams_only)

        if not teams_only and not skip_odds:
            self._generate_odds(season)

    def _seed_offline(self, season: int, teams_only: bool):
        from games.models import Team

        teams_file = STATIC_DATA_DIR / "teams.json"
        if not teams_file.exists():
            self.stderr.write(self.style.ERROR(f"Missing fixture: {teams_file}"))
            return

        teams_data = json.loads(teams_file.read_text())
        count = 0
        for t in teams_data:
            conf_raw = t.get("conference", "")
            conference = "EAST" if conf_raw.lower().startswith("e") else "WEST"
            Team.objects.update_or_create(
                external_id=t["id"],
                defaults={
                    "name": t["name"],
                    "short_name": t["full_name"],
                    "abbreviation": t["abbreviation"],
                    "conference": conference,
                    "division": t.get("division", ""),
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"  Teams: {count} upserted"))

        if teams_only:
            return

        self.stdout.write(
            self.style.WARNING(
                "  Schedule + standings: no offline fixtures available. "
                "Run without --offline to fetch from the API."
            )
        )

    def _seed_live(self, season: int, teams_only: bool):
        from games.services import sync_games, sync_standings, sync_teams

        self.stdout.write("  Syncing teams...")
        count = sync_teams()
        self.stdout.write(self.style.SUCCESS(f"  Teams: {count} synced"))

        if teams_only:
            return

        self.stdout.write("  Syncing schedule...")
        count = sync_games(season)
        self.stdout.write(
            self.style.SUCCESS(f"  Games: {count} synced (season={season})")
        )

        self.stdout.write("  Syncing standings...")
        try:
            count = sync_standings(season)
            self.stdout.write(
                self.style.SUCCESS(f"  Standings: {count} synced (season={season})")
            )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  Standings: skipped ({exc})"))

    def _generate_odds(self, season: int):
        from betting.odds_engine import generate_all_upcoming_odds

        from games.models import Odds

        self.stdout.write("  Generating house odds...")
        results = generate_all_upcoming_odds(season)
        count = 0
        for r in results:
            game = r.pop("game")
            Odds.objects.update_or_create(
                game=game,
                bookmaker="House",
                defaults={**r, "fetched_at": timezone.now()},
            )
            count += 1
        self.stdout.write(
            self.style.SUCCESS(f"  Odds: {count} games (season={season})")
        )

    def _current_season(self) -> int:
        """BDL uses the start year: 2025-26 season = '2025'."""
        today = timezone.now().date()
        return today.year if today.month >= 10 else today.year - 1
