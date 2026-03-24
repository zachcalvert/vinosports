"""
Backfill correct final scores for NBA games from the sportsdata.io API.

The /Games/{season} endpoint returns unreliable score data, so this command
fetches scores per-date using the /GamesByDate/{date} endpoint which returns
accurate final scores.
"""

import time

from django.core.management.base import BaseCommand
from django.db.models import F

from games.models import Game, GameStatus
from games.services import NBADataClient


class Command(BaseCommand):
    help = "Backfill correct final scores for games with stale/partial scores"

    def add_arguments(self, parser):
        parser.add_argument(
            "--threshold",
            type=int,
            default=150,
            help="Combined score threshold below which a game is considered stale (default: 150)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        threshold = options["threshold"]
        dry_run = options["dry_run"]

        # Find FINAL games with suspiciously low scores
        stale_games = list(
            Game.objects.filter(status=GameStatus.FINAL)
            .exclude(home_score__isnull=True)
            .annotate(total=F("home_score") + F("away_score"))
            .filter(total__lt=threshold)
            .select_related("home_team", "away_team")
            .order_by("game_date")
        )

        if not stale_games:
            self.stdout.write(self.style.SUCCESS("No stale scores found."))
            return

        self.stdout.write(
            f"Found {len(stale_games)} FINAL games with combined score < {threshold}"
        )

        # Group by game_date — one API call per date
        dates = sorted({g.game_date for g in stale_games})
        self.stdout.write(f"Dates to fetch: {len(dates)} ({dates[0]} to {dates[-1]})")

        if dry_run:
            for g in stale_games[-20:]:
                self.stdout.write(
                    f"  {g.game_date} {g.away_team.abbreviation} {g.away_score}"
                    f" @ {g.home_team.abbreviation} {g.home_score}"
                    f" (total={g.home_score + g.away_score})"
                )
            if len(stale_games) > 20:
                self.stdout.write(f"  ... and {len(stale_games) - 20} more")
            self.stdout.write(self.style.WARNING("Dry run — no changes made."))
            return

        # Build lookup: external_id → Game object
        stale_by_ext_id = {g.external_id: g for g in stale_games}

        updated = 0
        errors = 0
        with NBADataClient() as client:
            for i, game_date in enumerate(dates):
                try:
                    api_games = client.get_games(
                        season=0,  # ignored when game_date is provided
                        game_date=game_date,
                    )
                except Exception as e:
                    self.stderr.write(f"  API error for {game_date}: {e}")
                    errors += 1
                    time.sleep(2)
                    continue

                api_lookup = {g["external_id"]: g for g in api_games}

                for ext_id, game_obj in stale_by_ext_id.items():
                    if game_obj.game_date != game_date:
                        continue
                    api_data = api_lookup.get(ext_id)
                    if not api_data:
                        continue

                    new_home = api_data["home_score"]
                    new_away = api_data["away_score"]
                    if new_home is None or new_away is None:
                        continue

                    Game.objects.filter(pk=game_obj.pk).update(
                        home_score=new_home,
                        away_score=new_away,
                        status=api_data["status"],
                    )
                    updated += 1

                if (i + 1) % 10 == 0:
                    self.stdout.write(
                        f"  Processed {i + 1}/{len(dates)} dates ({updated} updated)"
                    )

                # Rate limit: ~1 req/sec
                time.sleep(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nBackfill complete: {updated} games updated, {errors} API errors."
            )
        )
