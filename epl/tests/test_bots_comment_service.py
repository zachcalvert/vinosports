"""Tests for epl.bots.comment_service — LLM comment generation, filtering, and bot selection."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from epl.bots.comment_service import (
    MAX_REPLIES_PER_MATCH,
    _build_user_prompt,
    _filter_comment,
    _homer_team_mentioned,
    _is_bot_relevant,
    generate_bot_comment,
    select_bots_for_match,
    select_reply_bot,
)
from epl.bots.models import BotComment
from epl.tests.factories import (
    BetSlipFactory,
    BotCommentFactory,
    BotProfileFactory,
    BotUserFactory,
    CommentFactory,
    MatchFactory,
    OddsFactory,
    TeamFactory,
    UserBalanceFactory,
    UserFactory,
    UserStatsFactory,
)
from vinosports.bots.models import StrategyType

# ---------------------------------------------------------------------------
# _filter_comment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFilterComment:
    def test_too_short(self):
        match = MatchFactory()
        ok, reason = _filter_comment("Hi", match)
        assert not ok
        assert reason == "too_short"

    def test_too_long(self):
        match = MatchFactory()
        ok, reason = _filter_comment("x" * 501, match)
        assert not ok
        assert reason == "too_long"

    def test_profanity_rejected(self):
        match = MatchFactory()
        ok, reason = _filter_comment(
            "What the fuck is this match prediction about goals", match
        )
        assert not ok
        assert reason == "profanity:fuck"

    def test_profanity_word_boundary(self):
        """Profanity check uses word boundaries — 'Scunthorpe' should not trigger."""
        match = MatchFactory()
        # Contains no profanity at word boundaries, but has a football keyword
        ok, reason = _filter_comment(
            "Arsenal played a great match today at the Emirates", match
        )
        assert ok

    def test_irrelevant_rejected(self):
        match = MatchFactory()
        ok, reason = _filter_comment(
            "I really love cooking pasta with tomato sauce everyday", match
        )
        assert not ok
        assert reason == "irrelevant"

    def test_relevant_with_team_name(self):
        home = TeamFactory(name="Arsenal", short_name="Arsenal", tla="ARS")
        away = TeamFactory(name="Chelsea", short_name="Chelsea", tla="CHE")
        match = MatchFactory(home_team=home, away_team=away)
        ok, reason = _filter_comment("Arsenal are going to dominate this one", match)
        assert ok
        assert reason == ""

    def test_relevant_with_football_keyword(self):
        match = MatchFactory()
        ok, reason = _filter_comment(
            "The odds are definitely stacked against them in this one", match
        )
        assert ok
        assert reason == ""

    def test_relevant_with_team_tla(self):
        home = TeamFactory(name="Manchester United", short_name="Man Utd", tla="MUN")
        match = MatchFactory(home_team=home)
        ok, reason = _filter_comment(
            "MUN are not looking great this season in the league", match
        )
        assert ok

    def test_exactly_10_chars_passes_length_check(self):
        match = MatchFactory()
        # 10 chars with a football keyword
        ok, reason = _filter_comment("Great goal", match)
        assert ok

    def test_exactly_500_chars_passes_length_check(self):
        match = MatchFactory()
        text = "What a match " + "x" * (500 - len("What a match "))
        assert len(text) == 500
        ok, reason = _filter_comment(text, match)
        assert ok


# ---------------------------------------------------------------------------
# _homer_team_mentioned
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHomerTeamMentioned:
    def setup_method(self):
        # Clear the module-level cache before each test
        from epl.bots.comment_service import _homer_team_cache

        _homer_team_cache.clear()

    def test_no_tla_returns_false(self):
        profile = BotProfileFactory(epl_team_tla="")
        assert not _homer_team_mentioned(profile, "Arsenal are great")

    def test_team_name_mentioned(self):
        TeamFactory(name="Arsenal", short_name="Arsenal", tla="ARS")
        profile = BotProfileFactory(epl_team_tla="ARS")
        assert _homer_team_mentioned(profile, "Arsenal are looking strong")

    def test_team_short_name_mentioned(self):
        TeamFactory(name="Manchester United FC", short_name="Man Utd", tla="MUN")
        profile = BotProfileFactory(epl_team_tla="MUN")
        assert _homer_team_mentioned(profile, "Man Utd is on fire")

    def test_team_tla_mentioned_word_boundary(self):
        TeamFactory(name="Arsenal", short_name="Arsenal", tla="ARS")
        profile = BotProfileFactory(epl_team_tla="ARS")
        assert _homer_team_mentioned(profile, "ARS are brilliant")

    def test_tla_false_positive_avoided(self):
        """TLA 'ARS' inside 'stars' should NOT match due to word boundary."""
        TeamFactory(name="Arsenal", short_name="Arsenal", tla="ARS")
        profile = BotProfileFactory(epl_team_tla="ARS")
        assert not _homer_team_mentioned(profile, "These stars are incredible")

    def test_unknown_tla_returns_false(self):
        profile = BotProfileFactory(epl_team_tla="ZZZ")
        assert not _homer_team_mentioned(profile, "ZZZ is great")

    def test_case_insensitive(self):
        TeamFactory(name="Arsenal", short_name="Arsenal", tla="ARS")
        profile = BotProfileFactory(epl_team_tla="ARS")
        assert _homer_team_mentioned(profile, "arsenal are the best")


# ---------------------------------------------------------------------------
# _is_bot_relevant
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIsBotRelevant:
    def test_frontrunner_relevant_when_clear_favorite(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.FRONTRUNNER)
        odds = {
            "home_win": Decimal("1.50"),
            "draw": Decimal("3.50"),
            "away_win": Decimal("5.00"),
        }
        assert _is_bot_relevant(profile, match, odds)

    def test_frontrunner_irrelevant_when_no_favorite(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.FRONTRUNNER)
        odds = {
            "home_win": Decimal("2.00"),
            "draw": Decimal("3.00"),
            "away_win": Decimal("3.50"),
        }
        assert not _is_bot_relevant(profile, match, odds)

    def test_underdog_relevant_when_big_underdog(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.UNDERDOG)
        odds = {
            "home_win": Decimal("1.50"),
            "draw": Decimal("3.50"),
            "away_win": Decimal("5.00"),
        }
        assert _is_bot_relevant(profile, match, odds)

    def test_underdog_irrelevant_when_no_underdog(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.UNDERDOG)
        odds = {
            "home_win": Decimal("1.80"),
            "draw": Decimal("2.50"),
            "away_win": Decimal("2.90"),
        }
        assert not _is_bot_relevant(profile, match, odds)

    def test_draw_specialist_relevant_in_sweet_spot(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.DRAW_SPECIALIST)
        odds = {
            "home_win": Decimal("2.00"),
            "draw": Decimal("3.20"),
            "away_win": Decimal("3.50"),
        }
        assert _is_bot_relevant(profile, match, odds)

    def test_draw_specialist_irrelevant_outside_range(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.DRAW_SPECIALIST)
        odds = {
            "home_win": Decimal("2.00"),
            "draw": Decimal("4.00"),
            "away_win": Decimal("3.50"),
        }
        assert not _is_bot_relevant(profile, match, odds)

    def test_value_hunter_relevant_when_multiple_bookmakers(self):
        match = MatchFactory()
        OddsFactory(match=match, bookmaker="BookA")
        OddsFactory(match=match, bookmaker="BookB")
        profile = BotProfileFactory(strategy_type=StrategyType.VALUE_HUNTER)
        odds = {
            "home_win": Decimal("2.00"),
            "draw": Decimal("3.00"),
            "away_win": Decimal("3.50"),
        }
        assert _is_bot_relevant(profile, match, odds)

    def test_value_hunter_irrelevant_single_bookmaker(self):
        match = MatchFactory()
        OddsFactory(match=match, bookmaker="Only")
        profile = BotProfileFactory(strategy_type=StrategyType.VALUE_HUNTER)
        odds = {
            "home_win": Decimal("2.00"),
            "draw": Decimal("3.00"),
            "away_win": Decimal("3.50"),
        }
        assert not _is_bot_relevant(profile, match, odds)

    def test_parlay_always_relevant(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.PARLAY)
        assert _is_bot_relevant(profile, match, {})

    def test_chaos_always_relevant(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT)
        assert _is_bot_relevant(profile, match, {})

    def test_all_in_alice_always_relevant(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.ALL_IN_ALICE)
        assert _is_bot_relevant(profile, match, {})

    def test_homer_relevant_when_team_plays(self):
        team = TeamFactory(tla="ARS")
        match = MatchFactory(home_team=team)
        profile = BotProfileFactory(
            strategy_type=StrategyType.HOMER, epl_team_tla="ARS"
        )
        assert _is_bot_relevant(profile, match, {})

    def test_homer_irrelevant_when_team_not_playing(self):
        match = MatchFactory()
        profile = BotProfileFactory(
            strategy_type=StrategyType.HOMER, epl_team_tla="ARS"
        )
        assert not _is_bot_relevant(profile, match, {})

    def test_homer_no_tla_returns_false(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.HOMER, epl_team_tla="")
        assert not _is_bot_relevant(profile, match, {})

    def test_missing_odds_returns_false_for_frontrunner(self):
        match = MatchFactory()
        profile = BotProfileFactory(strategy_type=StrategyType.FRONTRUNNER)
        assert not _is_bot_relevant(profile, match, {})


# ---------------------------------------------------------------------------
# select_bots_for_match
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSelectBotsForMatch:
    def test_returns_up_to_max_bots(self):
        match = MatchFactory()
        OddsFactory(match=match)
        # Create 5 bots with always-relevant strategies
        for _ in range(5):
            BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT)

        bots = select_bots_for_match(
            match, BotComment.TriggerType.PRE_MATCH, max_bots=2
        )
        assert len(bots) <= 2

    def test_excludes_already_commented_bots(self):
        match = MatchFactory()
        OddsFactory(match=match)
        profile = BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT)
        BotCommentFactory(
            user=profile.user,
            match=match,
            trigger_type=BotComment.TriggerType.PRE_MATCH,
        )

        bots = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)
        assert profile.user not in bots

    def test_excludes_specified_user_ids(self):
        match = MatchFactory()
        OddsFactory(match=match)
        profile = BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT)

        bots = select_bots_for_match(
            match,
            BotComment.TriggerType.PRE_MATCH,
            exclude_user_ids={profile.user.pk},
        )
        assert profile.user not in bots

    def test_returns_empty_when_no_candidates(self):
        match = MatchFactory()
        bots = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)
        assert bots == []

    def test_skips_inactive_bots(self):
        match = MatchFactory()
        OddsFactory(match=match)
        BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT, is_active=False)

        bots = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)
        assert bots == []

    def test_skips_bots_not_active_in_epl(self):
        match = MatchFactory()
        OddsFactory(match=match)
        BotProfileFactory(
            strategy_type=StrategyType.CHAOS_AGENT,
            active_in_epl=False,
        )

        bots = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)
        assert bots == []


# ---------------------------------------------------------------------------
# select_reply_bot
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSelectReplyBot:
    def test_returns_none_when_reply_cap_reached(self):
        match = MatchFactory()
        for _ in range(MAX_REPLIES_PER_MATCH):
            BotCommentFactory(
                match=match,
                trigger_type=BotComment.TriggerType.REPLY,
            )

        comment = CommentFactory(match=match)
        result = select_reply_bot(match, comment)
        assert result is None

    def test_bot_to_bot_affinity_match(self):
        """A bot whose email is in another bot's affinity list should be a reply candidate."""
        match = MatchFactory()
        OddsFactory(match=match)

        # Create frontrunner bot (has underdog in affinities)
        frontrunner_user = BotUserFactory(email="frontrunner@bots.eplbets.local")
        BotProfileFactory(
            user=frontrunner_user,
            strategy_type=StrategyType.FRONTRUNNER,
        )

        # Create underdog bot who posts the comment
        underdog_user = BotUserFactory(email="underdog@bots.eplbets.local")
        BotProfileFactory(
            user=underdog_user,
            strategy_type=StrategyType.UNDERDOG,
        )
        underdog_user.is_bot = True
        underdog_user.save()

        comment = CommentFactory(user=underdog_user, match=match)

        # Try multiple times to account for randomness
        found = False
        for _ in range(20):
            bot = select_reply_bot(match, comment)
            if bot and bot.pk == frontrunner_user.pk:
                found = True
                break
        assert found, "Frontrunner should reply to underdog via affinity"

    @patch("vinosports.bots.comment_pipeline.random.random", return_value=0.8)
    def test_human_comment_gate_rejects(self, mock_random):
        """Configurable gate for human comments — random >= probability means no reply."""
        match = MatchFactory()
        OddsFactory(match=match)
        BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT)
        human_user = UserFactory()
        comment = CommentFactory(user=human_user, match=match)

        result = select_reply_bot(match, comment)
        assert result is None

    @patch("vinosports.bots.comment_pipeline.random.random", return_value=0.5)
    def test_human_comment_gate_passes(self, mock_random):
        """Configurable gate for human comments — random < probability means try to reply."""
        match = MatchFactory()
        OddsFactory(match=match)
        BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT)
        human_user = UserFactory()
        comment = CommentFactory(user=human_user, match=match)

        result = select_reply_bot(match, comment)
        assert result is not None

    def test_bot_does_not_reply_to_itself(self):
        match = MatchFactory()
        OddsFactory(match=match)
        profile = BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT)
        comment = CommentFactory(user=profile.user, match=match)

        # Even with self in affinity, should not self-reply
        for _ in range(20):
            bot = select_reply_bot(match, comment)
            if bot:
                assert bot.pk != profile.user.pk


