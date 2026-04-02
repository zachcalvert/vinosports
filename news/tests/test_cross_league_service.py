"""Tests for cross-league article generation in article_service."""

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from news.article_service import (
    _build_cross_league_prompt,
    _get_last_week_range,
    generate_cross_league_article,
)
from news.models import NewsArticle

from .factories import BotProfileFactory, UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# _build_cross_league_prompt
# ---------------------------------------------------------------------------


class TestBuildCrossLeaguePrompt:
    def test_returns_none_when_no_data(self):
        prompt = _build_cross_league_prompt()
        assert prompt is None

    def test_includes_nba_section_when_games_exist(self):
        from nba.games.models import GameStatus
        from nba.tests.factories import GameFactory

        start, _ = _get_last_week_range()
        GameFactory(
            status=GameStatus.FINAL,
            game_date=start,
            home_score=110,
            away_score=98,
        )

        prompt = _build_cross_league_prompt()
        assert prompt is not None
        assert "NBA" in prompt
        assert "110" in prompt

    def test_includes_epl_section_when_matches_exist(self):
        from epl.matches.models import Match
        from epl.tests.factories import MatchFactory

        start, _ = _get_last_week_range()
        kickoff = timezone.now().replace(
            year=start.year, month=start.month, day=start.day, hour=15
        )
        MatchFactory(
            status=Match.Status.FINISHED,
            kickoff=kickoff,
            home_score=2,
            away_score=0,
        )

        prompt = _build_cross_league_prompt()
        assert prompt is not None
        assert "Premier League" in prompt

    def test_includes_nfl_section_when_games_exist(self):
        from nfl.games.models import GameStatus
        from nfl.tests.factories import GameFactory

        start, _ = _get_last_week_range()
        GameFactory(
            status=GameStatus.FINAL,
            game_date=start,
            home_score=31,
            away_score=17,
            week=5,
        )

        prompt = _build_cross_league_prompt()
        assert prompt is not None
        assert "NFL" in prompt
        assert "Week 5" in prompt

    def test_combines_multiple_leagues(self):
        from nba.games.models import GameStatus as NbaStatus
        from nba.tests.factories import GameFactory as NbaGameFactory
        from nfl.games.models import GameStatus as NflStatus
        from nfl.tests.factories import GameFactory as NflGameFactory

        start, _ = _get_last_week_range()
        NbaGameFactory(
            status=NbaStatus.FINAL,
            game_date=start,
            home_score=105,
            away_score=99,
        )
        NflGameFactory(
            status=NflStatus.FINAL,
            game_date=start,
            home_score=24,
            away_score=21,
        )

        prompt = _build_cross_league_prompt()
        assert prompt is not None
        assert "NBA" in prompt
        assert "NFL" in prompt

    def test_includes_format_instructions(self):
        from nba.games.models import GameStatus
        from nba.tests.factories import GameFactory

        start, _ = _get_last_week_range()
        GameFactory(
            status=GameStatus.FINAL, game_date=start, home_score=100, away_score=90
        )

        prompt = _build_cross_league_prompt()
        assert "TITLE:" in prompt
        assert "SUBTITLE:" in prompt
        assert "cross-league" in prompt.lower()
        assert "4-6 paragraphs" in prompt

    def test_includes_leaderboard_when_stats_exist(self):
        from nba.games.models import GameStatus
        from nba.tests.factories import GameFactory
        from vinosports.betting.models import UserStats

        start, _ = _get_last_week_range()
        GameFactory(
            status=GameStatus.FINAL, game_date=start, home_score=100, away_score=90
        )

        user = UserFactory()
        UserStats.objects.create(
            user=user,
            total_bets=20,
            total_wins=15,
            total_losses=5,
            net_profit=500,
        )

        prompt = _build_cross_league_prompt()
        assert "leaderboard" in prompt.lower() or "Cross-league" in prompt


# ---------------------------------------------------------------------------
# generate_cross_league_article — end-to-end
# ---------------------------------------------------------------------------


class TestGenerateCrossLeagueArticle:
    @pytest.fixture(autouse=True)
    def _setup_games(self):
        from nba.games.models import GameStatus
        from nba.tests.factories import GameFactory

        start, _ = _get_last_week_range()
        self.game = GameFactory(
            status=GameStatus.FINAL,
            game_date=start,
            home_score=110,
            away_score=102,
        )

    @patch("news.article_service.anthropic.Anthropic")
    def test_successful_generation(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="", epl_team_tla="", nfl_team_abbr="")

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=(
                    "TITLE: The Weekend Sports Smorgasbord — Three Leagues, One Wild Ride\n"
                    "SUBTITLE: From Premier League drama to NBA upsets, here's your weekend preview.\n"
                    "If you thought last week was wild across the sporting landscape, buckle up — "
                    "this weekend promises even more chaos. The Premier League title race is "
                    "heating up, the NBA playoff picture is taking shape, and the NFL just "
                    "delivered another week of pure madness.\n\n"
                    "On the betting front, spread bettors have been cleaning up across all "
                    "three leagues. The public is fading favorites and it's working. If "
                    "you're not on the contrarian train yet, the data says you should be.\n\n"
                    "Looking ahead to this weekend, there are several marquee matchups that "
                    "could define the season in each league. The smart money is already "
                    "moving on a few of these lines."
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        article = generate_cross_league_article()

        assert article is not None
        assert "Smorgasbord" in article.title
        assert article.league == ""  # cross-league
        assert article.article_type == NewsArticle.ArticleType.CROSS_LEAGUE
        assert article.status == NewsArticle.Status.DRAFT
        assert article.published_at is None

    def test_no_bot_returns_none(self):
        article = generate_cross_league_article()
        assert article is None

    @patch("news.article_service.anthropic.Anthropic")
    def test_api_failure_returns_none(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="")

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        article = generate_cross_league_article()
        assert article is None

    def test_no_games_returns_none(self):
        from nba.games.models import Game

        Game.objects.all().delete()
        BotProfileFactory(nba_team_abbr="")

        article = generate_cross_league_article()
        assert article is None

    @patch("news.article_service.anthropic.Anthropic")
    def test_uses_roundup_max_tokens(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="")

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=(
                    "TITLE: Cross-League Weekend Preview\n"
                    "SUBTITLE: A look across all three leagues.\n"
                    "The NBA season rolls on with plenty of drama this week. "
                    "Multiple games went down to the wire and the betting lines "
                    "were all over the place across every league."
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        generate_cross_league_article()

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 1200
