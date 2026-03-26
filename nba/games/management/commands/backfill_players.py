"""
Management command: backfill_players

One-time bulk import of all NBA players from BallDontLie.
Uses a per-page delay to stay within API rate limits (~4500+ players).
After syncing, marks players with current-season box scores as active.

Usage:
  python manage.py backfill_players              # default 2s delay between pages
  python manage.py backfill_players --delay 1.0  # custom delay
"""

from django.core.management.base import BaseCommand

from nba.games.services import refresh_active_players, sync_players


class Command(BaseCommand):
    help = "Backfill all NBA players from BallDontLie (one-time bulk import)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delay",
            type=float,
            default=2.0,
            help="Seconds to wait between paginated API requests (default: 2.0).",
        )

    def handle(self, *args, **options):
        delay = options["delay"]
        self.stdout.write(
            self.style.MIGRATE_HEADING(f"Backfilling NBA players (page delay={delay}s)")
        )

        def on_page(total):
            self.stdout.write(f"  Fetched {total} players so far...")

        count = sync_players(page_delay=delay, on_page=on_page)
        self.stdout.write(self.style.SUCCESS(f"  Players: {count} synced"))

        self.stdout.write("  Refreshing active flags...")
        active = refresh_active_players()
        self.stdout.write(self.style.SUCCESS(f"  Active: {active} players"))