# ---------------------------------------------------------------------------
# generate_bot_comment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGenerateBotComment:
    def _make_bot_with_match(self):
        match = MatchFactory()
        OddsFactory(match=match)
        profile = BotProfileFactory(strategy_type=StrategyType.FRONTRUNNER)
        return profile.user, match

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_successful_comment_creation(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        bot_user, match = self._make_bot_with_match()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="Arsenal looking strong for the win today!")
        ]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        comment = generate_bot_comment(
            bot_user, match, BotComment.TriggerType.PRE_MATCH
        )
        assert comment is not None
        assert comment.body == "Arsenal looking strong for the win today!"
        assert comment.user == bot_user
        assert comment.match == match

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_dedup_prevents_second_comment(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        bot_user, match = self._make_bot_with_match()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Great odds on this match today")]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        # First call succeeds
        c1 = generate_bot_comment(bot_user, match, BotComment.TriggerType.PRE_MATCH)
        assert c1 is not None

        # Second call with same trigger should be deduped
        c2 = generate_bot_comment(bot_user, match, BotComment.TriggerType.PRE_MATCH)
        assert c2 is None

    def test_no_persona_prompt_returns_none(self):
        match = MatchFactory()
        profile = BotProfileFactory(persona_prompt="")
        result = generate_bot_comment(
            profile.user, match, BotComment.TriggerType.PRE_MATCH
        )
        assert result is None

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_filtered_comment_returns_none(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        bot_user, match = self._make_bot_with_match()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Too short")]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        result = generate_bot_comment(bot_user, match, BotComment.TriggerType.PRE_MATCH)
        assert result is None
        # BotComment should be marked as filtered
        bc = BotComment.objects.get(user=bot_user, match=match)
        assert bc.filtered is True

    def test_no_api_key_returns_none(self):
        bot_user, match = self._make_bot_with_match()
        with patch("vinosports.bots.comment_pipeline.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY = ""
            result = generate_bot_comment(
                bot_user, match, BotComment.TriggerType.PRE_MATCH
            )
        assert result is None
        bc = BotComment.objects.get(user=bot_user, match=match)
        assert "ANTHROPIC_API_KEY" in bc.error

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_api_exception_returns_none(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        bot_user, match = self._make_bot_with_match()
        MockAnthropic.return_value.messages.create.side_effect = Exception("API down")

        result = generate_bot_comment(bot_user, match, BotComment.TriggerType.PRE_MATCH)
        assert result is None
        bc = BotComment.objects.get(user=bot_user, match=match)
        assert bc.error == "API call failed"

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_reply_cap_enforced_at_creation_time(self, MockAnthropic):
        match = MatchFactory()
        OddsFactory(match=match)
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Great match with some nice goals")]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        # Fill up the reply cap
        for _ in range(MAX_REPLIES_PER_MATCH):
            BotCommentFactory(match=match, trigger_type=BotComment.TriggerType.REPLY)

        profile = BotProfileFactory()
        parent = CommentFactory(match=match)
        result = generate_bot_comment(
            profile.user, match, BotComment.TriggerType.REPLY, parent_comment=parent
        )
        assert result is None

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_max_tokens_trims_to_sentence(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        bot_user, match = self._make_bot_with_match()
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text="First sentence about the match. Second sentence about the goals that gets cut"
            )
        ]
        mock_response.stop_reason = "max_tokens"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        comment = generate_bot_comment(
            bot_user, match, BotComment.TriggerType.PRE_MATCH
        )
        assert comment is not None
        assert comment.body.endswith(".")

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_reply_to_depth1_nests_directly(self, MockAnthropic, settings):
        """Replies to depth-1 comments nest directly under them (depth 2)."""
        settings.ANTHROPIC_API_KEY = "test-key"
        match = MatchFactory()
        OddsFactory(match=match)
        profile = BotProfileFactory()

        top_comment = CommentFactory(match=match)
        child_comment = CommentFactory(match=match, parent=top_comment)

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="Nice take on the match, totally agree")
        ]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        comment = generate_bot_comment(
            profile.user,
            match,
            BotComment.TriggerType.REPLY,
            parent_comment=child_comment,
        )
        assert comment is not None
        assert comment.parent == child_comment

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_reply_to_depth2_normalizes_to_parent(self, MockAnthropic, settings):
        """Replies to depth-2 comments get normalized up to the depth-1 parent."""
        settings.ANTHROPIC_API_KEY = "test-key"
        match = MatchFactory()
        OddsFactory(match=match)
        profile = BotProfileFactory()

        top_comment = CommentFactory(match=match)
        child_comment = CommentFactory(match=match, parent=top_comment)
        grandchild = CommentFactory(match=match, parent=child_comment)

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="Nice take on the match, totally agree")
        ]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        comment = generate_bot_comment(
            profile.user,
            match,
            BotComment.TriggerType.REPLY,
            parent_comment=grandchild,
        )
        assert comment is not None
        assert comment.parent == child_comment


