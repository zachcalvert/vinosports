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

# Keyed by BDL external_id
TEAM_LOGOS = {
    1: "https://i.logocdn.com/nba/2015/atlanta-hawks@3x.png",
    2: "https://i.logocdn.com/nba/1976/boston-celtics@3x.png",
    3: "https://i.logocdn.com/nba/1990/new-jersey-nets@3x.png",
    4: "https://i.logocdn.com/nba/1988/charlotte-hornets@3x.png",
    5: "https://i.logocdn.com/nba/1966/chicago-bulls.svg",
    6: "https://i.logocdn.com/nba/1994/cleveland-cavaliers@3x.png",
    7: "https://i.logocdn.com/nba/2001/dallas-mavericks@3x.png",
    8: "https://i.logocdn.com/nba/1993/denver-nuggets@3x.png",
    9: "https://i.logocdn.com/nba/1979/detroit-pistons@3x.png",
    10: "https://i.logocdn.com/nba/1988/golden-state-warriors@3x.png",
    11: "https://i.logocdn.com/nba/1972/houston-rockets@3x.png",
    12: "https://i.logocdn.com/nba/2005/indiana-pacers@3x.png",
    13: "https://i.logocdn.com/nba/2010/los-angeles-clippers@3x.png",
    14: "https://i.logocdn.com/nba/2001/los-angeles-lakers@3x.png",
    15: "https://i.logocdn.com/nba/2001/memphis-grizzlies@3x.png",
    16: "https://i.logocdn.com/nba/1999/miami-heat.svg",
    17: "https://i.logocdn.com/nba/1993/milwaukee-bucks@3x.png",
    18: "https://i.logocdn.com/nba/1996/minnesota-timberwolves@3x.png",
    19: "https://i.logocdn.com/nba/2023/new-orleans-pelicans.svg",
    20: "https://i.logocdn.com/nba/1995/new-york-knicks@3x.png",
    21: "https://i.logocdn.com/nba/current/oklahoma-city-thunder.svg",
    22: "https://i.logocdn.com/nba/1989/orlando-magic@3x.png",
    23: "https://i.logocdn.com/nba/1977/philadelphia-76ers@3x.png",
    24: "https://i.logocdn.com/nba/1992/phoenix-suns@3x.png",
    25: "https://i.logocdn.com/nba/1970/portland-trail-blazers@3x.png",
    26: "https://i.logocdn.com/nba/1994/sacramento-kings@3x.png",
    27: "https://i.logocdn.com/nba/1989/san-antonio-spurs@3x.png",
    28: "https://i.logocdn.com/nba/1995/toronto-raptors@3x.png",
    29: "https://i.logocdn.com/nba/1979/utah-jazz@3x.png",
    30: "https://i.logocdn.com/nba/1997/washington-wizards@3x.png",
    37: "https://cdn.nba.com/logos/nba/37/global/L/logo.svg",
    38: "https://cdn.nba.com/logos/nba/38/global/L/logo.svg",
    39: "https://cdn.nba.com/logos/nba/39/global/L/logo.svg",
    40: "https://cdn.nba.com/logos/nba/40/global/L/logo.svg",
    41: "https://cdn.nba.com/logos/nba/41/global/L/logo.svg",
    42: "https://cdn.nba.com/logos/nba/42/global/L/logo.svg",
    43: "https://cdn.nba.com/logos/nba/43/global/L/logo.svg",
    44: "https://cdn.nba.com/logos/nba/44/global/L/logo.svg",
    45: "https://cdn.nba.com/logos/nba/45/global/L/logo.svg",
    46: "https://cdn.nba.com/logos/nba/46/global/L/logo.svg",
    47: "https://cdn.nba.com/logos/nba/47/global/L/logo.svg",
    48: "https://cdn.nba.com/logos/nba/48/global/L/logo.svg",
    49: "https://cdn.nba.com/logos/nba/49/global/L/logo.svg",
    50: "https://cdn.nba.com/logos/nba/50/global/L/logo.svg",
    51: "https://cdn.nba.com/logos/nba/51/global/L/logo.svg",
}


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

        self._set_logos()

        if not teams_only and not skip_odds:
            self._generate_odds(season)

    def _seed_offline(self, season: int, teams_only: bool):
        from nba.games.models import Team

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
        from nba.games.services import sync_games, sync_standings, sync_teams

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
        count = sync_standings(season)
        self.stdout.write(
            self.style.SUCCESS(f"  Standings: {count} synced (season={season})")
        )

    def _generate_odds(self, season: int):
        from nba.betting.odds_engine import generate_all_upcoming_odds
        from nba.games.models import Odds

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

    def _set_logos(self):
        from nba.games.models import Team

        count = Team.objects.filter(external_id__in=TEAM_LOGOS.keys()).count()
        for ext_id, url in TEAM_LOGOS.items():
            Team.objects.filter(external_id=ext_id).update(logo_url=url)
        self.stdout.write(self.style.SUCCESS(f"  Logos: {count} teams updated"))

    def _current_season(self) -> int:
        """BDL uses the start year: 2025-26 season = '2025'."""
        today = timezone.now().date()
        return today.year if today.month >= 10 else today.year - 1
