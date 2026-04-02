"""Tests for news Celery tasks — recap polling, roundup dispatch, and generation."""

from unittest.mock import MagicMock, patch

import pytest

from news.models import NewsArticle
from news.tasks import (
    _resolve_game,
    generate_game_recap_task,
    generate_pending_recaps,
    generate_weekly_roundup_task,
)

from .factories import NewsArticleFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# generate_pending_recaps
# ---------------------------------------------------------------------------


class TestGeneratePendingRecaps:
    @patch("news.tasks.generate_game_recap_task")
    def test_dispatches_for_final_nba_games(self, mock_task):
        from nba.games.models import GameStatus
        from nba.tests.factories import GameFactory

        game = GameFactory(status=GameStatus.FINAL)
        result = generate_pending_recaps()
        assert result["dispatched"] >= 1
        mock_task.delay.assert_any_call(game.id_hash, "nba")

    @patch("news.tasks.generate_game_recap_task")
    def test_skips_games_with_existing_recaps(self, mock_task):
        from nba.games.models import GameStatus
        from nba.tests.factories import GameFactory

        game = GameFactory(status=GameStatus.FINAL)
        # Create an existing recap for this game
        NewsArticleFactory(
            league="nba",
            article_type=NewsArticle.ArticleType.RECAP,
            game_id_hash=game.id_hash,
        )
        generate_pending_recaps()
        # Should not dispatch for this game
        for call in mock_task.delay.call_args_list:
            assert call[0] != (game.id_hash, "nba")

    @patch("news.tasks.generate_game_recap_task")
    def test_skips_non_final_games(self, mock_task):
        from nba.games.models import GameStatus
        from nba.tests.factories import GameFactory

        GameFactory(status=GameStatus.SCHEDULED)
        GameFactory(status=GameStatus.IN_PROGRESS)
        generate_pending_recaps()
        # mock_task.delay should not be called with these games
        nba_calls = [c for c in mock_task.delay.call_args_list if c[0][1] == "nba"]
        assert len(nba_calls) == 0

    @patch("news.tasks.generate_game_recap_task")
    def test_dispatches_for_final_nfl_games(self, mock_task):
        from nfl.games.models import GameStatus as NflStatus
        from nfl.tests.factories import GameFactory as NflGameFactory

        game = NflGameFactory(status=NflStatus.FINAL)
        generate_pending_recaps()
        mock_task.delay.assert_any_call(game.id_hash, "nfl")

    @patch("news.tasks.generate_game_recap_task")
    def test_dispatches_for_final_ot_nfl_games(self, mock_task):
        from nfl.games.models import GameStatus as NflStatus
        from nfl.tests.factories import GameFactory as NflGameFactory

        game = NflGameFactory(status=NflStatus.FINAL_OT)
        generate_pending_recaps()
        mock_task.delay.assert_any_call(game.id_hash, "nfl")


# ---------------------------------------------------------------------------
# generate_game_recap_task
# ---------------------------------------------------------------------------


class TestGenerateGameRecapTask:
    @patch("news.article_service.generate_game_recap")
    def test_calls_service_for_valid_game(self, mock_generate):
        from nba.games.models import GameStatus
        from nba.tests.factories import GameFactory

        game = GameFactory(status=GameStatus.FINAL)
        mock_generate.return_value = MagicMock(id_hash="xyz123")

        result = generate_game_recap_task(game.id_hash, "nba")
        mock_generate.assert_called_once()
        assert result["status"] == "created"

    def test_returns_not_found_for_missing_game(self):
        result = generate_game_recap_task("ZZZZZZZZ", "nba")
        assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# _resolve_game
# ---------------------------------------------------------------------------


class TestResolveGame:
    def test_resolves_nba_game(self):
        from nba.tests.factories import GameFactory

        game = GameFactory()
        resolved = _resolve_game(game.id_hash, "nba")
        assert resolved is not None
        assert resolved.pk == game.pk

    def test_resolves_nfl_game(self):
        from nfl.tests.factories import GameFactory as NflGameFactory

        game = NflGameFactory()
        resolved = _resolve_game(game.id_hash, "nfl")
        assert resolved is not None
        assert resolved.pk == game.pk

    def test_returns_none_for_invalid_hash(self):
        resolved = _resolve_game("ZZZZZZZZ", "nba")
        assert resolved is None

    def test_returns_none_for_invalid_league(self):
        resolved = _resolve_game("abc12345", "invalid")
        assert resolved is None


# ---------------------------------------------------------------------------
# generate_weekly_roundup_task
# ---------------------------------------------------------------------------


class TestGenerateWeeklyRoundupTask:
    @patch("news.article_service.generate_weekly_roundup")
    def test_calls_service(self, mock_generate):
        mock_generate.return_value = MagicMock(id_hash="roundup123")
        result = generate_weekly_roundup_task("nba")
        mock_generate.assert_called_once_with("nba")
        assert result["status"] == "created"

    @patch("news.article_service.generate_weekly_roundup")
    def test_returns_skipped_when_none(self, mock_generate):
        mock_generate.return_value = None
        result = generate_weekly_roundup_task("nba")
        assert result["status"] == "skipped"

    @patch("news.article_service.generate_weekly_roundup")
    def test_retries_on_exception(self, mock_generate):
        mock_generate.side_effect = Exception("API error")
        with pytest.raises(Exception):
            generate_weekly_roundup_task("nba")
