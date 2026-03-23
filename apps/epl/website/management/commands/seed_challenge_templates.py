from django.core.management.base import BaseCommand

from vinosports.challenges.models import ChallengeTemplate

CT = ChallengeTemplate.ChallengeType
CR = ChallengeTemplate.CriteriaType

CHALLENGE_TEMPLATE_DEFINITIONS = [
    # ── Daily challenges ──────────────────────────────────────────────
    {
        "slug": "daily-bet-3",
        "title": "Triple Threat",
        "description": "Place 3 bets today.",
        "icon": "number-three",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.BET_COUNT,
        "criteria_params": {"target": 3},
        "reward_amount": 50,
    },
    {
        "slug": "daily-bet-5",
        "title": "Five-a-Side",
        "description": "Place 5 bets today.",
        "icon": "hand-fist",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.BET_COUNT,
        "criteria_params": {"target": 5},
        "reward_amount": 100,
    },
    {
        "slug": "daily-underdog",
        "title": "Giant Killer",
        "description": "Place a bet on an underdog (odds 3.00+).",
        "icon": "sword",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.BET_ON_UNDERDOG,
        "criteria_params": {"target": 1, "odds_min": "3.00"},
        "reward_amount": 75,
    },
    {
        "slug": "daily-win-2",
        "title": "Double Up",
        "description": "Win 2 bets today.",
        "icon": "checks",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.WIN_COUNT,
        "criteria_params": {"target": 2},
        "reward_amount": 100,
    },
    {
        "slug": "daily-parlay",
        "title": "Combo Meal",
        "description": "Place a parlay bet.",
        "icon": "link",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.PARLAY_PLACED,
        "criteria_params": {"target": 1, "min_legs": 2},
        "reward_amount": 75,
    },
    {
        "slug": "daily-stake-500",
        "title": "Big Spender",
        "description": "Stake 500+ credits today.",
        "icon": "coins",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.TOTAL_STAKED,
        "criteria_params": {"target": 500},
        "reward_amount": 100,
    },
    {
        "slug": "daily-correct-3",
        "title": "Crystal Ball",
        "description": "Get 3 correct predictions today.",
        "icon": "crystal-ball",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.CORRECT_PREDICTIONS,
        "criteria_params": {"target": 3},
        "reward_amount": 150,
    },
    {
        "slug": "daily-win-1",
        "title": "On the Board",
        "description": "Win a bet today.",
        "icon": "check-circle",
        "challenge_type": CT.DAILY,
        "criteria_type": CR.WIN_COUNT,
        "criteria_params": {"target": 1},
        "reward_amount": 50,
    },
    # ── Weekly challenges ─────────────────────────────────────────────
    {
        "slug": "weekly-streak-3",
        "title": "Hot Streak",
        "description": "Win 3 bets in a row this week.",
        "icon": "fire",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.WIN_STREAK,
        "criteria_params": {"target": 3},
        "reward_amount": 250,
    },
    {
        "slug": "weekly-bet-all",
        "title": "Full Coverage",
        "description": "Place a bet on every match this matchday.",
        "icon": "soccer-ball",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.BET_ALL_MATCHES,
        "criteria_params": {"target": 10},
        "reward_amount": 300,
    },
    {
        "slug": "weekly-parlay-win",
        "title": "Parlay Royale",
        "description": "Win a parlay this week.",
        "icon": "crown",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.PARLAY_WON,
        "criteria_params": {"target": 1},
        "reward_amount": 500,
    },
    {
        "slug": "weekly-win-5",
        "title": "High Five",
        "description": "Win 5 bets this week.",
        "icon": "trophy",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.WIN_COUNT,
        "criteria_params": {"target": 5},
        "reward_amount": 300,
    },
    {
        "slug": "weekly-correct-5",
        "title": "Oracle",
        "description": "Get 5 correct predictions this week.",
        "icon": "eye",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.CORRECT_PREDICTIONS,
        "criteria_params": {"target": 5},
        "reward_amount": 350,
    },
    {
        "slug": "weekly-stake-2000",
        "title": "Whale Watch",
        "description": "Stake 2000+ credits this week.",
        "icon": "wallet",
        "challenge_type": CT.WEEKLY,
        "criteria_type": CR.TOTAL_STAKED,
        "criteria_params": {"target": 2000},
        "reward_amount": 250,
    },
]


class Command(BaseCommand):
    help = "Seed ChallengeTemplate rows for the challenge rotation system"

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
