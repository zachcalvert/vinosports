"""Tests for vinosports.betting — balance, models, leaderboard."""

from decimal import Decimal

import pytest
from django.db import transaction

from vinosports.betting.balance import log_transaction
from vinosports.betting.leaderboard import (
    get_leaderboard_entries,
    get_public_identity,
    get_user_rank,
    mask_email,
)
from vinosports.betting.models import BalanceTransaction, UserBalance

from .factories import UserBalanceFactory, UserFactory, UserStatsFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# log_transaction
# ---------------------------------------------------------------------------


class TestLogTransaction:
    def test_credits_balance(self):
        ub = UserBalanceFactory(balance=Decimal("500.00"))
        with transaction.atomic():
            ub = UserBalance.objects.select_for_update().get(pk=ub.pk)
            log_transaction(ub, Decimal("100.00"), BalanceTransaction.Type.BET_WIN)
        ub.refresh_from_db()
        assert ub.balance == Decimal("600.00")

    def test_debits_balance(self):
        ub = UserBalanceFactory(balance=Decimal("500.00"))
        with transaction.atomic():
            ub = UserBalance.objects.select_for_update().get(pk=ub.pk)
            log_transaction(
                ub, Decimal("-50.00"), BalanceTransaction.Type.BET_PLACEMENT
            )
        ub.refresh_from_db()
        assert ub.balance == Decimal("450.00")

    def test_creates_transaction_record(self):
        ub = UserBalanceFactory(balance=Decimal("500.00"))
        with transaction.atomic():
            ub = UserBalance.objects.select_for_update().get(pk=ub.pk)
            log_transaction(
                ub,
                Decimal("25.00"),
                BalanceTransaction.Type.REWARD,
                description="Test reward",
            )
        txn = BalanceTransaction.objects.get(user=ub.user)
        assert txn.amount == Decimal("25.00")
        assert txn.balance_after == Decimal("525.00")
        assert txn.transaction_type == BalanceTransaction.Type.REWARD
        assert txn.description == "Test reward"

    def test_accepts_string_amount(self):
        ub = UserBalanceFactory(balance=Decimal("100.00"))
        with transaction.atomic():
            ub = UserBalance.objects.select_for_update().get(pk=ub.pk)
            log_transaction(ub, "50", BalanceTransaction.Type.BAILOUT)
        ub.refresh_from_db()
        assert ub.balance == Decimal("150.00")


# ---------------------------------------------------------------------------
# UserStats
# ---------------------------------------------------------------------------


class TestUserStats:
    def test_win_rate_with_bets(self):
        stats = UserStatsFactory(total_bets=10, total_wins=7)
        assert stats.win_rate == Decimal("70.0")

    def test_win_rate_zero_bets(self):
        stats = UserStatsFactory(total_bets=0, total_wins=0)
        assert stats.win_rate == Decimal("0.00")

    def test_str_format(self):
        stats = UserStatsFactory(
            total_wins=5, total_losses=3, net_profit=Decimal("200.00")
        )
        result = str(stats)
        assert "5W-3L" in result
        assert "+200" in result


# ---------------------------------------------------------------------------
# mask_email / get_public_identity
# ---------------------------------------------------------------------------


class TestMaskEmail:
    def test_masks_local_part(self):
        assert mask_email("john@example.com") == "jo**@example.com"

    def test_short_local_part(self):
        assert mask_email("a@example.com") == "a*@example.com"

    def test_no_domain(self):
        assert mask_email("nodomain") == "nodomain"


class TestGetPublicIdentity:
    def test_returns_display_name_when_set(self):
        user = UserFactory(display_name="CoolGuy")
        assert get_public_identity(user) == "CoolGuy"

    def test_returns_masked_email_when_no_display_name(self):
        user = UserFactory(display_name=None, email="hidden@test.com")
        assert get_public_identity(user) == "hi****@test.com"

    def test_returns_masked_email_for_empty_display_name(self):
        user = UserFactory(display_name="", email="empty@test.com")
        assert get_public_identity(user) == "em***@test.com"


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


