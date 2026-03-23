from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from betting.odds_engine import generate_all_upcoming_odds
from matches.models import Odds
from matches.services import sync_matches, sync_standings, sync_teams


class Command(BaseCommand):
    help = "Seed the database with EPL data from football-data.org and generate house odds"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            default=settings.CURRENT_SEASON,
            help="Season start year, e.g. 2025 for 2025-26 (default: %(default)s)",
        )
        parser.add_argument(
            "--skip-odds",
            action="store_true",
            help="Skip generating odds",
        )
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Seed from bundled static JSON instead of calling APIs",
        )

    def handle(self, *args, **options):
        season = options["season"]
        offline = options["offline"]
        skip_odds = options["skip_odds"]
        mode = "offline" if offline else "live"

        self.stdout.write(f"Seeding EPL data (season={season}, mode={mode})")
        self.stdout.write("")

        # Teams
        self.stdout.write("Syncing teams...")
        created, updated = sync_teams(season, offline=offline)
        self.stdout.write(
            self.style.SUCCESS(f"  Teams: {created} created, {updated} updated")
        )

        # Matches
        self.stdout.write("Syncing matches...")
        created, updated = sync_matches(season, offline=offline)
        self.stdout.write(
            self.style.SUCCESS(f"  Matches: {created} created, {updated} updated")
        )

        # Standings
        self.stdout.write("Syncing standings...")
        created, updated = sync_standings(season, offline=offline)
        self.stdout.write(
            self.style.SUCCESS(
                f"  Standings: {created} created, {updated} updated"
            )
        )

        # Odds
        if skip_odds:
            self.stdout.write(self.style.WARNING("  Odds: skipped (--skip-odds)"))
        else:
            self.stdout.write("Generating house odds...")
            results = generate_all_upcoming_odds(season)
            now = timezone.now()
            created = 0
            for r in results:
                _, was_created = Odds.objects.update_or_create(
                    match=r["match"],
                    bookmaker="House",
                    defaults={
                        "home_win": r["home_win"],
                        "draw": r["draw"],
                        "away_win": r["away_win"],
                        "fetched_at": now,
                    },
                )
                if was_created:
                    created += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Odds: {created} generated for {len(results)} matches"
                )
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done!"))
