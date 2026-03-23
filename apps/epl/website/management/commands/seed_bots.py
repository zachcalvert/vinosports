from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from bots.models import BotProfile
from bots.personas import BOT_PERSONA_PROMPTS
from bots.registry import BOT_PROFILES, STRATEGY_TYPE_TO_CLASS
from vinosports.betting.models import UserBalance

User = get_user_model()

# Reverse lookup: strategy class -> strategy_type string
CLASS_TO_STRATEGY_TYPE = {cls: key for key, cls in STRATEGY_TYPE_TO_CLASS.items()}

STARTING_BALANCE = Decimal("10000.00")


class Command(BaseCommand):
    help = "Seed bot user accounts, BotProfile rows, and starting balances"

    def handle(self, *args, **options):
        created_users = 0
        created_profiles = 0

        for profile in BOT_PROFILES:
            email = profile["email"]
            display_name = profile["display_name"]

            user, user_created = User.objects.get_or_create(
                email=email,
                defaults={
                    "display_name": display_name,
                    "is_bot": True,
                    "is_active": True,
                    "avatar_icon": profile["avatar_icon"],
                    "avatar_bg": profile["avatar_bg"],
                },
            )
            if user_created:
                user.set_unusable_password()
                user.save()
                created_users += 1

            strategy_type = CLASS_TO_STRATEGY_TYPE.get(profile["strategy"], "")
            persona_prompt = BOT_PERSONA_PROMPTS.get(email, "")

            _, profile_created = BotProfile.objects.update_or_create(
                user=user,
                defaults={
                    "strategy_type": strategy_type,
                    "team_tla": profile.get("team_tla", ""),
                    "persona_prompt": persona_prompt,
                    "avatar_icon": profile["avatar_icon"],
                    "avatar_bg": profile["avatar_bg"],
                    "is_active": True,
                },
            )
            if profile_created:
                created_profiles += 1

            UserBalance.objects.get_or_create(
                user=user, defaults={"balance": STARTING_BALANCE}
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"  Bots: {created_users} users created, "
                f"{created_profiles} profiles created, "
                f"{len(BOT_PROFILES)} total"
            )
        )
