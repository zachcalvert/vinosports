"""Tests for news article_service — parsing, filtering, bot selection, prompt building, generation."""

from unittest.mock import MagicMock, patch

import pytest

from news.article_service import (
    _build_recap_prompt,
    _filter_article,
    _format_game_summary,
    _get_game_url,
    _parse_article_response,
    _select_recap_bot,
    _spread_result,
    _trim_to_last_sentence,
    generate_game_recap,
)
from news.models import NewsArticle

from .factories import BotProfileFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


class TestParseArticleResponse:
    def test_full_structured_response(self):
        raw = (
            "TITLE: Lakers Crush Celtics in Statement Win\n"
            "SUBTITLE: LA covers the spread with a dominant second half.\n"
            "The Lakers came out firing in the third quarter...\n"
            "\n"
            "This was a game that betting markets had pegged as close..."
        )
        title, subtitle, body = _parse_article_response(raw)
        assert title == "Lakers Crush Celtics in Statement Win"
        assert subtitle == "LA covers the spread with a dominant second half."
        assert "Lakers came out firing" in body

    def test_missing_subtitle_marker(self):
        raw = (
            "TITLE: A Big Win for the Bulls\n"
            "The Bulls dominated from start to finish...\n"
            "It was a classic performance."
        )
        title, subtitle, body = _parse_article_response(raw)
        assert title == "A Big Win for the Bulls"
        assert subtitle == ""
        assert "Bulls dominated" in body

    def test_no_markers_at_all(self):
        raw = "What a game that was.\nThe home team pulled off a stunning upset."
        title, subtitle, body = _parse_article_response(raw)
        assert title == "What a game that was."
        assert "stunning upset" in body

    def test_empty_response(self):
        title, subtitle, body = _parse_article_response("")
        assert title == ""
        assert subtitle == ""
        assert body == ""


# ---------------------------------------------------------------------------
# Post-hoc filter
# ---------------------------------------------------------------------------


class TestFilterArticle:
    def test_clean_article_passes(self):
        title = "Big Game Recap"
        body = "The team won the game in convincing fashion. " * 10
        ok, reason = _filter_article(title, body)
        assert ok is True
        assert reason == ""

    def test_body_too_short(self):
        ok, reason = _filter_article("Title", "Short.")
        assert ok is False
        assert reason == "body_too_short"

    def test_body_too_long(self):
        ok, reason = _filter_article("Title", "x" * 3001)
        assert ok is False
        assert reason == "body_too_long"

    def test_title_too_short(self):
        ok, reason = _filter_article("Hi", "The game was great. " * 20)
        assert ok is False
        assert reason == "title_too_short"

    def test_title_too_long(self):
        ok, reason = _filter_article("x" * 201, "The game was great. " * 20)
        assert ok is False
        assert reason == "title_too_long"

    def test_profanity_rejected(self):
        ok, reason = _filter_article("Clean Title", "The game was fucking great. " * 10)
        assert ok is False
        assert "profanity" in reason

    def test_irrelevant_rejected(self):
        ok, reason = _filter_article("Nice Title", "Lorem ipsum dolor sit amet. " * 10)
        assert ok is False
        assert reason == "irrelevant"


# ---------------------------------------------------------------------------
# Bot selection
# ---------------------------------------------------------------------------


class TestSelectRecapBot:
    def test_picks_winner_team_bot(self):
        profile = BotProfileFactory(nba_team_abbr="LAL")
        game = MagicMock()
        game.home_score = 112
        game.away_score = 98
        game.home_team = MagicMock(abbreviation="LAL")
        game.away_team = MagicMock(abbreviation="BOS")

        user = _select_recap_bot("nba", game)
        assert user == profile.user

    def test_falls_back_to_loser_team_bot(self):
        profile = BotProfileFactory(nba_team_abbr="BOS")
        game = MagicMock()
        game.home_score = 112
        game.away_score = 98
        game.home_team = MagicMock(abbreviation="LAL")
        game.away_team = MagicMock(abbreviation="BOS")

        user = _select_recap_bot("nba", game)
        assert user == profile.user

    def test_falls_back_to_any_active_bot(self):
        profile = BotProfileFactory(nba_team_abbr="GSW")
        game = MagicMock()
        game.home_score = 100
        game.away_score = 95
        game.home_team = MagicMock(abbreviation="LAL")
        game.away_team = MagicMock(abbreviation="BOS")

        user = _select_recap_bot("nba", game)
        assert user == profile.user

    def test_returns_none_when_no_bots(self):
        game = MagicMock()
        game.home_score = 100
        game.away_score = 95
        game.home_team = MagicMock(abbreviation="LAL")
        game.away_team = MagicMock(abbreviation="BOS")

        user = _select_recap_bot("nba", game)
        assert user is None

    def test_epl_uses_tla(self):
        profile = BotProfileFactory(epl_team_tla="ARS")
        match = MagicMock()
        match.home_score = 2
        match.away_score = 1
        match.home_team = MagicMock(tla="ARS")
        match.away_team = MagicMock(tla="CHE")

        user = _select_recap_bot("epl", match)
        assert user == profile.user

    def test_draw_skips_winner_loser(self):
        """On a draw, should fall back to any active bot."""
        profile = BotProfileFactory(epl_team_tla="LIV")
        match = MagicMock()
        match.home_score = 1
        match.away_score = 1
        match.home_team = MagicMock(tla="ARS")
        match.away_team = MagicMock(tla="CHE")

        user = _select_recap_bot("epl", match)
        assert user == profile.user


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