# ---------------------------------------------------------------------------
# _build_user_prompt
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBuildUserPrompt:
    def test_pre_match_with_bet(self):
        match = MatchFactory()
        OddsFactory(match=match)
        from epl.tests.factories import BetSlipFactory

        bet = BetSlipFactory(match=match)
        prompt = _build_user_prompt(
            match, BotComment.TriggerType.PRE_MATCH, bet_slip=bet
        )
        assert "Your bet:" in prompt
        assert "pre-match" in prompt.lower()

    def test_pre_match_without_bet(self):
        match = MatchFactory()
        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)
        assert "pre-match hype" in prompt.lower()

    def test_post_bet_includes_selection(self):
        match = MatchFactory()
        OddsFactory(match=match)
        from epl.tests.factories import BetSlipFactory

        bet = BetSlipFactory(match=match)
        prompt = _build_user_prompt(
            match, BotComment.TriggerType.POST_BET, bet_slip=bet
        )
        assert "Your bet:" in prompt
        assert "reacting to the bet" in prompt.lower()

    def test_post_match_includes_score(self):
        match = MatchFactory(home_score=2, away_score=1)
        prompt = _build_user_prompt(match, BotComment.TriggerType.POST_MATCH)
        assert "Final score:" in prompt
        assert "2-1" in prompt

    def test_reply_includes_quoted_text(self):
        match = MatchFactory()
        parent = CommentFactory(match=match, body="Arsenal is going to win this!")
        prompt = _build_user_prompt(
            match, BotComment.TriggerType.REPLY, parent_comment=parent
        )
        assert "Arsenal is going to win this!" in prompt
        assert "reply" in prompt.lower()

    def test_reply_truncates_long_quotes(self):
        match = MatchFactory()
        long_body = "x" * 500
        parent = CommentFactory(match=match, body=long_body)
        prompt = _build_user_prompt(
            match, BotComment.TriggerType.REPLY, parent_comment=parent
        )
        # The quoted text should be truncated to 300 chars
        assert long_body[:300] in prompt
        assert long_body[:301] not in prompt

    def test_includes_venue_when_present(self):
        home = TeamFactory(venue="Emirates Stadium")
        match = MatchFactory(home_team=home)
        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)
        assert "Emirates Stadium" in prompt

    def test_includes_odds_when_available(self):
        match = MatchFactory()
        OddsFactory(
            match=match,
            home_win=Decimal("1.50"),
            draw=Decimal("3.50"),
            away_win=Decimal("5.00"),
        )
        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)
        assert "Odds:" in prompt

    def test_bot_stats_included_when_provided(self):
        match = MatchFactory()
        prompt = _build_user_prompt(
            match,
            BotComment.TriggerType.PRE_MATCH,
            bot_stats="Balance: 112,450 credits | Net profit: +12,450 | Last 10: 6W-4L",
        )
        assert "Your stats:" in prompt
        assert "Balance: 112,450 credits" in prompt

    def test_bot_stats_omitted_when_empty(self):
        match = MatchFactory()
        prompt = _build_user_prompt(
            match, BotComment.TriggerType.PRE_MATCH, bot_stats=""
        )
        assert "Your stats:" not in prompt

    def test_target_stats_included_in_reply(self):
        match = MatchFactory()
        parent = CommentFactory(match=match, body="Arsenal will bottle it.")
        prompt = _build_user_prompt(
            match,
            BotComment.TriggerType.REPLY,
            parent_comment=parent,
            target_stats="Balance: 94,200 credits | Net profit: -5,800 | Last 10: 3W-7L",
        )
        assert "Net profit: -5,800" in prompt
        assert parent.user.display_name in prompt

    def test_target_stats_not_included_for_non_reply(self):
        match = MatchFactory()
        prompt = _build_user_prompt(
            match,
            BotComment.TriggerType.PRE_MATCH,
            target_stats="Balance: 94,200 credits | Last 10: 3W-7L",
        )
        assert "Balance: 94,200 credits" not in prompt


