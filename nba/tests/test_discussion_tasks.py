"""Tests for pregame/postgame bot comment generation tasks."""

from unittest.mock import patch

import pytest

from nba.activity.models import ActivityEvent
from nba.discussions.models import Comment
from nba.discussions.tasks import generate_postgame_comments, generate_pregame_comments
from nba.games.models import GameStatus
from nba.tests.factories import (
    BotProfileFactory,
    CommentFactory,
    GameFactory,
)


@pytest.fixture
def mock_claude():
    """Mock the Claude API so no real API calls are made."""
    with patch("nba.discussions.tasks._generate_comment_body") as mock:
        mock.return_value = "This is going to be a great game!"
        yield mock


# ---------------------------------------------------------------------------
# generate_pregame_comments
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGeneratePregameComments:
    def test_creates_comments_for_scheduled_games(self, mock_claude):
        game = GameFactory(status=GameStatus.SCHEDULED)
        BotProfileFactory(is_active=True)

        with patch("nba.discussions.tasks.roll_action", return_value=True):
            result = generate_pregame_comments()

        assert result["commented"] >= 1
        assert Comment.objects.filter(game=game).exists()

    def test_skips_when_no_games(self, mock_claude):
        BotProfileFactory(is_active=True)
        # No scheduled games
        result = generate_pregame_comments()
        assert result["commented"] == 0

    def test_skips_when_no_bots(self, mock_claude):
        GameFactory(status=GameStatus.SCHEDULED)
        # No bot profiles
        result = generate_pregame_comments()
        assert result["commented"] == 0

    def test_skips_bot_already_commented(self, mock_claude):
        game = GameFactory(status=GameStatus.SCHEDULED)
        profile = BotProfileFactory(is_active=True)
        # Bot already commented on this game
        CommentFactory(user=profile.user, game=game)

        with patch("nba.discussions.tasks.roll_action", return_value=True):
            result = generate_pregame_comments()

        assert result["commented"] == 0

    def test_skips_when_roll_fails(self, mock_claude):
        GameFactory(status=GameStatus.SCHEDULED)
        BotProfileFactory(is_active=True)

        with patch("nba.discussions.tasks.roll_action", return_value=False):
            result = generate_pregame_comments()

        assert result["commented"] == 0

    def test_respects_max_comments_cap(self, mock_claude):
        """Bot should stop commenting when window max_comments is reached."""
        GameFactory(status=GameStatus.SCHEDULED)
        GameFactory(status=GameStatus.SCHEDULED)
        profile = BotProfileFactory(is_active=True)

        # Create existing comments to fill the cap
        for _ in range(3):
            g = GameFactory(status=GameStatus.SCHEDULED)
            CommentFactory(user=profile.user, game=g)

        with (
            patch("nba.discussions.tasks.roll_action", return_value=True),
            patch("nba.discussions.tasks.get_active_window") as mock_window,
        ):
            mock_window.return_value = {
                "comment_probability": 1.0,
                "max_comments": 3,
            }
            result = generate_pregame_comments()

        assert result["commented"] == 0

    def test_creates_activity_event(self, mock_claude):
        GameFactory(status=GameStatus.SCHEDULED)
        BotProfileFactory(is_active=True)

        with patch("nba.discussions.tasks.roll_action", return_value=True):
            generate_pregame_comments()

        assert ActivityEvent.objects.filter(
            event_type=ActivityEvent.EventType.BOT_COMMENT
        ).exists()

    def test_handles_api_failure_gracefully(self):
        game = GameFactory(status=GameStatus.SCHEDULED)
        BotProfileFactory(is_active=True)

        with (
            patch(
                "nba.discussions.tasks._generate_comment_body",
                side_effect=Exception("API error"),
            ),
            patch("nba.discussions.tasks.roll_action", return_value=True),
        ):
            result = generate_pregame_comments()

        # Should not crash, just skip
        assert result["commented"] == 0
        assert not Comment.objects.filter(game=game).exists()


# ---------------------------------------------------------------------------
# generate_postgame_comments
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGeneratePostgameComments:
    def test_creates_comments_for_final_games(self, mock_claude):
        game = GameFactory(status=GameStatus.FINAL, home_score=110, away_score=95)
        BotProfileFactory(is_active=True)

        with patch("nba.discussions.tasks.roll_action", return_value=True):
            result = generate_postgame_comments()

        assert result["commented"] >= 1
        assert Comment.objects.filter(game=game).exists()

    def test_skips_non_final_games(self, mock_claude):
        GameFactory(status=GameStatus.SCHEDULED)
        BotProfileFactory(is_active=True)

        result = generate_postgame_comments()
        assert result["commented"] == 0

    def test_skips_bot_already_commented(self, mock_claude):
        game = GameFactory(status=GameStatus.FINAL, home_score=110, away_score=95)
        profile = BotProfileFactory(is_active=True)
        CommentFactory(user=profile.user, game=game)

        with patch("nba.discussions.tasks.roll_action", return_value=True):
            result = generate_postgame_comments()

        assert result["commented"] == 0
