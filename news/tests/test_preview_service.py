"""Tests for league preview article generation."""

from unittest.mock import MagicMock, patch

import pytest

from news.article_service import generate_league_preview
from news.models import NewsArticle
from vinosports.betting.models import FuturesMarketStatus

from .factories import BotProfileFactory

pytestmark = pytest.mark.django_db

MOCK_PREVIEW_RESPONSE = (
    "TITLE: The NFL Is Back — Here's Where the Smart Money Is Going\n"
    "SUBTITLE: Breaking down the futures board ahead of the new season.\n"
    "Football season is almost here, and I've been staring at the futures "
    "board for weeks trying to find edges. The oddsmakers have set their "
    "lines, and I've got some strong opinions about where the value sits.\n\n"
    "Let's start at the top. The favorites look solid on paper, but futures "
    "markets always have inefficiencies if you know where to look. I've been "
    "tracking roster moves and coaching changes, and there are some teams "
    "being slept on that could make serious noise this season.\n\n"
    "The betting public loves to pile on the usual suspects, but that creates "
    "value on the other side. I'm looking at a few sleepers that could return "
    "massive payoffs for patient bettors willing to hold a ticket all year."
)


def _create_nfl_futures():
    """Create an open NFL futures market with outcomes."""
    from nfl.betting.models import FuturesMarket, FuturesOutcome
    from nfl.tests.factories import TeamFactory

    team1 = TeamFactory(name="Kansas City Chiefs", abbreviation="KC")
    team2 = TeamFactory(name="Buffalo Bills", abbreviation="BUF")
    team3 = TeamFactory(name="Detroit Lions", abbreviation="DET")

    market = FuturesMarket.objects.create(
        name="Super Bowl Winner 2026",
        season="2026",
        market_type="SUPER_BOWL",
        status=FuturesMarketStatus.OPEN,
    )
    FuturesOutcome.objects.create(market=market, team=team1, odds=350)
    FuturesOutcome.objects.create(market=market, team=team2, odds=500)
    FuturesOutcome.objects.create(market=market, team=team3, odds=800)

    return market


def _create_epl_futures():
    """Create an open EPL futures market with outcomes."""
    from epl.betting.models import FuturesMarket, FuturesOutcome
    from epl.tests.factories import TeamFactory

    team1 = TeamFactory(name="Arsenal", tla="ARS")
    team2 = TeamFactory(name="Manchester City", tla="MCI")

    market = FuturesMarket.objects.create(
        name="Premier League Winner 2026-27",
        season="2026-27",
        market_type="WINNER",
        status=FuturesMarketStatus.OPEN,
    )
    FuturesOutcome.objects.create(market=market, team=team1, odds="2.50")
    FuturesOutcome.objects.create(market=market, team=team2, odds="1.80")

    return market


class TestGenerateLeaguePreview:
    @patch("news.article_service.anthropic.Anthropic")
    def test_successful_nfl_preview(self, mock_anthropic_cls):
        BotProfileFactory(active_in_nfl=True, nfl_team_abbr="KC")
        _create_nfl_futures()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_PREVIEW_RESPONSE)]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        article = generate_league_preview("nfl")

        assert article is not None
        assert article.league == "nfl"
        assert article.article_type == NewsArticle.ArticleType.PREVIEW
        assert article.status == NewsArticle.Status.DRAFT
        assert article.published_at is None
        assert (
            article.title == "The NFL Is Back — Here's Where the Smart Money Is Going"
        )
        assert article.author is not None
        assert article.prompt_used != ""

    @patch("news.article_service.anthropic.Anthropic")
    def test_successful_epl_preview(self, mock_anthropic_cls):
        BotProfileFactory(active_in_epl=True, epl_team_tla="ARS")
        _create_epl_futures()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_PREVIEW_RESPONSE)]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        article = generate_league_preview("epl")

        assert article is not None
        assert article.league == "epl"
        assert article.article_type == NewsArticle.ArticleType.PREVIEW

    @patch("news.article_service.anthropic.Anthropic")
    def test_uses_preview_max_tokens(self, mock_anthropic_cls):
        BotProfileFactory(active_in_nfl=True)
        _create_nfl_futures()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_PREVIEW_RESPONSE)]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        generate_league_preview("nfl")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2500

    def test_no_bot_returns_none(self):
        _create_nfl_futures()
        article = generate_league_preview("nfl")
        assert article is None

    def test_no_futures_markets_returns_none(self):
        BotProfileFactory(active_in_nfl=True)
        article = generate_league_preview("nfl")
        assert article is None

    def test_unknown_league_returns_none(self):
        article = generate_league_preview("xyz")
        assert article is None

    @patch("news.article_service.anthropic.Anthropic")
    def test_api_failure_returns_none(self, mock_anthropic_cls):
        BotProfileFactory(active_in_nfl=True)
        _create_nfl_futures()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        article = generate_league_preview("nfl")
        assert article is None

    @patch("news.article_service.anthropic.Anthropic")
    def test_prompt_includes_futures_odds(self, mock_anthropic_cls):
        BotProfileFactory(active_in_nfl=True)
        _create_nfl_futures()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_PREVIEW_RESPONSE)]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        generate_league_preview("nfl")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_prompt = call_kwargs["messages"][0]["content"]
        assert "Kansas City Chiefs" in user_prompt
        assert "Buffalo Bills" in user_prompt
        assert "+350" in user_prompt
        assert "Super Bowl" in user_prompt

    @patch("news.article_service.anthropic.Anthropic")
    def test_epl_prompt_uses_decimal_odds(self, mock_anthropic_cls):
        BotProfileFactory(active_in_epl=True)
        _create_epl_futures()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_PREVIEW_RESPONSE)]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        generate_league_preview("epl")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_prompt = call_kwargs["messages"][0]["content"]
        assert "Arsenal" in user_prompt
        assert "2.50" in user_prompt
        assert "1.80" in user_prompt