class TestLeaderboard:
    def test_balance_leaderboard_ordering(self):
        ub1 = UserBalanceFactory(balance=Decimal("500.00"))
        ub2 = UserBalanceFactory(balance=Decimal("2000.00"))
        ub3 = UserBalanceFactory(balance=Decimal("1000.00"))

        entries = get_leaderboard_entries(board_type="balance")
        user_ids = [e.user_id for e in entries]
        assert user_ids == [ub2.user_id, ub3.user_id, ub1.user_id]

    def test_excludes_superusers(self):
        UserBalanceFactory(
            user=UserFactory(is_superuser=True, is_staff=True),
            balance=Decimal("99999.00"),
        )
        UserBalanceFactory(balance=Decimal("100.00"))

        entries = get_leaderboard_entries(board_type="balance")
        assert len(entries) == 1

    def test_profit_leaderboard(self):
        u1 = UserFactory()
        u2 = UserFactory()
        UserStatsFactory(user=u1, total_bets=5, net_profit=Decimal("300.00"))
        UserStatsFactory(user=u2, total_bets=5, net_profit=Decimal("500.00"))

        entries = get_leaderboard_entries(board_type="profit")
        assert entries[0].user_id == u2.id

    def test_win_rate_requires_min_bets(self):
        u1 = UserFactory()
        u2 = UserFactory()
        UserStatsFactory(user=u1, total_bets=5, total_wins=5)  # below threshold
        UserStatsFactory(user=u2, total_bets=10, total_wins=7)  # at threshold

        entries = get_leaderboard_entries(board_type="win_rate")
        assert len(entries) == 1
        assert entries[0].user_id == u2.id

    def test_streak_leaderboard(self):
        u1 = UserFactory()
        u2 = UserFactory()
        UserStatsFactory(user=u1, total_bets=5, best_streak=3, current_streak=2)
        UserStatsFactory(user=u2, total_bets=5, best_streak=7, current_streak=0)

        entries = get_leaderboard_entries(board_type="streak")
        assert entries[0].user_id == u2.id

    def test_display_identity_annotated(self):
        UserBalanceFactory(
            user=UserFactory(display_name="ShowMe"),
            balance=Decimal("100.00"),
        )
        entries = get_leaderboard_entries(board_type="balance")
        assert entries[0].display_identity == "ShowMe"

    def test_limit_respected(self):
        for _ in range(5):
            UserBalanceFactory()
        entries = get_leaderboard_entries(limit=3, board_type="balance")
        assert len(entries) == 3

    def test_excludes_inactive_users(self):
        UserBalanceFactory(
            user=UserFactory(is_active=False),
            balance=Decimal("99999.00"),
        )
        UserBalanceFactory(balance=Decimal("100.00"))

        entries = get_leaderboard_entries(board_type="balance")
        assert len(entries) == 1

    def test_excludes_inactive_users_profit(self):
        inactive = UserFactory(is_active=False)
        UserStatsFactory(user=inactive, total_bets=5, net_profit=Decimal("9999.00"))
        active = UserFactory()
        UserStatsFactory(user=active, total_bets=5, net_profit=Decimal("100.00"))

        entries = get_leaderboard_entries(board_type="profit")
        assert len(entries) == 1
        assert entries[0].user_id == active.id

    def test_excludes_inactive_users_win_rate(self):
        inactive = UserFactory(is_active=False)
        UserStatsFactory(user=inactive, total_bets=10, total_wins=10)
        active = UserFactory()
        UserStatsFactory(user=active, total_bets=10, total_wins=7)

        entries = get_leaderboard_entries(board_type="win_rate")
        assert len(entries) == 1
        assert entries[0].user_id == active.id

    def test_excludes_inactive_users_streak(self):
        inactive = UserFactory(is_active=False)
        UserStatsFactory(user=inactive, total_bets=5, best_streak=99, current_streak=0)
        active = UserFactory()
        UserStatsFactory(user=active, total_bets=5, best_streak=3, current_streak=2)

        entries = get_leaderboard_entries(board_type="streak")
        assert len(entries) == 1
        assert entries[0].user_id == active.id


class TestGetUserRank:
    def test_returns_none_for_anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        assert get_user_rank(AnonymousUser()) is None

    def test_returns_none_for_superuser(self):
        user = UserFactory(is_superuser=True, is_staff=True)
        assert get_user_rank(user) is None

    def test_returns_balance_rank(self):
        u1 = UserFactory()
        u2 = UserFactory()
        UserBalanceFactory(user=u1, balance=Decimal("2000.00"))
        UserBalanceFactory(user=u2, balance=Decimal("500.00"))

        rank = get_user_rank(u2, leaderboard=[], board_type="balance")
        assert rank is not None
        assert rank.rank == 2

    def test_returns_none_when_user_on_leaderboard(self):
        u = UserFactory()
        ub = UserBalanceFactory(user=u, balance=Decimal("1000.00"))

        rank = get_user_rank(u, leaderboard=[ub], board_type="balance")
        assert rank is None

    def test_rank_excludes_inactive_users(self):
        # Inactive user with a higher balance should not affect the rank count.
        inactive = UserFactory(is_active=False)
        UserBalanceFactory(user=inactive, balance=Decimal("9999.00"))
        u = UserFactory()
        UserBalanceFactory(user=u, balance=Decimal("500.00"))

        rank = get_user_rank(u, leaderboard=[], board_type="balance")
        assert rank is not None
        assert rank.rank == 1
