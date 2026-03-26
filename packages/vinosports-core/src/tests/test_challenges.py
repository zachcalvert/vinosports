"""Tests for vinosports.challenges — ChallengeTemplate, Challenge, UserChallenge."""

import pytest

from .factories import ChallengeFactory, ChallengeTemplateFactory, UserChallengeFactory

pytestmark = pytest.mark.django_db


class TestChallengeTemplate:
    def test_str(self):
        ct = ChallengeTemplateFactory(title="Win 3 Bets")
        assert "Win 3 Bets" in str(ct)
        assert "Daily" in str(ct)


class TestChallenge:
    def test_target_from_criteria_params(self):
        ct = ChallengeTemplateFactory(criteria_params={"target": 5})
        challenge = ChallengeFactory(template=ct)
        assert challenge.target == 5

    def test_target_defaults_to_1(self):
        ct = ChallengeTemplateFactory(criteria_params={})
        challenge = ChallengeFactory(template=ct)
        assert challenge.target == 1


class TestUserChallenge:
    def test_progress_percent_basic(self):
        uc = UserChallengeFactory(progress=1, target=3)
        assert uc.progress_percent == 33

    def test_progress_percent_complete(self):
        uc = UserChallengeFactory(progress=3, target=3)
        assert uc.progress_percent == 100

    def test_progress_percent_capped_at_100(self):
        uc = UserChallengeFactory(progress=5, target=3)
        assert uc.progress_percent == 100

    def test_progress_percent_zero_target(self):
        uc = UserChallengeFactory(progress=1, target=0)
        assert uc.progress_percent == 0