class TestBuildRecapPrompt:
    @pytest.fixture(autouse=True)
    def _patch_nba_models(self):
        """Patch ORM manager methods to avoid DB hits on mock game objects."""
        from nba.games.models import GameNotes, Odds

        with (
            patch.object(Odds.objects, "filter") as mock_filter,
            patch.object(GameNotes.objects, "get", side_effect=GameNotes.DoesNotExist),
        ):
            mock_filter.return_value.order_by.return_value.first.return_value = None
            yield

    def _make_nba_game(self):
        game = MagicMock()
        game.pk = 999
        game.home_team = MagicMock(
            name="Los Angeles Lakers",
            abbreviation="LAL",
        )
        game.away_team = MagicMock(
            name="Boston Celtics",
            abbreviation="BOS",
        )
        game.home_score = 112
        game.away_score = 105
        game.game_date = MagicMock()
        game.game_date.strftime = MagicMock(return_value="Tuesday, March 15, 2026")
        game.arena = "Crypto.com Arena"
        game.postseason = False
        # Bets — return empty queryset behavior
        game.bets = MagicMock()
        game.bets.count = MagicMock(return_value=0)
        return game

    def test_nba_prompt_includes_score(self):
        profile = BotProfileFactory(nba_team_abbr="LAL")
        game = self._make_nba_game()
        prompt = _build_recap_prompt("nba", game, profile)
        assert "112" in prompt
        assert "105" in prompt
        assert "Lakers" in prompt
        assert "Celtics" in prompt

    def test_nba_prompt_includes_arena(self):
        profile = BotProfileFactory(nba_team_abbr="LAL")
        game = self._make_nba_game()
        prompt = _build_recap_prompt("nba", game, profile)
        assert "Crypto.com Arena" in prompt

    def test_nba_prompt_includes_team_affiliation(self):
        profile = BotProfileFactory(nba_team_abbr="LAL")
        game = self._make_nba_game()
        prompt = _build_recap_prompt("nba", game, profile)
        assert "Your team" in prompt
        assert "LAL" in prompt

    def test_nba_prompt_includes_format_instructions(self):
        profile = BotProfileFactory(nba_team_abbr="LAL")
        game = self._make_nba_game()
        prompt = _build_recap_prompt("nba", game, profile)
        assert "TITLE:" in prompt
        assert "SUBTITLE:" in prompt
        assert "3-5 paragraph" in prompt


# ---------------------------------------------------------------------------
# End-to-end generation
# ---------------------------------------------------------------------------


