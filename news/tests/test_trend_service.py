"""Tests for betting trend generation in article_service."""

from unittest.mock import MagicMock, patch

import pytest

from news.article_service import (
    _build_betting_stats_section,
    _build_top_bettors_section,
    _build_trend_prompt,
    generate_betting_trend,
)
from news.models import NewsArticle

from .factories import BotProfileFactory, BotUserFactory, UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# _build_betting_stats_section
# ---------------------------------------------------------------------------


class TestBuildBettingStatsSection:
    def test_empty_queryset_returns_empty(self):
        from nba.betting.models import BetSlip

        lines = _build_betting_stats_section(BetSlip.objects.none(), has_market=True)
        assert lines == []

    def test_includes_total_and_settled(self):
        from nba.betting.models import BetSlip
        from nba.tests.factories import BetSlipFactory

        BetSlipFactory(status="WON")
        BetSlipFactory(status="LOST")
        BetSlipFactory(status="PENDING")

        lines = _build_betting_stats_section(BetSlip.objects.all(), has_market=True)
        text = "\n".join(lines)
        assert "Total bets placed" in text
        assert "3" in text  # total
        assert "2" in text  # settled
        assert "1 won" in text
        assert "1 lost" in text

    def test_includes_market_breakdown_when_has_market(self):
        from nba.betting.models import BetSlip
        from nba.tests.factories import BetSlipFactory

        BetSlipFactory(market="SPREAD", status="WON")
        BetSlipFactory(market="SPREAD", status="LOST")
        BetSlipFactory(market="MONEYLINE", status="WON")

        lines = _build_betting_stats_section(BetSlip.objects.all(), has_market=True)
        text = "\n".join(lines)
        assert "Win rate by market" in text
        assert "SPREAD" in text
        assert "MONEYLINE" in text

    def test_excludes_market_breakdown_when_no_market(self):
        from epl.betting.models import BetSlip
        from epl.tests.factories import BetSlipFactory

        BetSlipFactory(status="WON")
        BetSlipFactory(status="LOST")

        lines = _build_betting_stats_section(BetSlip.objects.all(), has_market=False)
        text = "\n".join(lines)
        assert "Win rate by market" not in text

    def test_includes_popular_selections(self):
        from nba.betting.models import BetSlip
        from nba.tests.factories import BetSlipFactory

        BetSlipFactory(selection="HOME", status="WON")
        BetSlipFactory(selection="HOME", status="LOST")
        BetSlipFactory(selection="AWAY", status="WON")

        lines = _build_betting_stats_section(BetSlip.objects.all(), has_market=True)
        text = "\n".join(lines)
        assert "Most popular selections" in text
        assert "HOME" in text


# ---------------------------------------------------------------------------
# _build_top_bettors_section
# ---------------------------------------------------------------------------


class TestBuildTopBettorsSection:
    def test_empty_when_no_stats(self):
        lines = _build_top_bettors_section()
        assert lines == []

    def test_includes_top_performers(self):
        from vinosports.betting.models import UserStats

        user = UserFactory()
        UserStats.objects.create(
            user=user,
            total_bets=20,
            total_wins=15,
            total_losses=5,
            net_profit=500,
        )

        lines = _build_top_bettors_section()
        text = "\n".join(lines)
        assert "Top performers" in text
        assert "+500" in text

    def test_includes_hot_streaks(self):
        from vinosports.betting.models import UserStats

        user = UserFactory()
        UserStats.objects.create(
            user=user,
            total_bets=10,
            total_wins=7,
            total_losses=3,
            current_streak=5,
        )

        lines = _build_top_bettors_section()
        text = "\n".join(lines)
        assert "Hot streaks" in text
        assert "5W streak" in text

    def test_includes_cold_streaks(self):
        from vinosports.betting.models import UserStats

        user = UserFactory()
        UserStats.objects.create(
            user=user,
            total_bets=10,
            total_wins=3,
            total_losses=7,
            current_streak=-4,
        )

        lines = _build_top_bettors_section()
        text = "\n".join(lines)
        assert "Cold streaks" in text
        assert "4L streak" in text

    def test_excludes_bots(self):
        from vinosports.betting.models import UserStats

        bot_user = BotUserFactory()
        UserStats.objects.create(
            user=bot_user,
            total_bets=20,
            total_wins=18,
            total_losses=2,
            net_profit=9999,
        )

        lines = _build_top_bettors_section()
        # Bot should not appear in top performers
        assert lines == []


