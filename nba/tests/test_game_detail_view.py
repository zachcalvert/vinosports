"""Tests for GameDetailView with bet form rendering."""

import pytest
from django.test import Client

from nba.games.models import GameStatus
from nba.tests.factories import (
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
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.status_code in (301, 302)

    def test_authenticated_user_gets_200(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.status_code == 200

    def test_uses_game_detail_template(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.status_code == 200
        assert "games/game_detail.html" in [t.name for t in response.templates]

    def test_context_contains_bet_form(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert "bet_form" in response.context

    def test_context_contains_best_odds_when_available(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        odds = OddsFactory(game=game)
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.context["best_odds"] == odds

    def test_context_best_odds_is_none_when_no_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.context["best_odds"] is None

    def test_bet_form_partial_is_included(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game)
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "bet-form-container" in content

    def test_bet_form_shows_moneyline_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game, home_moneyline=-150, away_moneyline=130)
        response = c.get(f"/nba/games/{game.id_hash}/")
        content = response.content.decode()
        assert "-150" in content
        assert "+130" in content

    def test_bet_form_shows_spread_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game, spread_line=-3.5, spread_home=-110, spread_away=-110)
        response = c.get(f"/nba/games/{game.id_hash}/")
        content = response.content.decode()
        assert "-3.5" in content
        assert "+3.5" in content

    def test_bet_form_shows_total_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(game=game, total_line=222.5, over_odds=-110, under_odds=-110)
        response = c.get(f"/nba/games/{game.id_hash}/")
        content = response.content.decode()
        assert "222.5" in content
        assert "Over" in content
        assert "Under" in content

    def test_bet_form_shows_no_odds_message_when_no_odds(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        response = c.get(f"/nba/games/{game.id_hash}/")
        content = response.content.decode()
        assert "No odds available" in content

    def test_bet_form_hidden_for_non_scheduled_game(self, auth_client):
        c, user = auth_client
        game = GameFactory(status=GameStatus.FINAL)
        response = c.get(f"/nba/games/{game.id_hash}/")
        content = response.content.decode()
        assert "Betting is closed" in content

    def test_nonexistent_game_returns_404(self, auth_client):
        c, user = auth_client
        response = c.get("/nba/games/nonexistent/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestGameDetailViewSentiment:
    """Tests covering _get_game_sentiment, _get_spread_sentiment, _get_total_sentiment."""

    def test_moneyline_sentiment_when_bets_exist(self, auth_client):
        """_get_game_sentiment returns non-None when moneyline bets exist."""
        from decimal import Decimal
        from nba.betting.models import BetSlip
        from nba.tests.factories import BetSlipFactory

        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        BetSlipFactory(
            game=game,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
        )
        BetSlipFactory(
            game=game,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.AWAY,
        )
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.status_code == 200
        sentiment = response.context.get("sentiment")
        assert sentiment is not None
        assert "home_pct" in sentiment
        assert "away_pct" in sentiment

    def test_spread_sentiment_when_spread_bets_exist(self, auth_client):
        """_get_spread_sentiment returns non-None when spread bets exist."""
        from nba.betting.models import BetSlip
        from nba.tests.factories import BetSlipFactory

        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        BetSlipFactory(
            game=game,
            market=BetSlip.Market.SPREAD,
            selection=BetSlip.Selection.HOME,
        )
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.status_code == 200
        spread_sentiment = response.context.get("spread_sentiment")
        assert spread_sentiment is not None
        assert "home_pct" in spread_sentiment

    def test_total_sentiment_when_total_bets_exist(self, auth_client):
        """_get_total_sentiment returns non-None when total bets exist."""
        from nba.betting.models import BetSlip
        from nba.tests.factories import BetSlipFactory

        c, user = auth_client
        game = GameFactory(status=GameStatus.SCHEDULED)
        BetSlipFactory(
            game=game,
            market=BetSlip.Market.TOTAL,
            selection=BetSlip.Selection.OVER,
        )
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.status_code == 200
        total_sentiment = response.context.get("total_sentiment")
        assert total_sentiment is not None
        assert "over_pct" in total_sentiment


@pytest.mark.django_db
class TestGameDetailViewRecap:
    """Tests covering _get_recap_context for FINAL games."""

    def test_recap_context_included_for_final_game(self, auth_client):
        """For a FINAL game, recap_ctx is populated with result_context."""
        c, user = auth_client
        game = GameFactory(
            status=GameStatus.FINAL,
            home_score=100,
            away_score=115,
        )
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.status_code == 200
        assert "result_context" in response.context
        assert "headline" in response.context["result_context"]

    def test_away_team_wins_recap(self, auth_client):
        """When away score > home score, actual_result is AWAY."""
        c, user = auth_client
        game = GameFactory(
            status=GameStatus.FINAL,
            home_score=90,
            away_score=110,
        )
        response = c.get(f"/nba/games/{game.id_hash}/")
        assert response.status_code == 200
        assert response.context.get("actual_result") == "AWAY"
