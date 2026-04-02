"""Tests for vinosports.rewards — Reward distribution and RewardRule validation."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from vinosports.betting.models import BalanceTransaction, UserBalance
from vinosports.rewards.models import RewardDistribution, RewardRule

from .factories import RewardFactory, UserBalanceFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestRewardDistribution:
    @patch("vinosports.rewards.models._broadcast_rewards")
    def test_distribute_credits_balance(self, mock_broadcast):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        reward = RewardFactory(amount=Decimal("50.00"))

        dists = reward.distribute_to_users([user])

        assert len(dists) == 1
        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("1050.00")

    @patch("vinosports.rewards.models._broadcast_rewards")
    def test_creates_transaction_record(self, mock_broadcast):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        reward = RewardFactory(amount=Decimal("75.00"))

        reward.distribute_to_users([user])

        txn = BalanceTransaction.objects.get(user=user)
        assert txn.transaction_type == BalanceTransaction.Type.REWARD
        assert txn.amount == Decimal("75.00")

    @patch("vinosports.rewards.models._broadcast_rewards")
    def test_skips_duplicate_distribution(self, mock_broadcast):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        reward = RewardFactory(amount=Decimal("50.00"))

        reward.distribute_to_users([user])
        dists = reward.distribute_to_users([user])

        assert len(dists) == 0
        assert RewardDistribution.objects.filter(user=user).count() == 1

    @patch("vinosports.rewards.models._broadcast_rewards")
    def test_creates_balance_if_missing(self, mock_broadcast):
        user = UserFactory()
        reward = RewardFactory(amount=Decimal("50.00"))

        reward.distribute_to_users([user])

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("100050.00")

    @patch("vinosports.rewards.models._broadcast_rewards")
    def test_multiple_users(self, mock_broadcast):
        users = [UserFactory() for _ in range(3)]
        for u in users:
            UserBalanceFactory(user=u, balance=Decimal("100.00"))
        reward = RewardFactory(amount=Decimal("25.00"))

        dists = reward.distribute_to_users(users)

        assert len(dists) == 3
        for u in users:
            assert UserBalance.objects.get(user=u).balance == Decimal("125.00")


class TestRewardRule:
    def test_bet_count_rejects_fractional_threshold(self):
        reward = RewardFactory()
        rule = RewardRule(
            reward=reward,
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold=Decimal("5.5"),
        )
        with pytest.raises(ValidationError):
            rule.clean()

    def test_bet_count_accepts_whole_threshold(self):
        reward = RewardFactory()
        rule = RewardRule(
            reward=reward,
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold=Decimal("10.00"),
        )
        rule.clean()

    def test_stake_amount_accepts_fractional(self):
        reward = RewardFactory()
        rule = RewardRule(
            reward=reward,
            rule_type=RewardRule.RuleType.STAKE_AMOUNT,
            threshold=Decimal("100.50"),
        )
        rule.clean()
