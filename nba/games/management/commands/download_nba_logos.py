"""Download NBA team logos from logo_url and save them to team_logo ImageField."""

import urllib.request

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from nba.games.models import Team


class Command(BaseCommand):
    help = "Download team logos from logo_url into team_logo for all NBA teams"

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Re-download even if team_logo is already set",
        )

    def handle(self, *args, **options):
        teams = Team.objects.exclude(logo_url="")
        if not options["overwrite"]:
            teams = teams.filter(team_logo="")

        total = teams.count()
        if total == 0:
            self.stdout.write("No teams to process.")
            return

        success = 0
        for team in teams:
            try:
                req = urllib.request.Request(
                    team.logo_url,
                    headers={"User-Agent": "vinosports/1.0"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()

                ext = "svg" if "svg" in team.logo_url else "png"
                filename = f"{team.abbreviation.lower()}.{ext}"
                team.team_logo.save(filename, ContentFile(data), save=True)
                success += 1
                self.stdout.write(f"  OK  {team.abbreviation} -> {team.team_logo.name}")
            except Exception as e:
                self.stderr.write(f"  FAIL  {team.abbreviation}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Downloaded {success}/{total} logos."))
