"""
Management command: seed_nfl

Usage:
  python manage.py seed_nfl              # fetch from live API
  python manage.py seed_nfl --offline    # load from static_data fixtures (no API key needed)
  python manage.py seed_nfl --season 2024
"""

import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

STATIC_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "static_data"

# Team logos keyed by BDL external_id.
# ESPN CDN provides consistent, high-quality NFL team logos.
TEAM_LOGOS = {
    1: "https://a.espncdn.com/i/teamlogos/nfl/500/ne.png",
    3: "https://a.espncdn.com/i/teamlogos/nfl/500/buf.png",
    4: "https://a.espncdn.com/i/teamlogos/nfl/500/nyj.png",
    5: "https://a.espncdn.com/i/teamlogos/nfl/500/mia.png",
    6: "https://a.espncdn.com/i/teamlogos/nfl/500/bal.png",
    7: "https://a.espncdn.com/i/teamlogos/nfl/500/pit.png",
    8: "https://a.espncdn.com/i/teamlogos/nfl/500/cle.png",
    9: "https://a.espncdn.com/i/teamlogos/nfl/500/cin.png",
    10: "https://a.espncdn.com/i/teamlogos/nfl/500/hou.png",
    11: "https://a.espncdn.com/i/teamlogos/nfl/500/ten.png",
    12: "https://a.espncdn.com/i/teamlogos/nfl/500/ind.png",
    13: "https://a.espncdn.com/i/teamlogos/nfl/500/jax.png",
    14: "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png",
    15: "https://a.espncdn.com/i/teamlogos/nfl/500/den.png",
    16: "https://a.espncdn.com/i/teamlogos/nfl/500/lv.png",
    17: "https://a.espncdn.com/i/teamlogos/nfl/500/lac.png",
    18: "https://a.espncdn.com/i/teamlogos/nfl/500/phi.png",
    19: "https://a.espncdn.com/i/teamlogos/nfl/500/dal.png",
    20: "https://a.espncdn.com/i/teamlogos/nfl/500/nyg.png",
    21: "https://a.espncdn.com/i/teamlogos/nfl/500/wsh.png",
    22: "https://a.espncdn.com/i/teamlogos/nfl/500/gb.png",
    23: "https://a.espncdn.com/i/teamlogos/nfl/500/min.png",
    24: "https://a.espncdn.com/i/teamlogos/nfl/500/chi.png",
    25: "https://a.espncdn.com/i/teamlogos/nfl/500/det.png",
    26: "https://a.espncdn.com/i/teamlogos/nfl/500/no.png",
    27: "https://a.espncdn.com/i/teamlogos/nfl/500/atl.png",
    28: "https://a.espncdn.com/i/teamlogos/nfl/500/tb.png",
    29: "https://a.espncdn.com/i/teamlogos/nfl/500/car.png",
    30: "https://a.espncdn.com/i/teamlogos/nfl/500/sf.png",
    31: "https://a.espncdn.com/i/teamlogos/nfl/500/sea.png",
    32: "https://a.espncdn.com/i/teamlogos/nfl/500/lar.png",
    33: "https://a.espncdn.com/i/teamlogos/nfl/500/ari.png",
}


class Command(BaseCommand):
    help = (
        "Seed NFL teams, schedule, and standings from the data API or static fixtures."
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
            "--skip-players",
            action="store_true",
            help="Skip player sync (slow on free tier).",
        )

    def handle(self, *args, **options):
        offline = options["offline"]
        season = options["season"] or self._current_season()
        teams_only = options["teams_only"]
        skip_players = options["skip_players"]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Seeding NFL data (season={season}, offline={offline})"
            )
        )

        if offline:
            self._seed_offline(season, teams_only)
        else:
            self._seed_live(season, teams_only, skip_players)

        self._set_logos()

    def _seed_offline(self, season: int, teams_only: bool):
        from nfl.games.models import DIVISION_MAP, Division, Team

        teams_file = STATIC_DATA_DIR / "teams.json"
        if not teams_file.exists():
            self.stderr.write(self.style.ERROR(f"Missing fixture: {teams_file}"))
            return

        teams_data = json.loads(teams_file.read_text())
        count = 0
        for t in teams_data:
            conf = t.get("conference", "")
            div_raw = t.get("division", "")
            division = DIVISION_MAP.get((conf, div_raw), Division.AFC_EAST)
            Team.objects.update_or_create(
                external_id=t["id"],
                defaults={
                    "name": t.get("full_name", ""),
                    "short_name": t.get("name", ""),
                    "abbreviation": t.get("abbreviation", ""),
                    "location": t.get("location", ""),
                    "conference": conf,
                    "division": division,
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

    def _seed_live(self, season: int, teams_only: bool, skip_players: bool):
        from nfl.games.services import (
            compute_standings,
            sync_games,
            sync_players,
            sync_teams,
        )

        self.stdout.write("  Syncing teams...")
        count = sync_teams()
        self.stdout.write(self.style.SUCCESS(f"  Teams: {count} synced"))

        if teams_only:
            return

        self.stdout.write("  Syncing schedule...")
        count = sync_games(season, page_delay=1)
        self.stdout.write(
            self.style.SUCCESS(f"  Games: {count} synced (season={season})")
        )

        self.stdout.write("  Computing standings...")
        count = compute_standings(season)
        self.stdout.write(
            self.style.SUCCESS(f"  Standings: {count} computed (season={season})")
        )

        if not skip_players:
            self.stdout.write(
                "  Syncing players (this may take a while on free tier)..."
            )
            count = sync_players(
                page_delay=12,  # 5 req/min = one request every 12s
                on_page=lambda n: self.stdout.write(f"    ...{n} players fetched"),
            )
            self.stdout.write(self.style.SUCCESS(f"  Players: {count} synced"))

    def _set_logos(self):
        from nfl.games.models import Team

        count = Team.objects.filter(external_id__in=TEAM_LOGOS.keys()).count()
        for ext_id, url in TEAM_LOGOS.items():
            Team.objects.filter(external_id=ext_id).update(logo_url=url)
        self.stdout.write(self.style.SUCCESS(f"  Logos: {count} teams updated"))

    def _current_season(self) -> int:
        """NFL season = the year it starts (Sep). Mar-Aug = previous season."""
        today = timezone.now().date()
        return today.year if today.month >= 9 else today.year - 1
