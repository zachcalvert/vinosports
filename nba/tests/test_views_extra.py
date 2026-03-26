"""Tests for smaller views: ToggleToastsView, ChallengesPageView, DismissRewardView."""

import pytest
from django.test import Client

from nba.tests.factories import UserFactory
from vinosports.challenges.models import Challenge, UserChallenge
from vinosports.rewards.models import RewardDistribution


@pytest.fixture
def auth_client(db):
    user = UserFactory()
    c = Client()
    c.force_login(user)
    return c, user


# ---------------------------------------------------------------------------
# ToggleToastsView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestToggleToastsView:
    def test_unauthenticated_redirected(self):
        c = Client()
        response = c.post("/nba/activity/toggle-toasts/", {"show_activity_toasts": "1"})
        assert response.status_code in (301, 302)

    def test_enable_toasts(self, auth_client):
        c, user = auth_client
        user.show_activity_toasts = False
        user.save(update_fields=["show_activity_toasts"])

        c.post("/nba/activity/toggle-toasts/", {"show_activity_toasts": "1"})

        user.refresh_from_db()
        assert user.show_activity_toasts is True

    def test_disable_toasts(self, auth_client):
        c, user = auth_client
        user.show_activity_toasts = True
        user.save(update_fields=["show_activity_toasts"])

        c.post("/nba/activity/toggle-toasts/", {})

        user.refresh_from_db()
        assert user.show_activity_toasts is False

    def test_redirects_to_account_page(self, auth_client):
        c, user = auth_client
        response = c.post("/nba/activity/toggle-toasts/", {})
        assert response.status_code in (301, 302)
        assert "/nba/account/" in response["Location"]


# ---------------------------------------------------------------------------
# ChallengesPageView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChallengesPageView:
    def test_unauthenticated_redirected(self):
        c = Client()
        response = c.get("/nba/challenges/")
        assert response.status_code in (301, 302)

    def test_returns_200_for_authenticated_user(self, auth_client):
        c, user = auth_client
        response = c.get("/nba/challenges/")
        assert response.status_code == 200

    def test_context_has_active_challenges(self, auth_client):
        c, user = auth_client
        response = c.get("/nba/challenges/")
        assert "active_challenges" in response.context

    def test_context_has_user_challenges(self, auth_client):
        c, user = auth_client
        response = c.get("/nba/challenges/")
        assert "user_challenges" in response.context


# ---------------------------------------------------------------------------
# DismissRewardView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDismissRewardView:
    def test_unauthenticated_redirected(self):
        c = Client()
        response = c.post("/nba/rewards/1/dismiss/")
        assert response.status_code in (301, 302)

    def test_marks_distribution_as_seen(self, auth_client):
        from vinosports.rewards.models import Reward

        c, user = auth_client
        reward = Reward.objects.create(
            name="Test Reward",
            amount=50,
            description="A test reward",
        )
        distribution = RewardDistribution.objects.create(
            reward=reward,
            user=user,
            seen=False,
        )

        response = c.post(f"/nba/rewards/{distribution.pk}/dismiss/")
        assert response.status_code == 200
        distribution.refresh_from_db()
        assert distribution.seen is True

    def test_ignores_other_users_distributions(self, auth_client):
        from vinosports.rewards.models import Reward

        c, user = auth_client
        other_user = UserFactory()
        reward = Reward.objects.create(
            name="Test Reward",
            amount=50,
            description="A test reward",
        )
        distribution = RewardDistribution.objects.create(
            reward=reward,
            user=other_user,
            seen=False,
        )

        response = c.post(f"/nba/rewards/{distribution.pk}/dismiss/")
        assert response.status_code == 200
        distribution.refresh_from_db()
        assert distribution.seen is False

    def test_returns_empty_response(self, auth_client):
        from vinosports.rewards.models import Reward

        c, user = auth_client
        reward = Reward.objects.create(
            name="Test Reward 2",
            amount=25,
            description="Another reward",
        )
        distribution = RewardDistribution.objects.create(
            reward=reward,
            user=user,
            seen=False,
        )
        response = c.post(f"/nba/rewards/{distribution.pk}/dismiss/")
        assert response.content == b""
