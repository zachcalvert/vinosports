"""Tests for team detail view."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from nba.games.models import GameStatus
from nba.tests.factories import (
    GameFactory,
    PlayerFactory,
    StandingFactory,
    TeamFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestTeamDetailView:
    def setup_method(self):
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_renders_team_page(self):
        team = TeamFactory(abbreviation="LAL")
        resp = self.client.get("/nba/games/teams/lal/")
        assert resp.status_code == 200
        assert resp.context["team"] == team

    def test_case_insensitive_abbreviation(self):
        team = TeamFactory(abbreviation="BOS")
        resp = self.client.get("/nba/games/teams/BOS/")
        assert resp.status_code == 200
        assert resp.context["team"] == team

    def test_shows_standing_when_exists(self):
        team = TeamFactory()
        StandingFactory(team=team, season=2025)
        resp = self.client.get(f"/nba/games/teams/{team.abbreviation.lower()}/")
        assert resp.status_code == 200
        assert resp.context["standing"] is not None

    def test_handles_no_standing_gracefully(self):
        team = TeamFactory()
        resp = self.client.get(f"/nba/games/teams/{team.abbreviation.lower()}/")
        assert resp.status_code == 200
        assert resp.context["standing"] is None

    def test_shows_active_roster_only(self):
        team = TeamFactory()
        PlayerFactory(team=team, is_active=True)
        PlayerFactory(team=team, is_active=True)
        PlayerFactory(team=team, is_active=False)
        resp = self.client.get(f"/nba/games/teams/{team.abbreviation.lower()}/")
        assert resp.status_code == 200
        assert len(resp.context["roster"]) == 2

    def test_shows_last_game_when_final(self):
        team = TeamFactory()
        GameFactory(
            home_team=team,
            status=GameStatus.FINAL,
            home_score=110,
            away_score=105,
            game_date=timezone.localdate() - timedelta(days=1),
        )
        resp = self.client.get(f"/nba/games/teams/{team.abbreviation.lower()}/")
        assert resp.status_code == 200
        assert resp.context["last_game"] is not None

    def test_shows_next_game_when_scheduled(self):
        team = TeamFactory()
        GameFactory(
            home_team=team,
            status=GameStatus.SCHEDULED,
            game_date=timezone.localdate() + timedelta(days=1),
        )
        resp = self.client.get(f"/nba/games/teams/{team.abbreviation.lower()}/")
        assert resp.status_code == 200
        assert resp.context["next_game"] is not None

    def test_404_for_unknown_abbreviation(self):
        resp = self.client.get("/nba/games/teams/zzz/")
        assert resp.status_code == 404

    def test_requires_login_redirects_anonymous(self):
        team = TeamFactory()
        anon_client = Client()
        resp = anon_client.get(f"/nba/games/teams/{team.abbreviation.lower()}/")
        assert resp.status_code == 302
        assert "/login/" in resp.url
