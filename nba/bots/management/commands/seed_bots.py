"""
Management command to create bot users, their BotProfiles, and schedule templates.

Usage:
    python manage.py seed_bots           # Create bots (idempotent)
    python manage.py seed_bots --reset   # Wipe and re-create
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from nba.bots.personas import BOT_PERSONAS
from nba.games.models import Team
from vinosports.betting.models import UserBalance, UserStats
from vinosports.bots.models import BotProfile, ScheduleTemplate
from vinosports.users.models import User

SCHEDULE_TEMPLATES = [
    {
        "slug": "nine-to-five-grinder",
        "name": "9 to 5 Grinder",
        "description": (
            "Logs on in the morning, comments and maybe bets, disappears for 8 hours, "
            "then does the same after work. Every day."
        ),
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": [8, 9],
                "bet_probability": 0.4,
                "comment_probability": 0.7,
                "max_bets": 1,
                "max_comments": 1,
            },
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": [17, 18],
                "bet_probability": 0.4,
                "comment_probability": 0.7,
                "max_bets": 1,
                "max_comments": 1,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
    {
        "slug": "heavy-bettor-lurker",
        "name": "Heavy Bettor / Lurker",
        "description": (
            "Bets on every game every day but only comments once a week at most."
        ),
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": list(range(11, 24)),
                "bet_probability": 0.9,
                "comment_probability": 0.03,
                "max_bets": 6,
                "max_comments": 1,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
    {
        "slug": "heavy-commenter-light-bettor",
        "name": "Heavy Commenter / Light Bettor",
        "description": ("Talks a lot, bets sparingly. The forum regular."),
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": list(range(10, 23)),
                "bet_probability": 0.1,
                "comment_probability": 0.7,
                "max_bets": 1,
                "max_comments": 4,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
    {
        "slug": "postseason-fan",
        "name": "Postseason Fan",
        "description": (
            "Only shows up for the playoffs. Set active_from/active_to dates "
            "to the playoff window each season."
        ),
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": list(range(12, 24)),
                "bet_probability": 0.6,
                "comment_probability": 0.5,
                "max_bets": 3,
                "max_comments": 2,
            },
        ],
        # 2025-26 NBA playoffs (approximate — update each season)
        "active_from": "2026-04-18",
        "active_to": "2026-06-22",
    },
    {
        "slug": "night-owl",
        "name": "Night Owl",
        "description": (
            "Active late, watches West Coast games. Lives for the late slate."
        ),
        "windows": [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": [20, 21, 22, 23, 0, 1],
                "bet_probability": 0.5,
                "comment_probability": 0.6,
                "max_bets": 3,
                "max_comments": 2,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
    {
        "slug": "weekend-warrior",
        "name": "Weekend Warrior",
        "description": ("Casual fan, only active Friday through Sunday."),
        "windows": [
            {
                "days": [4, 5, 6],  # Fri, Sat, Sun
                "hours": list(range(12, 23)),
                "bet_probability": 0.5,
                "comment_probability": 0.5,
                "max_bets": 3,
                "max_comments": 2,
            },
        ],
        "active_from": None,
        "active_to": None,
    },
]


class Command(BaseCommand):
    help = "Create bot users, BotProfiles, and schedule templates for the NBA betting simulation."

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

        # --- Seed schedule templates ---
        templates_created = 0
        template_map = {}
        for tpl_data in SCHEDULE_TEMPLATES:
            tpl, created = ScheduleTemplate.objects.update_or_create(
                slug=tpl_data["slug"],
                defaults={
                    "name": tpl_data["name"],
                    "description": tpl_data["description"],
                    "windows": tpl_data["windows"],
                    "active_from": tpl_data["active_from"],
                    "active_to": tpl_data["active_to"],
                },
            )
            template_map[tpl_data["slug"]] = tpl
            if created:
                templates_created += 1
            self.stdout.write(
                f"  {'Created' if created else 'Updated'} template: {tpl.name}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Schedule templates: {templates_created} created, "
                f"{len(SCHEDULE_TEMPLATES) - templates_created} updated."
            )
        )

        # --- Seed bot profiles ---
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

            # Resolve schedule template
            schedule_template = None
            tpl_slug = persona.get("schedule_template_slug")
            if tpl_slug:
                schedule_template = template_map.get(tpl_slug)
                if not schedule_template:
                    self.stderr.write(
                        f"  Warning: Template '{tpl_slug}' not found "
                        f"for {persona['display_name']}."
                    )

            _, profile_created = BotProfile.objects.update_or_create(
                user=user,
                defaults={
                    "strategy_type": persona["strategy"],
                    "persona_prompt": persona["persona_prompt"],
                    "favorite_team": favorite_team,
                    "risk_multiplier": persona["risk_multiplier"],
                    "max_daily_bets": persona["max_daily_bets"],
                    "schedule_template": schedule_template,
                    "is_active": True,
                },
            )

            if profile_created:
                created += 1
            else:
                updated += 1

            self.stdout.write(
                f"  {'Created' if profile_created else 'Updated'}: {persona['display_name']}"
                f" [{tpl_slug or 'always-on'}]"
            )

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created {created}, updated {updated} bot(s).")
        )