# ---------------------------------------------------------------------------
# _build_trend_prompt
# ---------------------------------------------------------------------------


class TestBuildTrendPrompt:
    def test_nba_returns_prompt_with_bets(self):
        from nba.tests.factories import BetSlipFactory

        BetSlipFactory(status="WON")
        BetSlipFactory(status="LOST")

        prompt = _build_trend_prompt("nba")
        assert prompt is not None
        assert "NBA" in prompt
        assert "betting trend" in prompt.lower() or "Betting data" in prompt

    def test_nba_returns_none_when_no_bets(self):
        prompt = _build_trend_prompt("nba")
        assert prompt is None

    def test_epl_returns_prompt_with_bets(self):
        from epl.tests.factories import BetSlipFactory

        BetSlipFactory(status="WON")

        prompt = _build_trend_prompt("epl")
        assert prompt is not None
        assert "Premier League" in prompt

    def test_epl_includes_selection_breakdown(self):
        from epl.tests.factories import BetSlipFactory

        BetSlipFactory(selection="HOME_WIN", status="WON")
        BetSlipFactory(selection="DRAW", status="LOST")

        prompt = _build_trend_prompt("epl")
        assert "Win rate by selection" in prompt

    def test_nfl_returns_prompt_with_bets(self):
        from nfl.tests.factories import BetSlipFactory

        BetSlipFactory(status="WON")

        prompt = _build_trend_prompt("nfl")
        assert prompt is not None
        assert "NFL" in prompt

    def test_includes_format_instructions(self):
        from nba.tests.factories import BetSlipFactory

        BetSlipFactory(status="WON")

        prompt = _build_trend_prompt("nba")
        assert "TITLE:" in prompt
        assert "SUBTITLE:" in prompt
        assert "3-5 paragraphs" in prompt


# ---------------------------------------------------------------------------
# generate_betting_trend — end-to-end
# ---------------------------------------------------------------------------


class TestGenerateBettingTrend:
    @pytest.fixture(autouse=True)
    def _setup_bets(self):
        from nba.tests.factories import BetSlipFactory

        BetSlipFactory(status="WON")
        BetSlipFactory(status="LOST")

    @patch("news.article_service.anthropic.Anthropic")
    def test_successful_generation(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="")  # neutral analyst bot

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=(
                    "TITLE: Spread Bettors Are Cashing In This Week\n"
                    "SUBTITLE: The community is riding a hot streak on the spread market.\n"
                    "The numbers don't lie — spread bettors are having a field day this "
                    "week. With a 65% hit rate across the board, the smart money has "
                    "been on the points, not the moneyline.\n\n"
                    "The total market tells a different story though. Overs have been "
                    "cold, hitting at just 40% over the last two weeks. If you've been "
                    "hammering overs, it's time to reconsider your strategy.\n\n"
                    "Looking at the leaderboard, the usual suspects are near the top, "
                    "but a few new names are making noise with impressive streaks."
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        article = generate_betting_trend("nba")

        assert article is not None
        assert article.title == "Spread Bettors Are Cashing In This Week"
        assert article.league == "nba"
        assert article.article_type == NewsArticle.ArticleType.TREND
        assert article.status == NewsArticle.Status.DRAFT
        assert article.published_at is None

    def test_no_bot_returns_none(self):
        article = generate_betting_trend("nba")
        assert article is None

    @patch("news.article_service.anthropic.Anthropic")
    def test_api_failure_returns_none(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="")

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        article = generate_betting_trend("nba")
        assert article is None

    def test_no_bets_returns_none(self):
        from nba.betting.models import BetSlip

        BetSlip.objects.all().delete()
        BotProfileFactory(nba_team_abbr="")

        article = generate_betting_trend("nba")
        assert article is None
