"""Seed World Cup data — teams, groups, stages, matches, standings, odds."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed World Cup 2026 data from football-data.org or static JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Use bundled static JSON instead of API calls",
        )
        parser.add_argument(
            "--skip-odds",
            action="store_true",
            help="Skip odds generation",
        )

    def handle(self, *args, **options):
        offline = options["offline"]
        skip_odds = options["skip_odds"]

        from worldcup.matches.services import (
            sync_groups,
            sync_matches,
            sync_stages,
            sync_standings,
            sync_teams,
        )

        self.stdout.write("Syncing stages...")
        count = sync_stages()
        self.stdout.write(self.style.SUCCESS(f"  {count} stages"))

        self.stdout.write("Syncing teams...")
        created, updated = sync_teams(offline=offline)
        self.stdout.write(self.style.SUCCESS(f"  {created} created, {updated} updated"))

        self.stdout.write("Syncing groups...")
        count = sync_groups()
        self.stdout.write(self.style.SUCCESS(f"  {count} groups"))

        self.stdout.write("Syncing matches...")
        created, updated = sync_matches(offline=offline)
        self.stdout.write(self.style.SUCCESS(f"  {created} created, {updated} updated"))

        self.stdout.write("Syncing standings...")
        created, updated = sync_standings(offline=offline)
        self.stdout.write(self.style.SUCCESS(f"  {created} created, {updated} updated"))

        if not skip_odds:
            self.stdout.write("Generating odds...")
            from worldcup.betting.odds_engine import generate_all_upcoming_odds

            count = generate_all_upcoming_odds()
            self.stdout.write(self.style.SUCCESS(f"  {count} matches"))

        self.stdout.write(self.style.SUCCESS("World Cup seed complete!"))
