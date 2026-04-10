"""Tests for vinosports.bots.comment_pipeline — centralized bot comment generation."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from vinosports.bots.comment_pipeline import (
    DEFAULT_MAX_REPLIES,
    MatchContext,
    _format_age,
    _maybe_trigger_life_update,
    build_own_archive_context,
    build_target_archive_context,
    build_user_prompt,
    filter_comment,
    generate_comment,
    generate_life_update,
    get_bot_profile,
    homer_team_mentioned,
    select_bots_for_event,
    select_reply_bot,
    trim_to_last_sentence,
)
from vinosports.bots.models import BotArchiveEntry, EntryType

from .factories import BotProfileFactory, UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_match_ctx(**overrides):
    """Create a minimal MatchContext for testing."""
    defaults = {
        "event_id": 1,
        "league": "epl",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "home_team_short": "ARS",
        "away_team_short": "CHE",
        "header_lines": ["Match: Arsenal vs Chelsea", "Kickoff: Sat 10 Apr, 15:00 UTC"],
        "odds_line": "Odds: ARS 1.50 | Draw 4.00 | CHE 6.00",
        "stats_lines": [],
        "notes": "",
        "score_line": "",
        "team_terms": {"arsenal", "chelsea", "ars", "che"},
    }
    defaults.update(overrides)
    return MatchContext(**defaults)


# ---------------------------------------------------------------------------
# trim_to_last_sentence
# ---------------------------------------------------------------------------


class TestTrimToLastSentence:
    def test_trims_at_period(self):
        assert trim_to_last_sentence("Hello world. This is cut") == "Hello world."

    def test_trims_at_exclamation(self):
        assert trim_to_last_sentence("What a goal! Incredible play") == "What a goal!"

    def test_trims_at_question(self):
        assert trim_to_last_sentence("Is that right? I think") == "Is that right?"

    def test_returns_as_is_when_no_punctuation(self):
        assert trim_to_last_sentence("no punctuation here") == "no punctuation here"

    def test_handles_single_sentence(self):
        assert trim_to_last_sentence("Just one sentence.") == "Just one sentence."


# ---------------------------------------------------------------------------
# filter_comment
# ---------------------------------------------------------------------------


class TestFilterComment:
    def test_too_short(self):
        ok, reason = filter_comment("Hi", {"arsenal"}, {"goal"})
        assert not ok
        assert reason == "too_short"

    def test_too_long(self):
        ok, reason = filter_comment("x" * 501, {"arsenal"}, {"goal"})
        assert not ok
        assert reason == "too_long"

    def test_profanity_rejected(self):
        ok, reason = filter_comment(
            "What the fuck is this goal prediction", {"arsenal"}, {"goal"}
        )
        assert not ok
        assert "profanity" in reason

    def test_irrelevant_rejected(self):
        ok, reason = filter_comment(
            "I love cooking pasta with tomato sauce everyday", set(), set()
        )
        assert not ok
        assert reason == "irrelevant"

    def test_relevant_with_team_name(self):
        ok, reason = filter_comment(
            "Arsenal are looking strong today", {"arsenal"}, set()
        )
        assert ok

    def test_relevant_with_keyword(self):
        ok, reason = filter_comment(
            "What a beautiful goal to open the scoring", set(), {"goal"}
        )
        assert ok

    def test_profanity_word_boundary(self):
        ok, _ = filter_comment(
            "Arsenal played a great match today", {"arsenal"}, {"match"}
        )
        assert ok


# ---------------------------------------------------------------------------
# get_bot_profile
# ---------------------------------------------------------------------------


class TestGetBotProfile:
    def test_returns_profile(self):
        profile = BotProfileFactory()
        assert get_bot_profile(profile.user) == profile

    def test_returns_none_for_non_bot(self):
        user = UserFactory()
        assert get_bot_profile(user) is None


# ---------------------------------------------------------------------------
# _format_age
# ---------------------------------------------------------------------------


class TestFormatAge:
    def test_just_now(self):
        assert _format_age(timezone.now()) == "just now"

    def test_hours_ago(self):
        dt = timezone.now() - timedelta(hours=3)
        assert _format_age(dt) == "3h ago"

    def test_yesterday(self):
        dt = timezone.now() - timedelta(days=1)
        assert _format_age(dt) == "yesterday"

    def test_days_ago(self):
        dt = timezone.now() - timedelta(days=4)
        assert _format_age(dt) == "4 days ago"

    def test_weeks_ago(self):
        dt = timezone.now() - timedelta(days=14)
        assert _format_age(dt) == "2 weeks ago"

    def test_months_ago(self):
        dt = timezone.now() - timedelta(days=60)
        assert _format_age(dt) == "2 months ago"


# ---------------------------------------------------------------------------
# build_user_prompt
# ---------------------------------------------------------------------------


class TestBuildUserPrompt:
    def test_pre_match_with_bet(self):
        ctx = _make_match_ctx()
        bet = MagicMock()
        bet.get_selection_display.return_value = "Home Win"
        bet.odds_at_placement = 1.50
        bet.stake = 100
        prompt = build_user_prompt(ctx, "PRE_MATCH", bet_slip=bet)
        assert "Arsenal vs Chelsea" in prompt
        assert "Home Win" in prompt
        assert "hyping or defending" in prompt

    def test_pre_match_without_bet(self):
        ctx = _make_match_ctx()
        prompt = build_user_prompt(ctx, "PRE_MATCH")
        assert "pre-match hype comment" in prompt

    def test_post_bet(self):
        ctx = _make_match_ctx()
        bet = MagicMock()
        bet.get_selection_display.return_value = "Away Win"
        bet.odds_at_placement = 6.00
        bet.stake = 50
        prompt = build_user_prompt(ctx, "POST_BET", bet_slip=bet)
        assert "Away Win" in prompt
        assert "reacting to the bet" in prompt

    def test_post_match_with_bet_won(self):
        ctx = _make_match_ctx(score_line="Final score: Arsenal 2-1 Chelsea")
        bet = MagicMock()
        bet.get_selection_display.return_value = "Home Win"
        bet.odds_at_placement = 1.50
        bet.status = "WON"
        bet.payout = 150
        prompt = build_user_prompt(ctx, "POST_MATCH", bet_slip=bet)
        assert "Final score" in prompt
        assert "WON" in prompt
        assert "Payout: 150" in prompt

    def test_post_match_without_bet(self):
        ctx = _make_match_ctx(score_line="Final score: Arsenal 0-0 Chelsea")
        prompt = build_user_prompt(ctx, "POST_MATCH")
        assert "reacting to the final result" in prompt

    def test_reply(self):
        ctx = _make_match_ctx()
        parent = MagicMock()
        parent.body = "Arsenal are definitely winning this"
        parent.user.display_name = "ChalkEater"
        parent.user.is_bot = True
        prompt = build_user_prompt(ctx, "REPLY", parent_comment=parent)
        assert "ChalkEater" in prompt
        assert "Arsenal are definitely winning" in prompt
        assert "stay in character" in prompt

    def test_reply_to_bot_includes_social_instructions(self):
        ctx = _make_match_ctx()
        parent = MagicMock()
        parent.body = "Arsenal looking strong"
        parent.user.display_name = "ChalkEater"
        parent.user.is_bot = True
        prompt = build_user_prompt(ctx, "REPLY", parent_comment=parent)
        assert "You trust the other regulars" in prompt

    def test_reply_to_human_excludes_social_instructions(self):
        ctx = _make_match_ctx()
        parent = MagicMock()
        parent.body = "Arsenal looking strong"
        parent.user.display_name = "HumanUser"
        parent.user.is_bot = False
        prompt = build_user_prompt(ctx, "REPLY", parent_comment=parent)
        assert "You trust the other regulars" not in prompt

    def test_match_notes_included_for_post_match(self):
        ctx = _make_match_ctx(
            notes="Incredible last-minute goal",
            score_line="Final score: Arsenal 1-0 Chelsea",
        )
        prompt = build_user_prompt(ctx, "POST_MATCH")
        assert "Match notes (from a real viewer):" in prompt
        assert "Incredible last-minute goal" in prompt

    def test_match_notes_excluded_for_pre_match(self):
        ctx = _make_match_ctx(notes="Should not appear")
        prompt = build_user_prompt(ctx, "PRE_MATCH")
        assert "Match notes" not in prompt

    def test_own_archive_context_included(self):
        ctx = _make_match_ctx()
        prompt = build_user_prompt(
            ctx, "PRE_MATCH", own_archive_context="YOUR RECENT HISTORY:\n- Won an award"
        )
        assert "YOUR RECENT HISTORY" in prompt
        assert "Won an award" in prompt

    def test_target_archive_context_included(self):
        ctx = _make_match_ctx()
        parent = MagicMock()
        parent.body = "Test reply"
        parent.user.display_name = "Target"
        parent.user.is_bot = True
        prompt = build_user_prompt(
            ctx,
            "REPLY",
            parent_comment=parent,
            target_archive_context="ABOUT Target:\n- Loves hiking",
        )
        assert "ABOUT Target" in prompt
        assert "Loves hiking" in prompt

    def test_odds_line_included(self):
        ctx = _make_match_ctx(odds_line="Odds: ARS 1.50 | Draw 4.00 | CHE 6.00")
        prompt = build_user_prompt(ctx, "PRE_MATCH")
        assert "Odds: ARS 1.50" in prompt

    def test_bot_stats_included(self):
        ctx = _make_match_ctx()
        prompt = build_user_prompt(
            ctx, "PRE_MATCH", bot_stats="Balance: 10,000 | Net: +500"
        )
        assert "Your stats: Balance: 10,000" in prompt


# ---------------------------------------------------------------------------
# build_own_archive_context / build_target_archive_context
# ---------------------------------------------------------------------------


class TestArchiveContext:
    def test_own_archive_empty_when_no_entries(self):
        profile = BotProfileFactory()
        assert build_own_archive_context(profile) == ""

    def test_own_archive_includes_entries(self):
        profile = BotProfileFactory()
        BotArchiveEntry.objects.create(
            bot_profile=profile,
            entry_type=EntryType.AWARD,
            summary="Won Hot Streak award",
        )
        result = build_own_archive_context(profile)
        assert "YOUR RECENT HISTORY" in result
        assert "Won Hot Streak award" in result

    def test_own_archive_limited_to_max(self):
        profile = BotProfileFactory()
        for i in range(10):
            BotArchiveEntry.objects.create(
                bot_profile=profile,
                entry_type=EntryType.LIFE_UPDATE,
                summary=f"Entry {i}",
            )
        result = build_own_archive_context(profile)
        # Should only include 5 entries (MAX_OWN_ARCHIVE_ENTRIES)
        assert result.count("- [") == 5

    def test_target_archive_returns_empty_for_non_bot(self):
        profile = BotProfileFactory()
        human = UserFactory()
        assert build_target_archive_context(profile, human) == ""

    def test_target_archive_returns_empty_when_no_entries(self):
        profile1 = BotProfileFactory()
        profile2 = BotProfileFactory()
        assert build_target_archive_context(profile1, profile2.user) == ""

    def test_target_archive_includes_entries(self):
        profile1 = BotProfileFactory()
        profile2 = BotProfileFactory()
        BotArchiveEntry.objects.create(
            bot_profile=profile2,
            entry_type=EntryType.LIFE_UPDATE,
            summary="Grew up in Liverpool",
        )
        result = build_target_archive_context(profile1, profile2.user)
        assert f"ABOUT {profile2.user.display_name}" in result
        assert "Grew up in Liverpool" in result

    def test_target_archive_includes_shared_history(self):
        profile1 = BotProfileFactory()
        profile2 = BotProfileFactory()
        BotArchiveEntry.objects.create(
            bot_profile=profile2,
            entry_type=EntryType.LIFE_UPDATE,
            summary="Loves hiking",
        )
        BotArchiveEntry.objects.create(
            bot_profile=profile1,
            entry_type=EntryType.SOCIAL,
            summary="Asked about hiking",
            related_bot=profile2,
        )
        result = build_target_archive_context(profile1, profile2.user)
        assert "YOUR HISTORY WITH" in result
        assert "Asked about hiking" in result


# ---------------------------------------------------------------------------
# generate_comment (mocked Claude)
# ---------------------------------------------------------------------------


class TestGenerateComment:
    def _make_adapter(self):
        adapter = MagicMock()
        adapter.league = "epl"
        adapter.keywords = {"match", "goal", "bet"}
        adapter.max_replies = 4
        adapter.active_field = "active_in_epl"

        BotComment = MagicMock()
        BotComment.objects.get_or_create.return_value = (MagicMock(), True)
        BotComment.objects.filter.return_value.count.return_value = 0
        adapter.get_bot_comment_model.return_value = BotComment

        Comment = MagicMock()
        adapter.get_comment_model.return_value = Comment

        BetSlip = MagicMock()
        BetSlip.objects.filter.return_value = MagicMock()
        adapter.get_bet_slip_model.return_value = BetSlip

        adapter.get_event_fk_name.return_value = "match"
        adapter.build_match_context.return_value = _make_match_ctx()
        adapter.get_bot_profiles_qs.return_value = []

        return adapter

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_successful_generation(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="Arsenal looking strong for this match!")
        ]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        adapter = self._make_adapter()
        profile = BotProfileFactory()
        event = MagicMock()
        event.pk = 1

        comment = generate_comment(adapter, profile.user, event, "PRE_MATCH")
        assert comment is not None

    def test_no_profile_returns_none(self):
        adapter = self._make_adapter()
        user = UserFactory()  # non-bot user, no profile
        event = MagicMock()
        assert generate_comment(adapter, user, event, "PRE_MATCH") is None

    def test_no_persona_returns_none(self):
        adapter = self._make_adapter()
        profile = BotProfileFactory(persona_prompt="")
        event = MagicMock()
        assert generate_comment(adapter, profile.user, event, "PRE_MATCH") is None

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_dedup_returns_none(self, MockAnthropic):
        adapter = self._make_adapter()
        # Simulate already exists
        adapter.get_bot_comment_model().objects.get_or_create.return_value = (
            MagicMock(),
            False,
        )

        profile = BotProfileFactory()
        event = MagicMock()
        event.pk = 1
        assert generate_comment(adapter, profile.user, event, "PRE_MATCH") is None

    @patch("vinosports.bots.comment_pipeline.settings")
    def test_no_api_key_returns_none(self, mock_settings):
        mock_settings.ANTHROPIC_API_KEY = ""
        adapter = self._make_adapter()
        profile = BotProfileFactory()
        event = MagicMock()
        event.pk = 1
        assert generate_comment(adapter, profile.user, event, "PRE_MATCH") is None

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_filtered_comment_returns_none(self, MockAnthropic):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="I love cooking pasta")]  # irrelevant
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        adapter = self._make_adapter()
        profile = BotProfileFactory()
        event = MagicMock()
        event.pk = 1
        assert generate_comment(adapter, profile.user, event, "PRE_MATCH") is None


# ---------------------------------------------------------------------------
# homer_team_mentioned
# ---------------------------------------------------------------------------


class TestHomerTeamMentioned:
    def test_no_identifier_returns_false(self):
        adapter = MagicMock()
        adapter.get_homer_identifier.return_value = ""
        profile = BotProfileFactory()
        assert not homer_team_mentioned(adapter, profile, "Arsenal are great")

    def test_long_term_match(self):
        adapter = MagicMock()
        adapter.league = "test"
        adapter.get_homer_identifier.return_value = "ARS"
        adapter.resolve_homer_terms.return_value = ("arsenal", "arsenal", "ars")
        profile = BotProfileFactory()
        # Clear cache for this test
        from vinosports.bots.comment_pipeline import _homer_team_cache

        _homer_team_cache.clear()
        assert homer_team_mentioned(adapter, profile, "Arsenal are brilliant")

    def test_short_term_word_boundary(self):
        adapter = MagicMock()
        adapter.league = "test2"
        adapter.get_homer_identifier.return_value = "ARS"
        adapter.resolve_homer_terms.return_value = ("arsenal", "arsenal", "ars")
        profile = BotProfileFactory()
        from vinosports.bots.comment_pipeline import _homer_team_cache

        _homer_team_cache.clear()
        # "ARS" should NOT match inside "stars"
        assert not homer_team_mentioned(adapter, profile, "The stars are out tonight")


# ---------------------------------------------------------------------------
# select_reply_bot / select_bots_for_event
# ---------------------------------------------------------------------------


class TestSelectReplyBot:
    def test_returns_none_when_cap_reached(self):
        adapter = MagicMock()
        BotComment = MagicMock()
        BotComment.objects.filter.return_value.count.return_value = DEFAULT_MAX_REPLIES
        adapter.get_bot_comment_model.return_value = BotComment
        adapter.get_event_fk_name.return_value = "match"
        adapter.max_replies = DEFAULT_MAX_REPLIES

        event = MagicMock()
        comment = MagicMock()
        assert select_reply_bot(adapter, event, comment) is None


class TestSelectBotsForEvent:
    def test_returns_empty_when_no_candidates(self):
        adapter = MagicMock()
        BotComment = MagicMock()
        BotComment.objects.filter.return_value.values_list.return_value = []
        adapter.get_bot_comment_model.return_value = BotComment
        adapter.get_event_fk_name.return_value = "match"
        adapter.get_bot_profiles_qs.return_value = []

        event = MagicMock()
        result = select_bots_for_event(adapter, event, "PRE_MATCH")
        assert result == []


# ---------------------------------------------------------------------------
# generate_life_update
# ---------------------------------------------------------------------------


class TestGenerateLifeUpdate:
    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_successful_life_update(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="Been restoring a vintage motorcycle in my garage.")
        ]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        profile = BotProfileFactory()
        result = generate_life_update(profile, question_context="What's your hobby?")

        assert result is not None
        assert "motorcycle" in result
        # Should create an archive entry
        entry = BotArchiveEntry.objects.get(
            bot_profile=profile, entry_type=EntryType.LIFE_UPDATE
        )
        assert "motorcycle" in entry.summary

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_spontaneous_life_update(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="My daughter started school this week.")
        ]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        profile = BotProfileFactory()
        result = generate_life_update(profile)
        assert result is not None
        entry = BotArchiveEntry.objects.get(bot_profile=profile)
        assert entry.raw_source == "spontaneous"

    @patch("vinosports.bots.comment_pipeline.settings")
    def test_no_api_key_returns_none(self, mock_settings):
        mock_settings.ANTHROPIC_API_KEY = ""
        profile = BotProfileFactory()
        assert generate_life_update(profile) is None

    @patch("vinosports.bots.comment_pipeline.anthropic.Anthropic")
    def test_includes_existing_archive_in_prompt(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Still riding every weekend.")]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        profile = BotProfileFactory()
        BotArchiveEntry.objects.create(
            bot_profile=profile,
            entry_type=EntryType.LIFE_UPDATE,
            summary="Loves motorcycles",
        )
        generate_life_update(profile, question_context="Still riding?")

        # Verify the prompt included existing archive
        call_args = MockAnthropic.return_value.messages.create.call_args
        user_msg = call_args[1]["messages"][0]["content"]
        assert "Loves motorcycles" in user_msg


# ---------------------------------------------------------------------------
# _maybe_trigger_life_update
# ---------------------------------------------------------------------------


class TestMaybeTriggerLifeUpdate:
    def test_no_question_mark_does_nothing(self):
        adapter = MagicMock()
        event = MagicMock()
        asking_comment = MagicMock()
        author_profile = BotProfileFactory()
        parent_comment = MagicMock()
        parent_comment.user.is_bot = True

        _maybe_trigger_life_update(
            adapter,
            event,
            asking_comment,
            author_profile,
            parent_comment,
            "Arsenal will win for sure",
        )
        assert BotArchiveEntry.objects.count() == 0

    def test_human_parent_does_nothing(self):
        adapter = MagicMock()
        event = MagicMock()
        asking_comment = MagicMock()
        author_profile = BotProfileFactory()
        parent_comment = MagicMock()
        parent_comment.user.is_bot = False

        _maybe_trigger_life_update(
            adapter,
            event,
            asking_comment,
            author_profile,
            parent_comment,
            "How's your day going?",
        )
        assert BotArchiveEntry.objects.count() == 0

    def test_betting_question_skipped(self):
        adapter = MagicMock()
        event = MagicMock()
        asking_comment = MagicMock()
        author_profile = BotProfileFactory()
        target_profile = BotProfileFactory()
        parent_comment = MagicMock()
        parent_comment.user = target_profile.user
        parent_comment.user.is_bot = True

        _maybe_trigger_life_update(
            adapter,
            event,
            asking_comment,
            author_profile,
            parent_comment,
            "What are the odds on that bet?",
        )
        assert BotArchiveEntry.objects.count() == 0

    @patch("vinosports.bots.comment_pipeline.generate_life_update")
    def test_personal_question_triggers_life_update(self, mock_generate):
        mock_generate.return_value = "I've been great, thanks!"

        adapter = MagicMock()
        CommentModel = MagicMock()
        adapter.get_comment_model.return_value = CommentModel
        BotCommentModel = MagicMock()
        adapter.get_bot_comment_model.return_value = BotCommentModel
        adapter.get_event_fk_name.return_value = "match"

        event = MagicMock()
        asking_comment = MagicMock()
        asking_comment.depth = 1
        asking_comment.parent = MagicMock()
        author_profile = BotProfileFactory()
        target_profile = BotProfileFactory()
        parent_comment = MagicMock()
        parent_comment.user = target_profile.user
        parent_comment.user.is_bot = True

        _maybe_trigger_life_update(
            adapter,
            event,
            asking_comment,
            author_profile,
            parent_comment,
            "How's your weekend shaping up?",
        )

        mock_generate.assert_called_once()
        # Should create a SOCIAL entry for the asking bot
        social = BotArchiveEntry.objects.filter(
            bot_profile=author_profile, entry_type=EntryType.SOCIAL
        )
        assert social.exists()
        assert "weekend" in social.first().summary.lower()
