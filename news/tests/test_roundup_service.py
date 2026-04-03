"""Tests for weekly roundup generation in article_service."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from news.article_service import (
    _build_roundup_prompt,
    _get_last_week_range,
    _select_analyst_bot,
    generate_weekly_roundup,
)
from news.models import NewsArticle

from .factories import BotProfileFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# _get_last_week_range
# ---------------------------------------------------------------------------


class TestGetLastWeekRange:
    def test_returns_monday_to_sunday(self):
        start, end = _get_last_week_range()
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6  # Sunday
        assert end - start == timedelta(days=6)

    def test_range_is_in_the_past(self):
        start, end = _get_last_week_range()
        today = timezone.now().date()
        assert end < today


# ---------------------------------------------------------------------------
# _select_analyst_bot
# ---------------------------------------------------------------------------


class TestSelectAnalystBot:
    def test_prefers_unaffiliated_bot(self):
        """Bot with no team affiliation should be preferred."""
        BotProfileFactory(nba_team_abbr="LAL")  # affiliated
        neutral = BotProfileFactory(nba_team_abbr="")  # unaffiliated
        user = _select_analyst_bot("nba")
        assert user == neutral.user

    def test_falls_back_to_affiliated_bot(self):
        """If no unaffiliated bots, use any active bot."""
        affiliated = BotProfileFactory(nba_team_abbr="LAL")
        user = _select_analyst_bot("nba")
        assert user == affiliated.user

    def test_returns_none_when_no_bots(self):
        user = _select_analyst_bot("nba")
        assert user is None

    def test_respects_league_active_flag(self):
        """Bot inactive in the requested league should not be selected."""
        BotProfileFactory(nba_team_abbr="", active_in_nba=False)
        user = _select_analyst_bot("nba")
        assert user is None

    def test_epl_unaffiliated(self):
        neutral = BotProfileFactory(epl_team_tla="")
        user = _select_analyst_bot("epl")
        assert user == neutral.user

    def test_nfl_unaffiliated(self):
        neutral = BotProfileFactory(nfl_team_abbr="")
        user = _select_analyst_bot("nfl")
        assert user == neutral.user


# ---------------------------------------------------------------------------
# _build_roundup_prompt — NBA
# ---------------------------------------------------------------------------


class TestBuildNbaRoundup:
    @pytest.fixture(autouse=True)
    def _setup_games(self):
        """Create NBA games from last week."""
        from nba.games.models import GameStatus
        from nba.tests.factories import GameFactory

        start, end = _get_last_week_range()
        self.game1 = GameFactory(
            status=GameStatus.FINAL,
            game_date=start,
            home_score=110,
            away_score=102,
        )
        self.game2 = GameFactory(
            status=GameStatus.FINAL,
            game_date=end,
            home_score=98,
            away_score=105,
        )

    def test_returns_prompt_with_results(self):
        prompt = _build_roundup_prompt("nba", BotProfileFactory(nba_team_abbr=""))
        assert prompt is not None
        assert "Results this week" in prompt
        assert "110" in prompt
        assert "102" in prompt

    def test_includes_both_games(self):
        prompt = _build_roundup_prompt("nba", BotProfileFactory(nba_team_abbr=""))
        # Both games should appear
        assert "98" in prompt
        assert "105" in prompt

    def test_includes_format_instructions(self):
        prompt = _build_roundup_prompt("nba", BotProfileFactory(nba_team_abbr=""))
        assert "TITLE:" in prompt
        assert "SUBTITLE:" in prompt
        assert "4-6 paragraphs" in prompt
        assert "NBA" in prompt

    def test_returns_none_when_no_games(self):
        """If no games in the date range, return None."""
        from nba.games.models import Game

        Game.objects.all().delete()
        prompt = _build_roundup_prompt("nba", BotProfileFactory(nba_team_abbr=""))
        assert prompt is None


class TestBuildEplRoundup:
    @pytest.fixture(autouse=True)
    def _setup_matches(self):
        """Create EPL matches from last week."""
        from epl.matches.models import Match
        from epl.tests.factories import MatchFactory

        start, end = _get_last_week_range()
        # Set kickoff within the date range
        kickoff_time = timezone.now().replace(
            year=start.year, month=start.month, day=start.day, hour=15
        )
        self.match = MatchFactory(
            status=Match.Status.FINISHED,
            kickoff=kickoff_time,
            home_score=3,
            away_score=1,
        )

    def test_returns_prompt_with_results(self):
        prompt = _build_roundup_prompt("epl", BotProfileFactory(epl_team_tla=""))
        assert prompt is not None
        assert "Results this week" in prompt
        assert "Premier League" in prompt

    def test_returns_none_when_no_matches(self):
        from epl.matches.models import Match

        Match.objects.all().delete()
        prompt = _build_roundup_prompt("epl", BotProfileFactory(epl_team_tla=""))
        assert prompt is None


class TestBuildNflRoundup:
    @pytest.fixture(autouse=True)
    def _setup_games(self):
        """Create NFL games from last week."""
        from nfl.games.models import GameStatus
        from nfl.tests.factories import GameFactory

        start, end = _get_last_week_range()
        self.game = GameFactory(
            status=GameStatus.FINAL,
            game_date=start,
            home_score=27,
            away_score=24,
            week=5,
        )

    def test_returns_prompt_with_results(self):
        prompt = _build_roundup_prompt("nfl", BotProfileFactory(nfl_team_abbr=""))
        assert prompt is not None
        assert "Results this week" in prompt
        assert "NFL" in prompt
        assert "Week 5" in prompt

    def test_returns_none_when_no_games(self):
        from nfl.games.models import Game

        Game.objects.all().delete()
        prompt = _build_roundup_prompt("nfl", BotProfileFactory(nfl_team_abbr=""))
        assert prompt is None


# ---------------------------------------------------------------------------
# generate_weekly_roundup — end-to-end
# ---------------------------------------------------------------------------


class TestGenerateWeeklyRoundup:
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
        BotProfileFactory(nba_team_abbr="")  # neutral analyst bot

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=(
                    "TITLE: Wild Week in the NBA — Upsets Galore\n"
                    "SUBTITLE: Home teams struggled as underdogs cashed all week.\n"
                    "What a week it was in the NBA. The league delivered drama from "
                    "Monday through Sunday, with several teams defying the odds and "
                    "the spread in spectacular fashion.\n\n"
                    "The betting market had a rough go of it this week, with favorites "
                    "covering in only a handful of games. If you had the contrarian "
                    "picks, your bankroll is looking healthy.\n\n"
                    "Looking ahead, the schedule gets even tougher next week with "
                    "several divisional matchups that could shake up the standings."
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        article = generate_weekly_roundup("nba")

        assert article is not None
        assert article.title == "Wild Week in the NBA — Upsets Galore"
        assert article.league == "nba"
        assert article.article_type == NewsArticle.ArticleType.ROUNDUP
        # Roundups always start as drafts
        assert article.status == NewsArticle.Status.DRAFT
        assert article.published_at is None
        # No game reference fields (roundups cover multiple games)
        assert article.game_id_hash == ""
        assert article.game_url == ""

    def test_no_bot_returns_none(self):
        article = generate_weekly_roundup("nba")
        assert article is None

    @patch("news.article_service.anthropic.Anthropic")
    def test_api_failure_returns_none(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="")

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        article = generate_weekly_roundup("nba")
        assert article is None

    def test_no_games_returns_none(self):
        """If no games in the date range, should return None."""
        from nba.games.models import Game

        Game.objects.all().delete()
        BotProfileFactory(nba_team_abbr="")

        article = generate_weekly_roundup("nba")
        assert article is None

    @patch("news.article_service.anthropic.Anthropic")
    def test_uses_roundup_max_tokens(self, mock_anthropic_cls):
        """Roundups should use ROUNDUP_MAX_TOKENS (1200) not MAX_TOKENS (800)."""
        BotProfileFactory(nba_team_abbr="")

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=(
                    "TITLE: NBA Weekly Roundup\n"
                    "SUBTITLE: A look back at the week.\n"
                    "The NBA season rolls on with plenty of drama this week. "
                    "Multiple games went down to the wire and the betting lines "
                    "were all over the place."
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        generate_weekly_roundup("nba")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 1200
