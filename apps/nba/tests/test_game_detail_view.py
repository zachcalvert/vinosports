"""Tests for GameDetailView with bet form rendering."""

import pytest
from django.test import Client
from games.models import GameStatus

from tests.factories import (
    GameFactory,
    OddsFactory,
    UserBalanceFactory,
    UserFactory,
)


@pytest.fixture
def auth_client(db):
    user = UserFactory()
    UserBalanceFactory(user=user)
    c = Client()
    c.force_login(user)
    return c, user


@pytest.mark.django_db
class TestGameDetailView:
    def test_unauthenticated_redirected(self):
        c = Client()
        game = GameFactory()
        response = c.get(f"/games/{game.id_hash}/")
        assert response.status_code in (301, 302)

    def test_authenticated_user_gets_200(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.get(f"/games/{game.id_hash}/")
        assert response.status_code == 200

    def test_uses_game_detail_template(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        response = c.get(f"/games/{game.id_hash}/")
        assert response.status_code == 200
        assert "games/game_detail.html" in [t.name for t in response.templates]

    def test_context_contains_bet_form(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.get(f"/games/{game.id_hash}/")
        assert "bet_form" in response.context

    def test_context_contains_best_odds_when_available(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        odds = OddsFactory(game=game)
        response = c.get(f"/games/{game.id_hash}/")
        assert response.context["best_odds"] == odds

    def test_context_best_odds_is_none_when_no_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.get(f"/games/{game.id_hash}/")
        assert response.context["best_odds"] is None

    def test_bet_form_partial_is_included(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game)
        response = c.get(f"/games/{game.id_hash}/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "bet-form-container" in content

    def test_bet_form_shows_moneyline_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game, home_moneyline=-150, away_moneyline=130)
        response = c.get(f"/games/{game.id_hash}/")
        content = response.content.decode()
        assert "-150" in content
        assert "+130" in content

    def test_bet_form_shows_spread_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game, spread_line=-3.5, spread_home=-110, spread_away=-110)
        response = c.get(f"/games/{game.id_hash}/")
        content = response.content.decode()
        assert "-3.5" in content
        assert "+3.5" in content

    def test_bet_form_shows_total_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game, total_line=222.5, over_odds=-110, under_odds=-110)
        response = c.get(f"/games/{game.id_hash}/")
        content = response.content.decode()
        assert "222.5" in content
        assert "Over" in content
        assert "Under" in content

    def test_bet_form_shows_no_odds_message_when_no_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.get(f"/games/{game.id_hash}/")
        content = response.content.decode()
        assert "No odds available" in content

    def test_bet_form_hidden_for_non_scheduled_game(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.FINAL)
        response = c.get(f"/games/{game.id_hash}/")
        content = response.content.decode()
        assert "Betting is closed" in content

    def test_nonexistent_game_returns_404(self, auth_client):
        c, user = auth_client
        response = c.get("/games/nonexistent/")
        assert response.status_code == 404
