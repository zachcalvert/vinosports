"""Tests for player list and detail views."""

import pytest
from django.test import Client

from nba.games.models import GameStatus, PlayerBoxScore
from nba.tests.factories import GameFactory, PlayerFactory, TeamFactory, UserFactory


@pytest.mark.django_db
class TestPlayerListView:
    def setup_method(self):
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_renders_all_active_players(self):
        PlayerFactory(is_active=True)
        PlayerFactory(is_active=True)
        resp = self.client.get("/nba/games/players/")
        assert resp.status_code == 200
        assert len(resp.context["players"]) == 2

    def test_filters_by_team(self):
        team = TeamFactory(abbreviation="LAL")
        PlayerFactory(team=team, is_active=True)
        PlayerFactory(is_active=True)  # different team
        resp = self.client.get("/nba/games/players/?team=LAL")
        assert resp.status_code == 200
        assert all(p.team.abbreviation == "LAL" for p in resp.context["players"])

    def test_filters_by_position(self):
        PlayerFactory(position="G", is_active=True)
        PlayerFactory(position="C", is_active=True)
        resp = self.client.get("/nba/games/players/?position=G")
        assert resp.status_code == 200
        assert all("G" in p.position for p in resp.context["players"])

    def test_excludes_inactive_players_by_default(self):
        PlayerFactory(is_active=False)
        PlayerFactory(is_active=True)
        resp = self.client.get("/nba/games/players/")
        assert resp.status_code == 200
        assert all(p.is_active for p in resp.context["players"])


@pytest.mark.django_db
class TestPlayerDetailView:
    def setup_method(self):
        self.client = Client()
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_renders_player_profile(self):
        player = PlayerFactory()
        resp = self.client.get(f"/nba/games/players/{player.id_hash}/")
        assert resp.status_code == 200
        assert resp.context["player"] == player

    def test_shows_season_averages_when_box_scores_exist(self):
        team = TeamFactory()
        player = PlayerFactory(team=team)
        game = GameFactory(
            home_team=team,
            status=GameStatus.FINAL,
            season=2025,
            postseason=False,
        )
        PlayerBoxScore.objects.create(
            game=game,
            team=team,
            player=player,
            player_external_id=player.external_id,
            player_name=player.full_name,
            points=30,
            reb=10,
            ast=5,
        )
        resp = self.client.get(f"/nba/games/players/{player.id_hash}/")
        assert resp.status_code == 200
        assert resp.context["averages"]["games_played"] == 1
        assert resp.context["averages"]["ppg"] == 30.0

    def test_shows_empty_state_when_no_box_scores(self):
        player = PlayerFactory()
        resp = self.client.get(f"/nba/games/players/{player.id_hash}/")
        assert resp.status_code == 200
        assert resp.context["averages"]["games_played"] == 0

    def test_404_for_unknown_id_hash(self):
        resp = self.client.get("/nba/games/players/nonexistent/")
        assert resp.status_code == 404

    def test_requires_login_redirects_anonymous(self):
        player = PlayerFactory()
        anon_client = Client()
        resp = anon_client.get(f"/nba/games/players/{player.id_hash}/")
        assert resp.status_code == 302
        assert "/login/" in resp.url
