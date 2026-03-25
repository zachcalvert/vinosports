from django.core.management.base import BaseCommand

from vinosports.challenges.models import ChallengeTemplate

CT = ChallengeTemplate.ChallengeType
CR = ChallengeTemplate.CriteriaType

CHALLENGE_TEMPLATE_DEFINITIONS = [
    # ── Daily challenges ──────────────────────────────────────────────
    {
        "slug": "nba-daily-bet-3",
        "title": "Triple Double",
        "description": "Place 3 bets today.",
        "icon": "basketball",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.BET_COUNT,
        "criteria_params": {"target": 3},
        "reward_amount": 50,
    },
    {
        "slug": "nba-daily-bet-5",
        "title": "Starting Five",
        "description": "Place 5 bets today.",
        "icon": "users-five",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.BET_COUNT,
        "criteria_params": {"target": 5},
        "reward_amount": 100,
    },
    {
        "slug": "nba-daily-underdog",
        "title": "Cinderella Story",
        "description": "Bet on an underdog (+150 or longer).",
        "icon": "star-half",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.BET_ON_UNDERDOG,
        "criteria_params": {"target": 1, "odds_min": "2.50"},
        "reward_amount": 75,
    },
    {
        "slug": "nba-daily-win-2",
        "title": "And One",
        "description": "Win 2 bets today.",
        "icon": "checks",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.WIN_COUNT,
        "criteria_params": {"target": 2},
        "reward_amount": 100,
    },
    {
        "slug": "nba-daily-parlay",
        "title": "Alley-Oop",
        "description": "Place a parlay bet.",
        "icon": "link",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.PARLAY_PLACED,
        "criteria_params": {"target": 1, "min_legs": 2},
        "reward_amount": 75,
    },
    {
        "slug": "nba-daily-stake-500",
        "title": "Shot Clock",
        "description": "Stake 500+ credits today.",
        "icon": "coins",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.TOTAL_STAKED,
        "criteria_params": {"target": 500},
        "reward_amount": 100,
    },
    {
        "slug": "nba-daily-correct-3",
        "title": "Sixth Man",
        "description": "Get 3 correct predictions today.",
        "icon": "target",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.CORRECT_PREDICTIONS,
        "criteria_params": {"target": 3},
        "reward_amount": 150,
    },
    {
        "slug": "nba-daily-win-1",
        "title": "Free Throw",
        "description": "Win a bet today.",
        "icon": "check-circle",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.WIN_COUNT,
        "criteria_params": {"target": 1},
        "reward_amount": 50,
    },
    # ── Weekly challenges ─────────────────────────────────────────────
    {
        "slug": "nba-weekly-streak-3",
        "title": "On Fire",
        "description": "Win 3 bets in a row this week.",
        "icon": "fire",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.WIN_STREAK,
        "criteria_params": {"target": 3},
        "reward_amount": 250,
    },
    {
        "slug": "nba-weekly-bet-all",
        "title": "Full Court Press",
        "description": "Bet on every game today.",
        "icon": "court",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.BET_ALL_MATCHES,
        "criteria_params": {"target": 10},
        "reward_amount": 300,
    },
    {
        "slug": "nba-weekly-parlay-win",
        "title": "Buzzer Beater",
        "description": "Win a parlay this week.",
        "icon": "crown",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.PARLAY_WON,
        "criteria_params": {"target": 1},
        "reward_amount": 500,
    },
    {
        "slug": "nba-weekly-win-5",
        "title": "Playoff Mode",
        "description": "Win 5 bets this week.",
        "icon": "trophy",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.WIN_COUNT,
        "criteria_params": {"target": 5},
        "reward_amount": 300,
    },
    {
        "slug": "nba-weekly-correct-5",
        "title": "Floor General",
        "description": "Get 5 correct predictions this week.",
        "icon": "eye",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.CORRECT_PREDICTIONS,
        "criteria_params": {"target": 5},
        "reward_amount": 350,
    },
    {
        "slug": "nba-weekly-stake-2000",
        "title": "Max Contract",
        "description": "Stake 2000+ credits this week.",
        "icon": "wallet",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.TOTAL_STAKED,
        "criteria_params": {"target": 2000},
        "reward_amount": 250,
    },
]


class Command(BaseCommand):
    help = "Seed ChallengeTemplate rows for NBA challenge rotation"

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for defn in CHALLENGE_TEMPLATE_DEFINITIONS:
            slug = defn["slug"]
            _, was_created = ChallengeTemplate.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": defn["title"],
                    "description": defn["description"],
                    "icon": defn["icon"],
                    "challenge_type": defn["challenge_type"],
                    "criteria_type": defn["criteria_type"],
                    "criteria_params": defn["criteria_params"],
                    "reward_amount": defn["reward_amount"],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"  Challenge templates: {created} created, {updated} updated"
            )
        )