class TestGenerateGameRecap:
    @pytest.fixture(autouse=True)
    def _patch_nba_models(self):
        """Patch ORM manager methods to avoid DB hits on mock game objects."""
        from nba.games.models import GameNotes, Odds

        with (
            patch.object(Odds.objects, "filter") as mock_filter,
            patch.object(GameNotes.objects, "get", side_effect=GameNotes.DoesNotExist),
        ):
            mock_filter.return_value.order_by.return_value.first.return_value = None
            yield

    def _make_mock_game(self):
        game = MagicMock()
        game.pk = 999
        game.id_hash = "abc12345"
        game.home_team = MagicMock(
            name="Los Angeles Lakers",
            abbreviation="LAL",
        )
        game.away_team = MagicMock(
            name="Boston Celtics",
            abbreviation="BOS",
        )
        game.home_score = 112
        game.away_score = 105
        game.game_date = MagicMock()
        game.game_date.strftime = MagicMock(return_value="Tuesday, March 15, 2026")
        game.arena = "Crypto.com Arena"
        game.postseason = False
        game.slug = "lal-bos-2026-03-15"
        game.bets = MagicMock()
        game.bets.count = MagicMock(return_value=0)
        return game

    @patch("news.article_service.anthropic.Anthropic")
    def test_successful_generation(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="LAL")
        game = self._make_mock_game()

        # Mock Claude API response
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=(
                    "TITLE: Lakers Dominate Celtics in Scoring Fest\n"
                    "SUBTITLE: LA covers easily with a 112-105 win at home.\n"
                    "The Lakers came out with serious energy in this game, "
                    "dominating the paint and controlling the tempo throughout. "
                    "From the opening tip, it was clear this was going to be LA's night.\n\n"
                    "The spread was generous to Celtics backers, but the Lakers had "
                    "other plans. A dominant third quarter sealed the deal and the bet "
                    "for anyone who had LA at home."
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        article = generate_game_recap("nba", game)

        assert article is not None
        assert article.title == "Lakers Dominate Celtics in Scoring Fest"
        assert article.subtitle == "LA covers easily with a 112-105 win at home."
        assert article.status == NewsArticle.Status.PUBLISHED
        assert article.published_at is not None
        assert article.league == "nba"
        assert article.article_type == NewsArticle.ArticleType.RECAP
        assert article.game_id_hash == "abc12345"

    @patch("news.article_service.anthropic.Anthropic")
    def test_api_failure_returns_none(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="LAL")
        game = self._make_mock_game()

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API timeout")

        article = generate_game_recap("nba", game)
        assert article is None

    def test_no_bots_returns_none(self):
        game = self._make_mock_game()
        article = generate_game_recap("nba", game)
        assert article is None

    @patch("news.article_service.anthropic.Anthropic")
    def test_duplicate_constraint_returns_none(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="LAL")
        game = self._make_mock_game()

        # Mock Claude API response
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=(
                    "TITLE: Great Game Recap\n"
                    "SUBTITLE: A subtitle.\n"
                    "The game was excellent with lots of scoring and drama. "
                    "Both teams played hard and the result was fair."
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        # Create an existing recap for this game
        from .factories import NewsArticleFactory

        NewsArticleFactory(
            league="nba",
            article_type=NewsArticle.ArticleType.RECAP,
            game_id_hash="abc12345",
        )

        article = generate_game_recap("nba", game)
        assert article is None

    @patch("news.article_service.anthropic.Anthropic")
    def test_filtered_article_saved_as_draft(self, mock_anthropic_cls):
        BotProfileFactory(nba_team_abbr="LAL")
        game = self._make_mock_game()

        # Mock Claude API with response that will fail filter (too short body)
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=("TITLE: Short Article\nSUBTITLE: Very brief.\nToo short."))
        ]
        mock_client.messages.create.return_value = mock_response

        article = generate_game_recap("nba", game)
        assert article is not None
        assert article.status == NewsArticle.Status.DRAFT
        assert article.published_at is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_format_game_summary_nba(self):
        game = MagicMock()
        game.home_team = MagicMock(abbreviation="LAL")
        game.away_team = MagicMock(abbreviation="BOS")
        game.home_score = 112
        game.away_score = 105
        assert _format_game_summary("nba", game) == "BOS 105 - LAL 112"

    def test_format_game_summary_epl(self):
        match = MagicMock()
        match.home_team = MagicMock(short_name="Arsenal", name="Arsenal FC")
        match.away_team = MagicMock(short_name="Chelsea", name="Chelsea FC")
        match.home_score = 2
        match.away_score = 1
        assert _format_game_summary("epl", match) == "Chelsea 1 - Arsenal 2"

    def test_get_game_url_nba(self):
        game = MagicMock()
        game.id_hash = "abc12345"
        url = _get_game_url("nba", game)
        assert "/nba/games/abc12345/" in url

    def test_get_game_url_epl(self):
        match = MagicMock()
        match.slug = "ars-che-2026-03-15"
        url = _get_game_url("epl", match)
        assert "/epl/match/ars-che-2026-03-15/" in url


# ---------------------------------------------------------------------------
# Trim to last sentence
# ---------------------------------------------------------------------------


class TestTrimToLastSentence:
    def test_trims_at_period(self):
        assert _trim_to_last_sentence("Hello world. This is cut") == "Hello world."

    def test_trims_at_exclamation(self):
        assert _trim_to_last_sentence("What a game! The team") == "What a game!"

    def test_trims_at_question(self):
        assert _trim_to_last_sentence("Can they win? The odds") == "Can they win?"

    def test_returns_as_is_if_no_punctuation(self):
        assert _trim_to_last_sentence("no ending here") == "no ending here"

    def test_already_ends_with_punctuation(self):
        assert _trim_to_last_sentence("Complete sentence.") == "Complete sentence."


# ---------------------------------------------------------------------------
# Spread result helper
# ---------------------------------------------------------------------------


class TestSpreadResult:
    def test_home_favorite_covers(self):
        # Home -7, wins by 10 → margin=10, ats=10+(-7)=3 → home covered
        home_covered, text = _spread_result(27, 17, -7, "KC", "BUF")
        assert home_covered is True
        assert "KC covered" in text

    def test_home_favorite_does_not_cover(self):
        # Home -7, wins by 3 → margin=3, ats=3+(-7)=-4 → away covered
        home_covered, text = _spread_result(20, 17, -7, "KC", "BUF")
        assert home_covered is False
        assert "BUF covered" in text

    def test_home_underdog_covers(self):
        # Home +3.5, loses by 2 → margin=-2, ats=-2+3.5=1.5 → home covered
        home_covered, text = _spread_result(17, 19, 3.5, "BUF", "KC")
        assert home_covered is True
        assert "BUF covered" in text

    def test_home_underdog_does_not_cover(self):
        # Home +3.5, loses by 7 → margin=-7, ats=-7+3.5=-3.5 → away covered
        home_covered, text = _spread_result(14, 21, 3.5, "BUF", "KC")
        assert home_covered is False
        assert "KC covered" in text

    def test_push(self):
        # Home -7, wins by exactly 7 → margin=7, ats=7+(-7)=0 → push
        home_covered, text = _spread_result(24, 17, -7, "KC", "BUF")
        assert home_covered is None
        assert text == "PUSH"
