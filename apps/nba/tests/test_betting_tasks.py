"""Tests for betting/tasks.py (generate_odds, settle_pending_bets, _odds_changed)."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from games.models import GameStatus

from betting.tasks import _odds_changed, generate_odds, settle_pending_bets
from tests.factories import (
    BetSlipFactory,
    GameFactory,
    OddsFactory,
    UserBalanceFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestOddsChanged:
    def test_detects_changed_home_moneyline(self):
        game = GameFactory()
        existing = OddsFactory(game=game, home_moneyline=-150, away_moneyline=130, spread_line=-3.5, total_line=222.5)
        new = {"home_moneyline": -160, "away_moneyline": 130, "spread_line": -3.5, "total_line": 222.5}
        assert _odds_changed(existing, new) is True

    def test_detects_changed_away_moneyline(self):
        game = GameFactory()
        existing = OddsFactory(game=game, home_moneyline=-150, away_moneyline=130, spread_line=-3.5, total_line=222.5)
        new = {"home_moneyline": -150, "away_moneyline": 140, "spread_line": -3.5, "total_line": 222.5}
        assert _odds_changed(existing, new) is True

    def test_detects_changed_spread_line(self):
        game = GameFactory()
        existing = OddsFactory(game=game, home_moneyline=-150, away_moneyline=130, spread_line=-3.5, total_line=222.5)
        new = {"home_moneyline": -150, "away_moneyline": 130, "spread_line": -5.0, "total_line": 222.5}
        assert _odds_changed(existing, new) is True

    def test_detects_changed_total_line(self):
        game = GameFactory()
        existing = OddsFactory(game=game, home_moneyline=-150, away_moneyline=130, spread_line=-3.5, total_line=222.5)
        new = {"home_moneyline": -150, "away_moneyline": 130, "spread_line": -3.5, "total_line": 225.0}
        assert _odds_changed(existing, new) is True

    def test_unchanged_odds_returns_false(self):
        game = GameFactory()
        existing = OddsFactory(game=game, home_moneyline=-150, away_moneyline=130, spread_line=-3.5, total_line=222.5)
        new = {"home_moneyline": -150, "away_moneyline": 130, "spread_line": -3.5, "total_line": 222.5}
        assert _odds_changed(existing, new) is False


@pytest.mark.django_db
class TestGenerateOddsTask:
    @patch("betting.tasks.generate_all_upcoming_odds")
    def test_creates_new_odds_records(self, mock_generate):
        game = GameFactory(status=GameStatus.SCHEDULED)
        mock_generate.return_value = [
            {
                "game": game,
                "home_moneyline": -150,
                "away_moneyline": 130,
                "spread_line": -3.5,
                "spread_home": -110,
                "spread_away": -110,
                "total_line": 222.5,
                "over_odds": -110,
                "under_odds": -110,
            }
        ]

        with patch("activity.services.queue_activity_event"):
            generate_odds()

        from games.models import Odds
        assert Odds.objects.filter(game=game, bookmaker="House").exists()

    @patch("betting.tasks.generate_all_upcoming_odds")
    def test_updates_existing_odds_when_changed(self, mock_generate):
        game = GameFactory(status=GameStatus.SCHEDULED)
        existing = OddsFactory(
            game=game,
            bookmaker="House",
            home_moneyline=-150,
            away_moneyline=130,
            spread_line=-3.5,
            total_line=222.5,
        )
        mock_generate.return_value = [
            {
                "game": game,
                "home_moneyline": -200,
                "away_moneyline": 170,
                "spread_line": -5.0,
                "spread_home": -110,
                "spread_away": -110,
                "total_line": 225.0,
                "over_odds": -110,
                "under_odds": -110,
            }
        ]

        generate_odds()

        existing.refresh_from_db()
        assert existing.home_moneyline == -200
        assert existing.away_moneyline == 170

    @patch("betting.tasks.generate_all_upcoming_odds")
    def test_skips_update_when_odds_unchanged(self, mock_generate):
        game = GameFactory(status=GameStatus.SCHEDULED)
        OddsFactory(
            game=game,
            bookmaker="House",
            home_moneyline=-150,
            away_moneyline=130,
            spread_line=-3.5,
            total_line=222.5,
        )
        mock_generate.return_value = [
            {
                "game": game,
                "home_moneyline": -150,
                "away_moneyline": 130,
                "spread_line": -3.5,
                "spread_home": -110,
                "spread_away": -110,
                "total_line": 222.5,
                "over_odds": -110,
                "under_odds": -110,
            }
        ]

        from games.models import Odds
        count_before = Odds.objects.count()
        generate_odds()
        assert Odds.objects.count() == count_before

    @patch("betting.tasks.generate_all_upcoming_odds", return_value=[])
    def test_empty_results_does_not_raise(self, mock_generate):
        generate_odds()  # Should complete without error

    @patch("betting.tasks.generate_all_upcoming_odds")
    def test_queues_activity_event_when_odds_created(self, mock_generate):
        game = GameFactory(status=GameStatus.SCHEDULED)
        mock_generate.return_value = [
            {
                "game": game,
                "home_moneyline": -150,
                "away_moneyline": 130,
                "spread_line": -3.5,
                "spread_home": -110,
                "spread_away": -110,
                "total_line": 222.5,
                "over_odds": -110,
                "under_odds": -110,
            }
        ]

        with patch("activity.services.queue_activity_event") as mock_queue:
            generate_odds()

        mock_queue.assert_called_once()


@pytest.mark.django_db
class TestSettlePendingBetsTask:
    def test_settles_final_games_with_pending_bets(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        game = GameFactory(status=GameStatus.FINAL, home_score=110, away_score=100)
        BetSlipFactory(
            user=user,
            game=game,
            market="MONEYLINE",
            selection="HOME",
            odds_at_placement=-150,
            stake=Decimal("50.00"),
        )

        result = settle_pending_bets()

        assert result["games_settled"] == 1

    def test_skips_non_final_games(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        game = GameFactory(status=GameStatus.SCHEDULED)
        BetSlipFactory(user=user, game=game)

        result = settle_pending_bets()

        assert result["games_settled"] == 0

    def test_no_pending_bets_returns_zero(self):
        result = settle_pending_bets()
        assert result["games_settled"] == 0

    def test_multiple_final_games_settled(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        game1 = GameFactory(status=GameStatus.FINAL, home_score=110, away_score=100)
        game2 = GameFactory(status=GameStatus.FINAL, home_score=90, away_score=95)
        BetSlipFactory(user=user, game=game1, stake=Decimal("50.00"))
        BetSlipFactory(user=user, game=game2, stake=Decimal("50.00"))

        result = settle_pending_bets()

        assert result["games_settled"] == 2