# ---------------------------------------------------------------------------
# build_user_stats_context
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBuildUserStatsContext:
    def test_empty_when_no_data(self):
        from epl.betting.models import BetSlip
        from vinosports.bots.prompt_utils import build_user_stats_context

        user = UserFactory()
        result = build_user_stats_context(user, BetSlip.objects.filter(user=user))
        assert result == ""

    def test_includes_balance(self):
        from epl.betting.models import BetSlip
        from vinosports.bots.prompt_utils import build_user_stats_context

        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("75000.00"))
        result = build_user_stats_context(user, BetSlip.objects.filter(user=user))
        assert "Balance: 75,000 credits" in result

    def test_includes_net_profit_positive(self):
        from epl.betting.models import BetSlip
        from vinosports.bots.prompt_utils import build_user_stats_context

        user = UserFactory()
        UserStatsFactory(
            user=user,
            net_profit=Decimal("12450.00"),
            total_bets=20,
            total_wins=12,
            total_losses=8,
        )
        result = build_user_stats_context(user, BetSlip.objects.filter(user=user))
        assert "Net profit: +12,450" in result
        assert "Overall: 12W-8L" in result

    def test_includes_net_profit_negative(self):
        from epl.betting.models import BetSlip
        from vinosports.bots.prompt_utils import build_user_stats_context

        user = UserFactory()
        UserStatsFactory(
            user=user,
            net_profit=Decimal("-5000.00"),
            total_bets=10,
            total_wins=3,
            total_losses=7,
        )
        result = build_user_stats_context(user, BetSlip.objects.filter(user=user))
        assert "Net profit: -5,000" in result

    def test_includes_streak(self):
        from epl.betting.models import BetSlip
        from vinosports.bots.prompt_utils import build_user_stats_context

        user = UserFactory()
        UserStatsFactory(user=user, current_streak=3)
        result = build_user_stats_context(user, BetSlip.objects.filter(user=user))
        assert "Streak: 3W" in result

    def test_losing_streak(self):
        from epl.betting.models import BetSlip
        from vinosports.bots.prompt_utils import build_user_stats_context

        user = UserFactory()
        UserStatsFactory(user=user, current_streak=-4)
        result = build_user_stats_context(user, BetSlip.objects.filter(user=user))
        assert "Streak: 4L" in result

    def test_last_10_record_from_bets(self):
        from epl.betting.models import BetSlip
        from vinosports.betting.models import BetStatus
        from vinosports.bots.prompt_utils import build_user_stats_context

        user = UserFactory()
        match = MatchFactory()
        for _ in range(6):
            BetSlipFactory(user=user, match=match, status=BetStatus.WON)
        for _ in range(4):
            BetSlipFactory(user=user, match=match, status=BetStatus.LOST)
        result = build_user_stats_context(user, BetSlip.objects.filter(user=user))
        assert "Last 10: 6W-4L" in result

    def test_last_10_caps_at_10(self):
        from epl.betting.models import BetSlip
        from vinosports.betting.models import BetStatus
        from vinosports.bots.prompt_utils import build_user_stats_context

        user = UserFactory()
        match = MatchFactory()
        for _ in range(15):
            BetSlipFactory(user=user, match=match, status=BetStatus.WON)
        result = build_user_stats_context(user, BetSlip.objects.filter(user=user))
        assert "Last 10: 10W-0L" in result

    def test_pending_bets_excluded_from_last_10(self):
        from epl.betting.models import BetSlip
        from vinosports.betting.models import BetStatus
        from vinosports.bots.prompt_utils import build_user_stats_context

        user = UserFactory()
        match = MatchFactory()
        BetSlipFactory(user=user, match=match, status=BetStatus.WON)
        BetSlipFactory(user=user, match=match, status=BetStatus.PENDING)
        result = build_user_stats_context(user, BetSlip.objects.filter(user=user))
        assert "Last 1: 1W-0L" in result


