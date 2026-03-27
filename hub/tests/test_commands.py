"""Tests for hub management commands."""

from decimal import Decimal

import pytest
from django.core.management import call_command

from vinosports.rewards.models import Reward, RewardRule

pytestmark = pytest.mark.django_db


class TestSeedRewardsCommand:
    def test_creates_all_rewards(self):
        call_command("seed_rewards", verbosity=0)

        assert Reward.objects.count() == 8
        assert RewardRule.objects.count() == 8

    def test_creates_bet_count_rewards(self):
        call_command("seed_rewards", verbosity=0)

        bet_count_rules = RewardRule.objects.filter(
            rule_type=RewardRule.RuleType.BET_COUNT
        ).order_by("threshold")
        assert bet_count_rules.count() == 5

        expected = [
            (Decimal("1"), Decimal("100.00"), "1st Bet Reward"),
            (Decimal("5"), Decimal("500.00"), "5th Bet Reward"),
            (Decimal("10"), Decimal("1000.00"), "10th Bet Reward"),
            (Decimal("25"), Decimal("2500.00"), "25th Bet Reward"),
            (Decimal("50"), Decimal("5000.00"), "50th Bet Reward"),
        ]
        for rule, (threshold, amount, name) in zip(bet_count_rules, expected):
            assert rule.threshold == threshold
            assert rule.reward.amount == amount
            assert rule.reward.name == name

    def test_creates_stake_amount_rewards(self):
        call_command("seed_rewards", verbosity=0)

        stake_rules = RewardRule.objects.filter(
            rule_type=RewardRule.RuleType.STAKE_AMOUNT
        ).order_by("threshold")
        assert stake_rules.count() == 3

        expected = [
            (Decimal("500.00"), Decimal("50.00"), "Big Buck Hunter"),
            (Decimal("1000.00"), Decimal("200.00"), "High Roller"),
            (Decimal("5000.00"), Decimal("500.00"), "Platinum Club"),
        ]
        for rule, (threshold, amount, name) in zip(stake_rules, expected):
            assert rule.threshold == threshold
            assert rule.reward.amount == amount
            assert rule.reward.name == name

    def test_idempotent_no_duplicates(self):
        call_command("seed_rewards", verbosity=0)
        call_command("seed_rewards", verbosity=0)

        assert Reward.objects.count() == 8
        assert RewardRule.objects.count() == 8

    def test_updates_existing_reward_name_and_amount(self):
        # Pre-create a reward/rule with stale data
        reward = Reward.objects.create(name="Old Name", amount=Decimal("1.00"))
        RewardRule.objects.create(
            reward=reward,
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold=Decimal("1"),
        )

        call_command("seed_rewards", verbosity=0)

        reward.refresh_from_db()
        assert reward.name == "1st Bet Reward"
        assert reward.amount == Decimal("100.00")
