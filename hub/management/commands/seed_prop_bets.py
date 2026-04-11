from decimal import Decimal

from django.core.management.base import BaseCommand

from vinosports.betting.models import PropBet, PropBetStatus
from vinosports.users.models import User

PROP_DEFINITIONS = [
    {
        "title": "Will any EPL match this weekend end 0-0?",
        "description": "At least one Premier League fixture finishing as a goalless draw.",
        "yes_odds": Decimal("3.500"),
        "no_odds": Decimal("1.300"),
    },
    {
        "title": "Will an NBA player score 50+ points tonight?",
        "description": "Any player across all games tonight reaching 50 or more points.",
        "yes_odds": Decimal("5.000"),
        "no_odds": Decimal("1.150"),
    },
    {
        "title": "Will the NFL draft's #1 pick be a quarterback?",
        "description": "First overall selection in the upcoming NFL draft is a QB.",
        "yes_odds": Decimal("1.400"),
        "no_odds": Decimal("2.800"),
    },
    {
        "title": "Will there be overtime in any Champions League match this week?",
        "description": "Extra time played in any UCL fixture this matchweek.",
        "yes_odds": Decimal("2.200"),
        "no_odds": Decimal("1.650"),
    },
    {
        "title": "Will Vinosports add a new league before the end of the month?",
        "description": "A new league section (not just a page) goes live on vinosports.com.",
        "yes_odds": Decimal("4.000"),
        "no_odds": Decimal("1.220"),
    },
]


class Command(BaseCommand):
    help = "Seed sample prop bets for development"

    def handle(self, *args, **options):
        # Use the first superuser as creator, fall back to first user
        creator = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not creator:
            self.stderr.write(self.style.ERROR("  No users found. Run seed first."))
            return

        created = 0
        skipped = 0

        for defn in PROP_DEFINITIONS:
            if PropBet.objects.filter(title=defn["title"]).exists():
                skipped += 1
                continue

            PropBet.objects.create(
                title=defn["title"],
                description=defn["description"],
                creator=creator,
                status=PropBetStatus.OPEN,
                yes_odds=defn["yes_odds"],
                no_odds=defn["no_odds"],
            )
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  Prop bets: {created} created, {skipped} skipped (already exist)"
            )
        )