# ---------------------------------------------------------------------------
# generate_bot_comment — stats in prompt
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGenerateBotCommentStats:
    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_bot_stats_appear_in_stored_prompt(self, MockAnthropic, settings):
        """Bot's balance/stats should be present in the prompt_used on BotComment."""
        settings.ANTHROPIC_API_KEY = "test-key"
        match = MatchFactory()
        OddsFactory(match=match)
        profile = BotProfileFactory(strategy_type=StrategyType.FRONTRUNNER)
        bot_user = profile.user
        UserBalanceFactory(user=bot_user, balance=Decimal("88000.00"))

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="Arsenal looking strong today in the match")
        ]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        generate_bot_comment(bot_user, match, BotComment.TriggerType.PRE_MATCH)

        bc = BotComment.objects.get(user=bot_user, match=match)
        assert "88,000 credits" in bc.prompt_used

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_target_stats_appear_in_reply_prompt(self, MockAnthropic, settings):
        """When replying, the target user's stats should be in the prompt."""
        settings.ANTHROPIC_API_KEY = "test-key"
        match = MatchFactory()
        OddsFactory(match=match)
        profile = BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT)
        bot_user = profile.user

        human = UserFactory()
        UserBalanceFactory(user=human, balance=Decimal("55000.00"))
        parent = CommentFactory(
            match=match, user=human, body="This match is going to be a banger"
        )

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="Classic vibes bet on this match today")
        ]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        generate_bot_comment(
            bot_user, match, BotComment.TriggerType.REPLY, parent_comment=parent
        )

        bc = BotComment.objects.get(user=bot_user, match=match)
        assert "55,000 credits" in bc.prompt_used
