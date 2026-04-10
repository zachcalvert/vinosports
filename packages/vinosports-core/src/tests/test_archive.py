"""Tests for vinosports.bots.archive — automatic BotArchiveEntry creation."""

import pytest

from vinosports.bots.archive import maybe_create_betting_highlight
from vinosports.bots.models import BotArchiveEntry, EntryType
from vinosports.challenges.models import UserChallenge
from vinosports.rewards.models import RewardDistribution

from .factories import (
    BotProfileFactory,
    RewardFactory,
    UserChallengeFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# RewardDistribution → AWARD archive entry
# ---------------------------------------------------------------------------


class TestRewardDistributedSignal:
    def test_creates_award_entry_for_bot(self):
        profile = BotProfileFactory()
        reward = RewardFactory(name="Hot Streak", amount=500)
        RewardDistribution.objects.create(reward=reward, user=profile.user)

        entry = BotArchiveEntry.objects.get(
            bot_profile=profile, entry_type=EntryType.AWARD
        )
        assert "Hot Streak" in entry.summary
        assert "500" in entry.summary

    def test_no_entry_for_human_user(self):
        user = UserFactory()
        reward = RewardFactory()
        RewardDistribution.objects.create(reward=reward, user=user)

        assert not BotArchiveEntry.objects.exists()

    def test_no_entry_on_update(self):
        profile = BotProfileFactory()
        reward = RewardFactory()
        dist = RewardDistribution.objects.create(reward=reward, user=profile.user)
        initial_count = BotArchiveEntry.objects.count()

        # Update the distribution (not a create)
        dist.seen = True
        dist.save()

        assert BotArchiveEntry.objects.count() == initial_count


# ---------------------------------------------------------------------------
# UserChallenge completed → CHALLENGE archive entry
# ---------------------------------------------------------------------------


class TestChallengeCompletedSignal:
    def test_creates_challenge_entry_on_completion(self):
        profile = BotProfileFactory()
        uc = UserChallengeFactory(
            user=profile.user,
            status=UserChallenge.Status.IN_PROGRESS,
        )
        # Simulate completion
        uc.status = UserChallenge.Status.COMPLETED
        uc.save()

        entry = BotArchiveEntry.objects.get(
            bot_profile=profile, entry_type=EntryType.CHALLENGE
        )
        assert uc.challenge.template.title in entry.summary

    def test_no_entry_for_in_progress(self):
        profile = BotProfileFactory()
        UserChallengeFactory(
            user=profile.user,
            status=UserChallenge.Status.IN_PROGRESS,
        )
        assert not BotArchiveEntry.objects.filter(
            entry_type=EntryType.CHALLENGE
        ).exists()

    def test_no_entry_for_human(self):
        user = UserFactory()
        uc = UserChallengeFactory(user=user)
        uc.status = UserChallenge.Status.COMPLETED
        uc.save()

        assert not BotArchiveEntry.objects.exists()

    def test_no_duplicate_on_re_save(self):
        profile = BotProfileFactory()
        uc = UserChallengeFactory(
            user=profile.user,
            status=UserChallenge.Status.COMPLETED,
        )
        initial_count = BotArchiveEntry.objects.filter(
            entry_type=EntryType.CHALLENGE
        ).count()

        # Re-save the completed challenge
        uc.save()

        assert (
            BotArchiveEntry.objects.filter(entry_type=EntryType.CHALLENGE).count()
            == initial_count
        )


# ---------------------------------------------------------------------------
# maybe_create_betting_highlight
# ---------------------------------------------------------------------------


class TestMaybeCreateBettingHighlight:
    def test_creates_entry_for_bot(self):
        profile = BotProfileFactory()
        entry = maybe_create_betting_highlight(
            profile.user,
            summary="Won 5,000 credits on a 4-leg parlay",
            league="epl",
            raw_source="bet_slip_id=123",
        )
        assert entry is not None
        assert entry.entry_type == EntryType.BETTING_HIGHLIGHT
        assert entry.league == "epl"
        assert "5,000" in entry.summary

    def test_returns_none_for_human(self):
        user = UserFactory()
        result = maybe_create_betting_highlight(user, "Big win!")
        assert result is None
        assert not BotArchiveEntry.objects.exists()

    def test_default_empty_league(self):
        profile = BotProfileFactory()
        entry = maybe_create_betting_highlight(profile.user, "Lost big")
        assert entry.league == ""
