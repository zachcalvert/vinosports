"""Tests for website/challenge_engine.py — evaluators and progress tracking."""

import random
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from epl.website.challenge_engine import (
    _apply_progress,
    _eval_bet_all_matches,
    _eval_bet_count,
    _eval_bet_on_underdog,
    _eval_correct_predictions,
    _eval_parlay_placed,
    _eval_parlay_won,
    _eval_total_staked,
    _eval_win_count,
    _eval_win_streak,
    update_challenge_progress,
)
from vinosports.betting.models import UserBalance
from vinosports.challenges.models import Challenge, ChallengeTemplate, UserChallenge

from .factories import BetSlipFactory, MatchFactory, UserFactory

pytestmark = pytest.mark.django_db


def _make_template(criteria_type, criteria_params=None, reward_amount="50.00"):
    suffix = random.randint(1000, 9999)
    return ChallengeTemplate.objects.create(
        slug=f"test-{suffix}",
        title=f"Test Challenge {suffix}",
        description="A test challenge",
        icon="star",
        challenge_type=ChallengeTemplate.ChallengeType.DAILY,
        criteria_type=criteria_type,
        criteria_params=criteria_params or {"target": 3},
        reward_amount=reward_amount,
        is_active=True,
    )


def _make_challenge(template, **kwargs):
    now = timezone.now()
    defaults = {
        "template": template,
        "status": Challenge.Status.ACTIVE,
        "starts_at": now - timedelta(hours=1),
        "ends_at": now + timedelta(hours=23),
    }
    defaults.update(kwargs)
    return Challenge.objects.create(**defaults)


def _make_user_challenge(user, challenge, progress=0, target=3):
    return UserChallenge.objects.create(
        user=user,
        challenge=challenge,
        progress=progress,
        target=target,
        status=UserChallenge.Status.IN_PROGRESS,
    )


class TestEvalBetCount:
    def test_increments_on_bet_placed(self):
        uc = MagicMock()
        assert _eval_bet_count(uc, "bet_placed", {}) == 1

    def test_increments_on_parlay_placed(self):
        uc = MagicMock()
        assert _eval_bet_count(uc, "parlay_placed", {}) == 1

    def test_ignores_settlement_events(self):
        uc = MagicMock()
        assert _eval_bet_count(uc, "bet_settled", {}) == 0

    def test_ignores_unknown_events(self):
        uc = MagicMock()
        assert _eval_bet_count(uc, "unknown", {}) == 0


class TestEvalBetOnUnderdog:
    def test_increments_when_odds_above_minimum(self):
        uc = MagicMock()
        uc.challenge.template.criteria_params = {"odds_min": "3.00"}
        assert _eval_bet_on_underdog(uc, "bet_placed", {"odds": "4.50"}) == 1

    def test_no_increment_when_odds_below_minimum(self):
        uc = MagicMock()
        uc.challenge.template.criteria_params = {"odds_min": "3.00"}
        assert _eval_bet_on_underdog(uc, "bet_placed", {"odds": "1.50"}) == 0

    def test_ignores_settlement_events(self):
        uc = MagicMock()
        assert _eval_bet_on_underdog(uc, "bet_settled", {"odds": "5.00"}) == 0

    def test_no_odds_in_context(self):
        uc = MagicMock()
        uc.challenge.template.criteria_params = {"odds_min": "3.00"}
        assert _eval_bet_on_underdog(uc, "bet_placed", {}) == 0


class TestEvalWinCount:
    def test_increments_on_win(self):
        uc = MagicMock()
        assert _eval_win_count(uc, "bet_settled", {"won": True}) == 1

    def test_no_increment_on_loss(self):
        uc = MagicMock()
        assert _eval_win_count(uc, "bet_settled", {"won": False}) == 0

    def test_ignores_placement_events(self):
        uc = MagicMock()
        assert _eval_win_count(uc, "bet_placed", {"won": True}) == 0


class TestEvalWinStreak:
    def test_increments_on_win(self):
        uc = MagicMock()
        uc.progress = 2
        assert _eval_win_streak(uc, "bet_settled", {"won": True}) == 1

    def test_resets_on_loss(self):
        uc = MagicMock()
        uc.progress = 3
        assert _eval_win_streak(uc, "bet_settled", {"won": False}) == -3

    def test_ignores_placement_events(self):
        uc = MagicMock()
        assert _eval_win_streak(uc, "bet_placed", {"won": True}) == 0


class TestEvalParlayPlaced:
    def test_increments_with_enough_legs(self):
        uc = MagicMock()
        uc.challenge.template.criteria_params = {"min_legs": 3}
        assert _eval_parlay_placed(uc, "parlay_placed", {"leg_count": 4}) == 1

    def test_no_increment_with_too_few_legs(self):
        uc = MagicMock()
        uc.challenge.template.criteria_params = {"min_legs": 3}
        assert _eval_parlay_placed(uc, "parlay_placed", {"leg_count": 2}) == 0

    def test_ignores_non_parlay_events(self):
        uc = MagicMock()
        assert _eval_parlay_placed(uc, "bet_placed", {"leg_count": 5}) == 0


