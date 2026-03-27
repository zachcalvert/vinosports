from decimal import Decimal

from django.core.management.base import BaseCommand

from vinosports.rewards.models import Reward, RewardRule

REWARD_DEFINITIONS = [
    # Bet count milestones
    {
        "name": "1st Bet Reward",
        "amount": Decimal("100.00"),
        "rule_type": RewardRule.RuleType.BET_COUNT,
        "threshold": Decimal("1"),
    },
    {
        "name": "5th Bet Reward",
        "amount": Decimal("500.00"),
        "rule_type": RewardRule.RuleType.BET_COUNT,
        "threshold": Decimal("5"),
    },
    {
        "name": "10th Bet Reward",
        "amount": Decimal("1000.00"),
        "rule_type": RewardRule.RuleType.BET_COUNT,
        "threshold": Decimal("10"),
    },
    {
        "name": "25th Bet Reward",
        "amount": Decimal("2500.00"),
        "rule_type": RewardRule.RuleType.BET_COUNT,
        "threshold": Decimal("25"),
    },
    {
        "name": "50th Bet Reward",
        "amount": Decimal("5000.00"),
        "rule_type": RewardRule.RuleType.BET_COUNT,
        "threshold": Decimal("50"),
    },
    # Stake amount thresholds
    {
        "name": "Big Buck Hunter",
        "amount": Decimal("50.00"),
        "rule_type": RewardRule.RuleType.STAKE_AMOUNT,
        "threshold": Decimal("500.00"),
    },
    {
        "name": "High Roller",
        "amount": Decimal("200.00"),
        "rule_type": RewardRule.RuleType.STAKE_AMOUNT,
        "threshold": Decimal("1000.00"),
    },
    {
        "name": "Platinum Club",
        "amount": Decimal("500.00"),
        "rule_type": RewardRule.RuleType.STAKE_AMOUNT,
        "threshold": Decimal("5000.00"),
    },
]


class Command(BaseCommand):
    help = "Seed automatic Reward and RewardRule rows"

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for defn in REWARD_DEFINITIONS:
            try:
                rule = RewardRule.objects.get(
                    rule_type=defn["rule_type"],
                    threshold=defn["threshold"],
                )
                reward = rule.reward
                reward.name = defn["name"]
                reward.amount = defn["amount"]
                reward.save()
                updated += 1
            except RewardRule.DoesNotExist:
                reward = Reward.objects.create(
                    name=defn["name"],
                    amount=defn["amount"],
                )
                RewardRule.objects.create(
                    reward=reward,
                    rule_type=defn["rule_type"],
                    threshold=defn["threshold"],
                )
                created += 1

        self.stdout.write(
            self.style.SUCCESS(f"  Rewards: {created} created, {updated} updated")
        )
