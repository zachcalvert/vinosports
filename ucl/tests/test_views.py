"""Smoke tests for all UCL views."""

import pytest
from django.test import Client
from django.urls import reverse

from ucl.matches.models import Stage

from .factories import (
    FinishedMatchFactory,
    MatchFactory,
    OddsFactory,
    StageFactory,
    StandingFactory,
    TeamFactory,
    UserBalanceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user():
    u = UserFactory()
    UserBalanceFactory(user=u)
    return u


@pytest.fixture
def auth_client(user):
    c = Client()
    c.login(email=user.email, password="testpass123")
    return c, user


@pytest.fixture
def league_phase_stage():
    return StageFactory(stage_type=Stage.StageType.LEAGUE_PHASE, order=1)


@pytest.fixture
def standings_with_teams():
    teams = [TeamFactory() for _ in range(4)]
    for i, team in enumerate(teams):
        StandingFactory(team=team, position=i + 1)
    return teams


@pytest.fixture
def scheduled_match(league_phase_stage):
    return MatchFactory(stage=league_phase_stage)


@pytest.fixture
def finished_match(league_phase_stage):
    return FinishedMatchFactory(stage=league_phase_stage)


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------


class TestDashboardView:
    def test_renders_for_anonymous_user(self, client):
        resp = client.get(reverse("ucl_matches:dashboard"))
        assert resp.status_code == 200

    def test_renders_for_authenticated_user(self, auth_client):
        c, _ = auth_client
        resp = c.get(reverse("ucl_matches:dashboard"))
        assert resp.status_code == 200

    def test_context_has_upcoming_matches(self, client, scheduled_match):
        resp = client.get(reverse("ucl_matches:dashboard"))
        assert "upcoming_matches" in resp.context

    def test_context_has_recent_results(self, client, finished_match):
        resp = client.get(reverse("ucl_matches:dashboard"))
        assert "recent_results" in resp.context
        assert finished_match in resp.context["recent_results"]


# ------------------------------------------------------------------
# Standings
# ------------------------------------------------------------------


class TestStandingsView:
    def test_renders(self, client):
        resp = client.get(reverse("ucl_matches:standings"))
        assert resp.status_code == 200

    def test_context_has_standings(self, client, standings_with_teams):
        resp = client.get(reverse("ucl_matches:standings"))
        assert "standings" in resp.context

    def test_all_standings_in_context(self, client, standings_with_teams):
        resp = client.get(reverse("ucl_matches:standings"))
        assert resp.context["standings"].count() == 4


# ------------------------------------------------------------------
# Bracket
# ------------------------------------------------------------------


class TestBracketView:
    def test_renders_with_no_knockout_matches(self, client):
        resp = client.get(reverse("ucl_matches:bracket"))
        assert resp.status_code == 200

    def test_context_has_stages(self, client):
        StageFactory(stage_type=Stage.StageType.ROUND_OF_16, order=3)
        StageFactory(stage_type=Stage.StageType.QUARTER, order=4)
        resp = client.get(reverse("ucl_matches:bracket"))
        assert "stages" in resp.context

    def test_knockout_matches_keyed_by_stage_type(self, client):
        stage = StageFactory(stage_type=Stage.StageType.FINAL, order=6)
        match = MatchFactory(stage=stage)
        resp = client.get(reverse("ucl_matches:bracket"))
        assert Stage.StageType.FINAL in resp.context["knockout_matches"]
        assert match in resp.context["knockout_matches"][Stage.StageType.FINAL]


# ------------------------------------------------------------------
# Match Detail
# ------------------------------------------------------------------


class TestMatchDetailView:
    def test_renders_scheduled_match(self, client, scheduled_match):
        resp = client.get(scheduled_match.get_absolute_url())
        assert resp.status_code == 200

    def test_renders_finished_match(self, client, finished_match):
        resp = client.get(finished_match.get_absolute_url())
        assert resp.status_code == 200

    def test_context_has_match(self, client, scheduled_match):
        resp = client.get(scheduled_match.get_absolute_url())
        assert resp.context["match"] == scheduled_match

    def test_context_has_odds_when_present(self, client, scheduled_match):
        odds = OddsFactory(match=scheduled_match)
        resp = client.get(scheduled_match.get_absolute_url())
        assert resp.context["odds"] == odds

    def test_context_odds_is_none_without_odds(self, client, scheduled_match):
        resp = client.get(scheduled_match.get_absolute_url())
        assert resp.context["odds"] is None

    def test_404_for_bad_slug(self, client):
        resp = client.get(
            reverse("ucl_matches:match_detail", kwargs={"slug": "no-such-match"})
        )
        assert resp.status_code == 404


# ------------------------------------------------------------------
# Leaderboard
# ------------------------------------------------------------------


class TestLeaderboardView:
    def test_renders(self, client):
        resp = client.get(reverse("ucl_matches:leaderboard"))
        assert resp.status_code == 200


# ------------------------------------------------------------------
# Odds Board
# ------------------------------------------------------------------


class TestOddsBoardView:
    def test_renders(self, client):
        resp = client.get(reverse("ucl_betting:odds_board"))
        assert resp.status_code == 200

    def test_context_has_matches_with_odds(self, client, scheduled_match):
        OddsFactory(match=scheduled_match)
        resp = client.get(reverse("ucl_betting:odds_board"))
        assert "matches_with_odds" in resp.context

    def test_partial_renders(self, client):
        resp = client.get(reverse("ucl_betting:odds_board_partial"))
        assert resp.status_code == 200