class TestEvalParlayWon:
    def test_increments_on_parlay_win(self):
        uc = MagicMock()
        assert _eval_parlay_won(uc, "parlay_settled", {"won": True}) == 1

    def test_no_increment_on_parlay_loss(self):
        uc = MagicMock()
        assert _eval_parlay_won(uc, "parlay_settled", {"won": False}) == 0

    def test_ignores_non_parlay_events(self):
        uc = MagicMock()
        assert _eval_parlay_won(uc, "bet_settled", {"won": True}) == 0


class TestEvalTotalStaked:
    def test_returns_total_staked_increment(self):
        user = UserFactory()
        template = _make_template(
            ChallengeTemplate.CriteriaType.TOTAL_STAKED,
            {"target": 200},
        )
        challenge = _make_challenge(template)
        uc = _make_user_challenge(user, challenge, progress=0, target=200)

        match = MatchFactory()
        BetSlipFactory(user=user, match=match, stake=Decimal("50.00"))

        increment = _eval_total_staked(uc, "bet_placed", {})
        assert increment == 50

    def test_ignores_settlement_events(self):
        user = UserFactory()
        template = _make_template(ChallengeTemplate.CriteriaType.TOTAL_STAKED)
        challenge = _make_challenge(template)
        uc = _make_user_challenge(user, challenge)
        assert _eval_total_staked(uc, "bet_settled", {}) == 0


class TestEvalBetAllMatches:
    def test_returns_distinct_match_count(self):
        user = UserFactory()
        template = _make_template(
            ChallengeTemplate.CriteriaType.BET_ALL_MATCHES,
            {"target": 10},
        )
        challenge = _make_challenge(template)
        uc = _make_user_challenge(user, challenge, progress=0, target=10)

        m1 = MatchFactory()
        m2 = MatchFactory()
        BetSlipFactory(user=user, match=m1)
        BetSlipFactory(user=user, match=m2)

        increment = _eval_bet_all_matches(uc, "bet_placed", {})
        assert increment == 2

    def test_ignores_settlement_events(self):
        user = UserFactory()
        template = _make_template(ChallengeTemplate.CriteriaType.BET_ALL_MATCHES)
        challenge = _make_challenge(template)
        uc = _make_user_challenge(user, challenge)
        assert _eval_bet_all_matches(uc, "bet_settled", {}) == 0


class TestEvalCorrectPredictions:
    def test_increments_on_correct(self):
        uc = MagicMock()
        assert _eval_correct_predictions(uc, "bet_settled", {"won": True}) == 1

    def test_no_increment_on_incorrect(self):
        uc = MagicMock()
        assert _eval_correct_predictions(uc, "bet_settled", {"won": False}) == 0

    def test_ignores_placement_events(self):
        uc = MagicMock()
        assert _eval_correct_predictions(uc, "bet_placed", {"won": True}) == 0


class TestApplyProgress:
    def test_increments_progress(self):
        user = UserFactory()
        template = _make_template(
            ChallengeTemplate.CriteriaType.BET_COUNT,
            {"target": 5},
            reward_amount="100.00",
        )
        challenge = _make_challenge(template)
        uc = _make_user_challenge(user, challenge, progress=1, target=5)

        _apply_progress(uc, 1)

        uc.refresh_from_db()
        assert uc.progress == 2
        assert uc.status == UserChallenge.Status.IN_PROGRESS

    @patch("vinosports.challenges.engine._broadcast_challenge_complete")
    def test_completes_and_rewards(self, mock_broadcast):
        user = UserFactory()
        UserBalance.objects.create(user=user, balance=Decimal("100.00"))
        template = _make_template(
            ChallengeTemplate.CriteriaType.BET_COUNT,
            {"target": 3},
            reward_amount="50.00",
        )
        challenge = _make_challenge(template)
        uc = _make_user_challenge(user, challenge, progress=2, target=3)

        _apply_progress(uc, 1)

        uc.refresh_from_db()
        assert uc.status == UserChallenge.Status.COMPLETED
        assert uc.completed_at is not None
        assert uc.reward_credited is True

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("150.00")
        mock_broadcast.assert_called_once()

    def test_progress_never_goes_negative(self):
        user = UserFactory()
        template = _make_template(
            ChallengeTemplate.CriteriaType.WIN_STREAK, {"target": 5}
        )
        challenge = _make_challenge(template)
        uc = _make_user_challenge(user, challenge, progress=2, target=5)

        _apply_progress(uc, -10)

        uc.refresh_from_db()
        assert uc.progress == 0


class TestUpdateChallengeProgress:
    def test_creates_user_challenge_and_updates(self):
        user = UserFactory()
        template = _make_template(
            ChallengeTemplate.CriteriaType.BET_COUNT,
            {"target": 3},
        )
        _make_challenge(template)

        update_challenge_progress(user, "bet_placed", {})

        uc = UserChallenge.objects.get(user=user)
        assert uc.progress == 1

    def test_no_active_challenges_is_noop(self):
        user = UserFactory()
        update_challenge_progress(user, "bet_placed", {})
        assert UserChallenge.objects.filter(user=user).count() == 0

    def test_handles_unknown_criteria_type(self):
        user = UserFactory()
        template = _make_template(
            ChallengeTemplate.CriteriaType.BET_COUNT, {"target": 3}
        )
        # Hack: change criteria_type to something unknown
        template.criteria_type = "UNKNOWN_TYPE"
        template.save()
        _make_challenge(template)

        # Should not raise
        update_challenge_progress(user, "bet_placed", {})
