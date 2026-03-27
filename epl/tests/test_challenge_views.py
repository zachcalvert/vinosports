"""Tests for website/challenge_views.py — ChallengesPageView, partials, enrollment."""

import random
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from vinosports.challenges.models import Challenge, ChallengeTemplate, UserChallenge

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def _make_template(challenge_type=ChallengeTemplate.ChallengeType.DAILY):
    suffix = random.randint(1000, 9999)
    return ChallengeTemplate.objects.create(
        slug=f"test-view-{suffix}",
        title=f"Test Challenge {suffix}",
        description="A test challenge",
        icon="star",
        challenge_type=challenge_type,
        criteria_type=ChallengeTemplate.CriteriaType.BET_COUNT,
        criteria_params={"target": 3},
        reward_amount="50.00",
        is_active=True,
    )


def _make_active_challenge(template=None):
    if template is None:
        template = _make_template()
    now = timezone.now()
    return Challenge.objects.create(
        template=template,
        status=Challenge.Status.ACTIVE,
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=23),
    )


@pytest.fixture
def authed_client():
    user = UserFactory(password="testpass123")
    c = Client()
    c.login(email=user.email, password="testpass123")
    return c, user


class TestChallengesPageView:
    def test_redirects_unauthenticated(self):
        c = Client()
        resp = c.get("/epl/challenges/")
        assert resp.status_code in (301, 302)

    def test_authenticated_gets_200(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/challenges/")
        assert resp.status_code == 200

    def test_default_tab_is_active(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/challenges/")
        assert resp.context["active_tab"] == "active"

    def test_completed_tab(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/challenges/?tab=completed")
        assert resp.context["active_tab"] == "completed"
        assert "challenges" in resp.context

    def test_upcoming_tab(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/challenges/?tab=upcoming")
        assert resp.context["active_tab"] == "upcoming"
        assert "upcoming_challenges" in resp.context

    def test_unknown_tab_defaults_to_active(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/challenges/?tab=invalid")
        assert "challenges" in resp.context

    def test_auto_enrolls_user_into_active_challenges(self, authed_client):
        c, user = authed_client
        _make_active_challenge()

        c.get("/epl/challenges/")

        assert UserChallenge.objects.filter(user=user).count() == 1

    def test_does_not_duplicate_enrollment(self, authed_client):
        c, user = authed_client
        challenge = _make_active_challenge()
        UserChallenge.objects.create(
            user=user,
            challenge=challenge,
            target=challenge.target,
        )

        c.get("/epl/challenges/")

        assert UserChallenge.objects.filter(user=user).count() == 1


class TestActiveChallengesPartial:
    def test_redirects_unauthenticated(self):
        c = Client()
        resp = c.get("/epl/challenges/active/")
        assert resp.status_code in (301, 302)

    def test_returns_200(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/challenges/active/")
        assert resp.status_code == 200
        assert resp.context["active_tab"] == "active"


class TestCompletedChallengesPartial:
    def test_returns_200(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/challenges/completed/")
        assert resp.status_code == 200
        assert resp.context["active_tab"] == "completed"


class TestUpcomingChallengesPartial:
    def test_returns_200(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/challenges/upcoming/")
        assert resp.status_code == 200
        assert resp.context["active_tab"] == "upcoming"


class TestChallengeWidgetPartial:
    def test_redirects_unauthenticated(self):
        c = Client()
        resp = c.get("/epl/challenges/widget/")
        assert resp.status_code in (301, 302)

    def test_returns_200(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/challenges/widget/")
        assert resp.status_code == 200
        assert "active_challenges" in resp.context

    def test_limits_to_3_challenges(self, authed_client):
        c, user = authed_client
        for _ in range(5):
            challenge = _make_active_challenge()
            UserChallenge.objects.create(
                user=user,
                challenge=challenge,
                target=challenge.target,
                status=UserChallenge.Status.IN_PROGRESS,
            )

        resp = c.get("/epl/challenges/widget/")
        assert len(resp.context["active_challenges"]) <= 3
