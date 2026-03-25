"""Tests for betting/signals.py (reward rule evaluation on bet placement)."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from nba.tests.factories import (
    BetSlipFactory,
    GameFactory,
    ParlayFactory,
    UserBalanceFactory,
    UserFactory,
)
from vinosports.rewards.models import Reward, RewardRule


def _make_reward_rule(rule_type, threshold):
    """Helper to create a Reward + RewardRule for testing."""
    reward = Reward.objects.create(
        name=f"Test Reward ({rule_type})",
        amount=Decimal("100.00"),
    )
    rule = RewardRule.objects.create(
        reward=reward,
        rule_type=rule_type,
        threshold=threshold,
        is_active=True,
    )
    return reward, rule


@pytest.mark.django_db
class TestBetSlipSignal:
    def test_no_rules_does_not_raise(self):
        """BetSlip creation should not fail when no reward rules exist."""
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        game = GameFactory()
        # Should not raise
        BetSlipFactory(user=user, game=game, stake=Decimal("50.00"))

    def test_bet_count_rule_triggers_at_threshold(self):
        """First bet by a user should trigger BET_COUNT rule with threshold=1."""
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        game = GameFactory()
        _make_reward_rule(RewardRule.RuleType.BET_COUNT, Decimal("1"))

        with patch("vinosports.rewards.models.Reward.distribute_to_users") as mock_dist:
            BetSlipFactory(user=user, game=game, stake=Decimal("50.00"))
            mock_dist.assert_called_once_with([user])

    def test_bet_count_rule_not_triggered_at_wrong_count(self):
        """BET_COUNT rule with threshold=10 should not fire on first bet."""
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        game = GameFactory()
        _make_reward_rule(RewardRule.RuleType.BET_COUNT, Decimal("10"))

        with patch("vinosports.rewards.models.Reward.distribute_to_users") as mock_dist:
            BetSlipFactory(user=user, game=game, stake=Decimal("50.00"))
            mock_dist.assert_not_called()

    def test_stake_amount_rule_triggers_above_threshold(self):
        """STAKE_AMOUNT rule with threshold=50 should fire for $50 bet."""
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        game = GameFactory()
        _make_reward_rule(RewardRule.RuleType.STAKE_AMOUNT, Decimal("50.00"))

        with patch("vinosports.rewards.models.Reward.distribute_to_users") as mock_dist:
            BetSlipFactory(user=user, game=game, stake=Decimal("50.00"))
            mock_dist.assert_called_once_with([user])

    def test_stake_amount_rule_not_triggered_below_threshold(self):
        """STAKE_AMOUNT rule with threshold=100 should not fire for $50 bet."""
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        game = GameFactory()
        _make_reward_rule(RewardRule.RuleType.STAKE_AMOUNT, Decimal("100.00"))

        with patch("vinosports.rewards.models.Reward.distribute_to_users") as mock_dist:
            BetSlipFactory(user=user, game=game, stake=Decimal("50.00"))
            mock_dist.assert_not_called()

    def test_inactive_rule_not_triggered(self):
        """Inactive reward rules should not fire."""
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        game = GameFactory()
        reward = Reward.objects.create(
            name="Inactive Reward",
            amount=Decimal("50.00"),
        )
        RewardRule.objects.create(
            reward=reward,
            rule_type=RewardRule.RuleType.BET_COUNT,
            threshold=Decimal("1"),
            is_active=False,
        )

        with patch("vinosports.rewards.models.Reward.distribute_to_users") as mock_dist:
            BetSlipFactory(user=user, game=game, stake=Decimal("50.00"))
            mock_dist.assert_not_called()


@pytest.mark.django_db
class TestParlaySignal:
    def test_no_rules_does_not_raise(self):
        """Parlay creation should not fail when no reward rules exist."""
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        # Should not raise
        ParlayFactory(user=user, stake=Decimal("30.00"))

    def test_bet_count_rule_counts_parlays(self):
        """Parlay should count toward BET_COUNT milestone."""
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        _make_reward_rule(RewardRule.RuleType.BET_COUNT, Decimal("1"))

        with patch("vinosports.rewards.models.Reward.distribute_to_users") as mock_dist:
            ParlayFactory(user=user, stake=Decimal("30.00"))
            mock_dist.assert_called_once_with([user])

    def test_stake_amount_rule_triggers_for_parlay(self):
        """STAKE_AMOUNT rule should also fire for parlay placements."""
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        _make_reward_rule(RewardRule.RuleType.STAKE_AMOUNT, Decimal("25.00"))

        with patch("vinosports.rewards.models.Reward.distribute_to_users") as mock_dist:
            ParlayFactory(user=user, stake=Decimal("30.00"))
            mock_dist.assert_called_once_with([user])
