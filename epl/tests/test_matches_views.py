"""Tests for matches/views.py — DashboardView, MatchDetailView, LeagueTableView, etc."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone

from epl.matches.models import Match
from epl.matches.views import _get_default_matchday

from .factories import (
    MatchFactory,
    OddsFactory,
    StandingFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def authed_client():
    user = UserFactory(password="testpass123")
    c = Client()
    c.login(email=user.email, password="testpass123")
    return c, user


@pytest.fixture
def superuser_client():
    user = UserFactory(password="testpass123")
    user.is_superuser = True
    user.save()
    c = Client()
    c.login(email=user.email, password="testpass123")
    return c, user


class TestGetDefaultMatchday:
    def test_returns_next_upcoming_matchday(self):
        season = settings.EPL_CURRENT_SEASON
        now = timezone.now()
        MatchFactory(
            season=season,
            matchday=10,
            kickoff=now + timedelta(days=1),
        )
        MatchFactory(
            season=season,
            matchday=9,
            kickoff=now - timedelta(days=3),
            status=Match.Status.FINISHED,
        )
        result = _get_default_matchday(season)
        assert result == 10

    def test_falls_back_to_most_recent(self):
        season = settings.EPL_CURRENT_SEASON
        now = timezone.now()
        MatchFactory(
            season=season,
            matchday=8,
            kickoff=now - timedelta(days=1),
            status=Match.Status.FINISHED,
        )
        result = _get_default_matchday(season)
        assert result == 8

    def test_returns_1_when_no_matches(self):
        result = _get_default_matchday(settings.EPL_CURRENT_SEASON)
        assert result == 1


class TestDashboardView:
    def test_renders_publicly(self, client):
        resp = client.get("/epl/")
        assert resp.status_code == 200

    def test_context_has_matches_and_matchdays(self, client):
        MatchFactory(season=settings.EPL_CURRENT_SEASON, matchday=1)
        resp = client.get("/epl/")
        assert "matches" in resp.context
        assert "matchdays" in resp.context
        assert "standings" in resp.context

    def test_matchday_param_filters(self, client):
        season = settings.EPL_CURRENT_SEASON
        MatchFactory(season=season, matchday=5)
        MatchFactory(season=season, matchday=10)
        resp = client.get("/epl/?matchday=5")
        assert resp.context["matchday"] == 5

    def test_invalid_matchday_uses_default(self, client):
        resp = client.get("/epl/?matchday=abc")
        assert resp.status_code == 200

    def test_htmx_returns_partial(self, client):
        resp = client.get("/epl/?matchday=1", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        templates = [t.name for t in resp.templates]
        assert "matches/partials/fixture_list_htmx.html" in templates

    def test_matches_with_odds_annotated(self, client):
        match = MatchFactory(season=settings.EPL_CURRENT_SEASON, matchday=1)
        OddsFactory(match=match, home_win=Decimal("2.10"))
        resp = client.get("/epl/?matchday=1")
        match_in_ctx = resp.context["matches"][0]
        assert match_in_ctx.best_home_odds is not None


class TestMatchDetailView:
    def test_renders_match(self, client):
        match = MatchFactory()
        resp = client.get(f"/epl/match/{match.slug}/")
        assert resp.status_code == 200
        assert resp.context["match"] == match

    def test_404_for_invalid_slug(self, client):
        resp = client.get("/epl/match/no-such-match/")
        assert resp.status_code == 404

    def test_context_contains_odds(self, client):
        match = MatchFactory()
        OddsFactory(match=match)
        resp = client.get(f"/epl/match/{match.slug}/")
        assert "odds" in resp.context
        assert resp.context["best_home"] is not None

    def test_context_without_odds(self, client):
        match = MatchFactory()
        resp = client.get(f"/epl/match/{match.slug}/")
        assert resp.context["best_home"] is None

    def test_authenticated_user_sees_bet_form(self, authed_client):
        c, user = authed_client
        match = MatchFactory()
        resp = c.get(f"/epl/match/{match.slug}/")
        assert "form" in resp.context

    def test_unauthenticated_user_has_no_form(self, client):
        match = MatchFactory()
        resp = client.get(f"/epl/match/{match.slug}/")
        assert "form" not in resp.context

    def test_superuser_sees_match_notes_form(self, superuser_client):
        c, user = superuser_client
        match = MatchFactory()
        resp = c.get(f"/epl/match/{match.slug}/")
        assert "match_notes_form" in resp.context

    def test_standings_in_context(self, client):
        home = TeamFactory()
        away = TeamFactory()
        match = MatchFactory(home_team=home, away_team=away)
        StandingFactory(team=home, season=settings.EPL_CURRENT_SEASON)
        StandingFactory(team=away, season=settings.EPL_CURRENT_SEASON)
        resp = client.get(f"/epl/match/{match.slug}/")
        assert resp.context["home_standing"] is not None
        assert resp.context["away_standing"] is not None


class TestMatchStatusCardPartialView:
    def test_scheduled_match_renders_hype_card(self, client):
        match = MatchFactory(status=Match.Status.SCHEDULED)
        resp = client.get(f"/epl/match/{match.slug}/status-card/")
        assert resp.status_code == 200
        templates = [t.name for t in resp.templates]
        assert "matches/partials/hype_card.html" in templates

    def test_finished_match_renders_recap_card(self, client):
        match = MatchFactory(
            status=Match.Status.FINISHED,
            home_score=2,
            away_score=1,
        )
        resp = client.get(f"/epl/match/{match.slug}/status-card/")
        assert resp.status_code == 200
        templates = [t.name for t in resp.templates]
        assert "matches/partials/recap_card.html" in templates

    def test_in_play_match_renders_live_card(self, client):
        match = MatchFactory(
            status=Match.Status.IN_PLAY,
            home_score=1,
            away_score=0,
        )
        resp = client.get(f"/epl/match/{match.slug}/status-card/")
        assert resp.status_code == 200
        templates = [t.name for t in resp.templates]
        assert "matches/partials/live_card.html" in templates


class TestMatchNotesView:
    def test_non_superuser_forbidden(self, authed_client):
        c, user = authed_client
        match = MatchFactory()
        resp = c.post(f"/epl/match/{match.slug}/notes/", {"body": "test notes"})
        assert resp.status_code == 403

    def test_superuser_can_create_notes(self, superuser_client):
        c, user = superuser_client
        match = MatchFactory()
        resp = c.post(f"/epl/match/{match.slug}/notes/", {"body": "Great match!"})
        assert resp.status_code == 200


class TestLeaderboardView:
    def test_renders(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/leaderboard/")
        assert resp.status_code == 200

    def test_board_type_filter(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/leaderboard/?type=profit")
        assert resp.status_code == 200
        assert resp.context["board_type"] == "profit"

    def test_invalid_board_type_defaults_to_balance(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/leaderboard/?type=invalid")
        assert resp.context["board_type"] == "balance"

    def test_htmx_returns_partial(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/leaderboard/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        templates = [t.name for t in resp.templates]
        assert "matches/partials/leaderboard_table.html" in templates


class TestLeagueTableView:
    def test_renders(self, client):
        resp = client.get("/epl/table/")
        assert resp.status_code == 200
        assert "standings" in resp.context

    def test_includes_form_by_team(self, client):
        team = TeamFactory()
        StandingFactory(team=team, season=settings.EPL_CURRENT_SEASON, position=1)
        MatchFactory(
            home_team=team,
            away_team=TeamFactory(),
            status=Match.Status.FINISHED,
            home_score=2,
            away_score=0,
            season=settings.EPL_CURRENT_SEASON,
        )
        resp = client.get("/epl/table/")
        assert "form_by_team" in resp.context
        assert team.pk in resp.context["form_by_team"]
