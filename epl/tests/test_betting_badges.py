"""Tests for epl/betting/badges.py — badge criteria and awarding logic."""

from decimal import Decimal

import pytest

from epl.betting.badges import (
    CENTURY_THRESHOLD,
    SHARP_EYE_MIN_BETS,
    STREAK_MASTER_THRESHOLD,
    BetContext,
    check_and_award_badges,
)
from vinosports.betting.models import Badge, BetStatus, UserBadge

from .factories import (
    BetSlipFactory,
    MatchFactory,
    UserFactory,
    UserStatsFactory,
)

pytestmark = pytest.mark.django_db


def _make_context(
    won=True,
    odds=Decimal("2.10"),
    is_parlay=False,
    leg_count=0,
    stake=Decimal("50.00"),
    max_stake=Decimal("1000.00"),
    matchday=None,
):
    return BetContext(
        won=won,
        odds=odds,
        is_parlay=is_parlay,
        leg_count=leg_count,
        stake=stake,
        max_stake=max_stake,
        matchday=matchday,
    )


@pytest.fixture
def badges():
    """Create all standard badges in the DB."""
    from epl.betting.badges import BADGE_DEFINITIONS

    created = {}
    for defn in BADGE_DEFINITIONS:
        badge = Badge.objects.create(
            slug=defn["slug"],
            name=defn["name"],
            description=defn["description"],
            icon=defn["icon"],
            rarity=defn["rarity"],
        )
        created[defn["slug"]] = badge
    return created


class TestFirstBlood:
    def test_earned_after_first_bet(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "first_blood" in slugs

    def test_not_earned_when_no_bets(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=0)
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "first_blood" not in slugs


class TestCalledTheUpset:
    def test_earned_on_upset_win(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context(won=True, odds=Decimal("5.00"))
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "called_the_upset" in slugs

    def test_not_earned_on_loss(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context(won=False, odds=Decimal("5.00"))
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "called_the_upset" not in slugs

    def test_not_earned_with_low_odds(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context(won=True, odds=Decimal("3.00"))
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "called_the_upset" not in slugs


class TestPerfectMatchweek:
    def test_earned_when_all_bets_won_in_matchweek(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=2)
        match = MatchFactory(matchday=5)
        BetSlipFactory(user=user, match=match, status=BetStatus.WON)
        ctx = _make_context(won=True, matchday=5)
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "perfect_matchweek" in slugs

    def test_not_earned_when_lost_in_matchweek(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=2)
        match = MatchFactory(matchday=5)
        BetSlipFactory(user=user, match=match, status=BetStatus.WON)
        match2 = MatchFactory(matchday=5)
        BetSlipFactory(user=user, match=match2, status=BetStatus.LOST)
        ctx = _make_context(won=True, matchday=5)
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "perfect_matchweek" not in slugs

    def test_not_earned_on_loss(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context(won=False, matchday=5)
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "perfect_matchweek" not in slugs

    def test_not_earned_without_matchday(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context(won=True, matchday=None)
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "perfect_matchweek" not in slugs


class TestParlayKing:
    def test_earned_on_big_parlay_win(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=5)
        ctx = _make_context(won=True, is_parlay=True, leg_count=5)
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "parlay_king" in slugs

    def test_not_earned_on_small_parlay(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=2)
        ctx = _make_context(won=True, is_parlay=True, leg_count=2)
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "parlay_king" not in slugs

    def test_not_earned_on_loss(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=5)
        ctx = _make_context(won=False, is_parlay=True, leg_count=5)
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "parlay_king" not in slugs


class TestStreakMaster:
    def test_earned_at_threshold(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(
            user=user, total_bets=10, best_streak=STREAK_MASTER_THRESHOLD
        )
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "streak_master" in slugs

    def test_not_earned_below_threshold(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(
            user=user, total_bets=5, best_streak=STREAK_MASTER_THRESHOLD - 1
        )
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "streak_master" not in slugs


class TestHighRoller:
    def test_earned_on_max_stake_win(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context(
            won=True, stake=Decimal("1000.00"), max_stake=Decimal("1000.00")
        )
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "high_roller" in slugs

    def test_not_earned_on_parlay(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context(
            won=True,
            is_parlay=True,
            stake=Decimal("1000.00"),
            max_stake=Decimal("1000.00"),
        )
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "high_roller" not in slugs

    def test_not_earned_below_max_stake(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context(
            won=True, stake=Decimal("500.00"), max_stake=Decimal("1000.00")
        )
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "high_roller" not in slugs


class TestSharpEye:
    def test_earned_with_high_win_rate(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(
            user=user,
            total_bets=SHARP_EYE_MIN_BETS,
            total_wins=35,
            total_losses=15,
        )
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "sharp_eye" in slugs

    def test_not_earned_below_min_bets(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=10, total_wins=8, total_losses=2)
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "sharp_eye" not in slugs


class TestCentury:
    def test_earned_at_100_bets(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=CENTURY_THRESHOLD)
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "century" in slugs

    def test_not_earned_below_threshold(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=99)
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "century" not in slugs


class TestCheckAndAwardBadges:
    def test_already_earned_not_duplicated(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        UserBadge.objects.create(user=user, badge=badges["first_blood"])
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        assert "first_blood" not in slugs

    def test_returns_empty_when_all_earned(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        for badge in badges.values():
            UserBadge.objects.create(user=user, badge=badge)
        ctx = _make_context()
        earned = check_and_award_badges(user, stats, ctx)
        assert earned == []

    def test_multiple_badges_earned_at_once(self, badges):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = _make_context(won=True, odds=Decimal("5.00"))
        earned = check_and_award_badges(user, stats, ctx)
        slugs = [ub.badge.slug for ub in earned]
        # first_blood + called_the_upset at minimum
        assert "first_blood" in slugs
        assert "called_the_upset" in slugs
