"""
Master seed command — runs all individual seed/backfill commands in dependency order.
Safe to run multiple times; each sub-command uses update_or_create semantics.

Order:
  1. seed_epl              — teams, fixtures, standings, odds (external APIs)
  2. seed_challenge_templates — ChallengeTemplate rows
  3. seed_badges            — Badge rows
  4. seed_bots              — bot user accounts
  5. backfill_stats         — UserStats from existing bet history
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run all seed and backfill commands in dependency order"

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-epl",
            action="store_true",
            help="Skip seed_epl (skips external API calls)",
        )
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Pass --offline to seed_epl (use bundled JSON instead of live APIs)",
        )
        parser.add_argument(
            "--skip-odds",
            action="store_true",
            help="Pass --skip-odds to seed_epl (saves Odds API credits)",
        )

    def handle(self, *args, **options):
        verbosity = options["verbosity"]

        def section(label):
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n>>> {label}"))

        # 1. EPL data (teams, fixtures, standings, odds)
        if options["skip_epl"]:
            self.stdout.write(self.style.WARNING("Skipping seed_epl"))
        else:
            section("seed_epl")
            epl_kwargs = {"verbosity": verbosity}
            if options["offline"]:
                epl_kwargs["offline"] = True
            if options["skip_odds"]:
                epl_kwargs["skip_odds"] = True
            call_command("seed_epl", **epl_kwargs)

        # 2. Challenge templates
        section("seed_challenge_templates")
        call_command("seed_challenge_templates", verbosity=verbosity)

        # 3. Badges
        section("seed_badges")
        call_command("seed_badges", verbosity=verbosity)

        # 4. Bots
        section("seed_bots")
        call_command("seed_bots", verbosity=verbosity)

        # 5. Backfill stats (depends on bets existing; safe no-op if none)
        section("backfill_stats")
        call_command("backfill_stats", verbosity=verbosity)

        self.stdout.write(self.style.SUCCESS("\nAll seed commands complete."))
