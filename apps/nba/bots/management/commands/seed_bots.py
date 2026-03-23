"""
Management command to create bot users and their BotProfiles.

Usage:
    python manage.py seed_bots           # Create bots (idempotent)
    python manage.py seed_bots --reset   # Wipe and re-create
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from games.models import Team

from bots.models import BotProfile
from bots.personas import BOT_PERSONAS
from vinosports.betting.models import UserBalance, UserStats
from vinosports.users.models import User


class Command(BaseCommand):
    help = "Create bot users and BotProfiles for the NBA betting simulation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing bot profiles and re-create them.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            deleted, _ = BotProfile.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing BotProfile(s).")

        created = 0
        updated = 0

        for persona in BOT_PERSONAS:
            email = f"{persona['slug']}@bot.vinosports.nba"

            user, user_created = User.objects.get_or_create(
                email=email,
                defaults={
                    "display_name": persona["display_name"],
                    "is_bot": True,
                    "avatar_bg": persona["avatar_bg"],
                },
            )
            if user_created:
                user.set_unusable_password()
                user.save()

            UserBalance.objects.get_or_create(
                user=user, defaults={"balance": Decimal("1000.00")}
            )
            UserStats.objects.get_or_create(user=user)

            # Resolve favorite team
            favorite_team = None
            if persona["favorite_team_abbr"]:
                favorite_team = Team.objects.filter(
                    abbreviation=persona["favorite_team_abbr"]
                ).first()
                if not favorite_team:
                    self.stderr.write(
                        f"  Warning: Team '{persona['favorite_team_abbr']}' not found "
                        f"for {persona['display_name']}. Skipping favorite_team."
                    )

            _, profile_created = BotProfile.objects.update_or_create(
                user=user,
                defaults={
                    "strategy_type": persona["strategy"],
                    "persona_prompt": persona["persona_prompt"],
                    "favorite_team": favorite_team,
                    "risk_multiplier": persona["risk_multiplier"],
                    "max_daily_bets": persona["max_daily_bets"],
                    "is_active": True,
                },
            )

            if profile_created:
                created += 1
            else:
                updated += 1

            self.stdout.write(
                f"  {'Created' if profile_created else 'Updated'}: {persona['display_name']}"
            )

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created {created}, updated {updated} bot(s).")
        )
