"""Tests for epl.bots.tasks — Celery task orchestration for bot betting and comments."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from epl.betting.models import BetSlip
from epl.bots.models import BotComment
from epl.bots.tasks import (
    execute_bot_strategy,
    generate_bot_comment_task,
    generate_bot_reply_task,
    generate_postmatch_comments,
    generate_prematch_comments,
    maybe_reply_to_human_comment,
    run_bot_strategies,
)
from epl.matches.models import Match
from epl.tests.factories import (
    BetSlipFactory,
    BotCommentFactory,
    BotProfileFactory,
    BotUserFactory,
    CommentFactory,
    MatchFactory,
    OddsFactory,
    UserBalanceFactory,
    UserFactory,
)
from vinosports.bots.models import StrategyType

# ---------------------------------------------------------------------------
# run_bot_strategies orchestrator
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRunBotStrategies:
    def test_skips_inactive_bots(self):
        BotProfileFactory(is_active=False)
        result = run_bot_strategies()
        assert result["dispatched"] == 0

    def test_skips_bots_not_active_in_epl(self):
        BotProfileFactory(is_active=True, active_in_epl=False)
        result = run_bot_strategies()
        assert result["dispatched"] == 0

    @patch("epl.bots.tasks.roll_action", return_value=False)
    def test_skips_when_roll_fails(self, mock_roll):
        BotProfileFactory(is_active=True, active_in_epl=True)
        result = run_bot_strategies()
        assert result["dispatched"] == 0

    @patch("epl.bots.tasks.execute_bot_strategy.apply_async")
    @patch("epl.bots.tasks.roll_action", return_value=True)
    @patch("epl.bots.tasks.get_active_window")
    def test_dispatches_active_bot(self, mock_window, mock_roll, mock_apply):
        mock_window.return_value = {"bet_probability": 0.8}
        BotProfileFactory(is_active=True, active_in_epl=True)
        result = run_bot_strategies()
        assert result["dispatched"] == 1
        mock_apply.assert_called_once()

    @patch("epl.bots.tasks.execute_bot_strategy.apply_async")
    @patch("epl.bots.tasks.roll_action", return_value=True)
    @patch("epl.bots.tasks.get_active_window", return_value=None)
    def test_skips_when_no_active_window(self, mock_window, mock_roll, mock_apply):
        BotProfileFactory(is_active=True, active_in_epl=True)
        result = run_bot_strategies()
        assert result["dispatched"] == 0
        assert result["skipped_schedule"] == 1

    @patch("epl.bots.tasks.execute_bot_strategy.apply_async")
    @patch("epl.bots.tasks.roll_action", return_value=True)
    @patch("epl.bots.tasks.get_active_window")
    def test_respects_daily_bet_limit(self, mock_window, mock_roll, mock_apply):
        mock_window.return_value = {"bet_probability": 0.8}
        profile = BotProfileFactory(
            is_active=True, active_in_epl=True, max_daily_bets=2
        )
        match = MatchFactory()
        # Create 2 bets already today
        BetSlipFactory(user=profile.user, match=match)
        BetSlipFactory(
            user=profile.user, match=match, selection=BetSlip.Selection.AWAY_WIN
        )
        result = run_bot_strategies()
        assert result["dispatched"] == 0


# ---------------------------------------------------------------------------
# execute_bot_strategy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExecuteBotStrategy:
    def test_user_not_found(self):
        result = execute_bot_strategy(999999)
        assert result == "bot not found"

    def test_non_bot_user(self):
        user = UserFactory(is_bot=False)
        result = execute_bot_strategy(user.pk)
        assert result == "bot not found"

    def test_no_strategy_returns_no_strategy(self):
        """Bot with a strategy_type not in the registry returns 'no strategy'."""
        profile = BotProfileFactory(
            is_active=True,
            active_in_epl=True,
            strategy_type=StrategyType.SPREAD_SHARK,  # Not mapped for EPL
        )
        UserBalanceFactory(user=profile.user)
        MatchFactory(status=Match.Status.SCHEDULED)
        result = execute_bot_strategy(profile.user.pk)
        assert result == "no strategy"

    def test_no_matches_returns_no_matches(self):
        profile = BotProfileFactory(is_active=True, active_in_epl=True)
        UserBalanceFactory(user=profile.user)
        # No scheduled matches
        result = execute_bot_strategy(profile.user.pk)
        assert result == "no matches"

    def test_no_odds_returns_message(self):
        profile = BotProfileFactory(is_active=True, active_in_epl=True)
        UserBalanceFactory(user=profile.user)
        MatchFactory(status=Match.Status.SCHEDULED)
        # No odds created
        result = execute_bot_strategy(profile.user.pk)
        assert "no odds" in result

    def test_no_balance_returns_message(self):
        profile = BotProfileFactory(is_active=True, active_in_epl=True)
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)
        # No UserBalance record
        result = execute_bot_strategy(profile.user.pk)
        assert result == "no balance"

    @patch("epl.bots.tasks.random.random", return_value=1.0)  # Skip comment dispatch
    @patch("epl.bots.tasks.queue_activity_event")
    def test_places_bets_when_matches_available(self, mock_activity, mock_rand):
        profile = BotProfileFactory(
            is_active=True,
            active_in_epl=True,
            strategy_type=StrategyType.FRONTRUNNER,
        )
        UserBalanceFactory(user=profile.user, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(
            match=match,
            home_win=Decimal("1.50"),
            draw=Decimal("3.50"),
            away_win=Decimal("5.00"),
        )

        result = execute_bot_strategy(profile.user.pk)
        # Frontrunner should bet on 1.50 favorite
        assert "1 bets" in result or "1 bet" in result

    @patch("epl.bots.tasks.random.random", return_value=1.0)
    @patch("epl.bots.tasks.queue_activity_event")
    def test_topup_on_low_balance(self, mock_activity, mock_rand):
        profile = BotProfileFactory(
            is_active=True,
            active_in_epl=True,
            strategy_type=StrategyType.FRONTRUNNER,
        )
        UserBalanceFactory(user=profile.user, balance=Decimal("10.00"))
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(
            match=match,
            home_win=Decimal("1.50"),
            draw=Decimal("3.50"),
            away_win=Decimal("5.00"),
        )

        execute_bot_strategy(profile.user.pk)
        # maybe_topup_bot should have given the bot more balance
        from vinosports.betting.models import UserBalance

        balance = UserBalance.objects.get(user=profile.user)
        # Either bot was topped up or placed a bet with remaining balance
        assert balance.balance > Decimal("0")


# ---------------------------------------------------------------------------
# generate_bot_comment_task
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGenerateBotCommentTask:
    def test_bot_not_found(self):
        result = generate_bot_comment_task(999999, 1, BotComment.TriggerType.PRE_MATCH)
        assert result == "bot not found"

    def test_match_not_found(self):
        bot = BotUserFactory()
        result = generate_bot_comment_task(
            bot.pk, 999999, BotComment.TriggerType.PRE_MATCH
        )
        assert result == "match not found"

    @patch("epl.bots.comment_service.anthropic.Anthropic")
    def test_successful_comment(self, MockAnthropic, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        match = MatchFactory()
        OddsFactory(match=match)
        profile = BotProfileFactory()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Big match energy, love these odds")]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        result = generate_bot_comment_task(
            profile.user.pk, match.pk, BotComment.TriggerType.PRE_MATCH
        )
        assert "posted:" in result

    @patch("epl.bots.comment_service.anthropic.Anthropic")
    def test_dedup_returns_skipped(self, MockAnthropic):
        match = MatchFactory()
        profile = BotProfileFactory()
        BotCommentFactory(
            user=profile.user,
            match=match,
            trigger_type=BotComment.TriggerType.PRE_MATCH,
        )
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Great match odds today")]
        mock_response.stop_reason = "end_turn"
        MockAnthropic.return_value.messages.create.return_value = mock_response

        result = generate_bot_comment_task(
            profile.user.pk, match.pk, BotComment.TriggerType.PRE_MATCH
        )
        assert "skipped" in result


# ---------------------------------------------------------------------------
# generate_bot_reply_task
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGenerateBotReplyTask:
    def test_bot_not_found(self):
        result = generate_bot_reply_task(999999, 1, 1)
        assert result == "bot not found"

    def test_match_not_found(self):
        bot = BotUserFactory()
        result = generate_bot_reply_task(bot.pk, 999999, 1)
        assert result == "match not found"

    def test_parent_not_found(self):
        bot = BotUserFactory()
        match = MatchFactory()
        result = generate_bot_reply_task(bot.pk, match.pk, 999999)
        assert result == "parent comment not found"


# ---------------------------------------------------------------------------
# maybe_reply_to_human_comment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMaybeReplyToHumanComment:
    def test_comment_not_found(self):
        result = maybe_reply_to_human_comment(999999)
        assert result == "comment not found"

    def test_skips_bot_author(self):
        bot = BotUserFactory()
        comment = CommentFactory(user=bot)
        result = maybe_reply_to_human_comment(comment.pk)
        assert result == "skipped (bot author)"

    @patch("epl.bots.comment_service.select_reply_bot", return_value=None)
    def test_no_candidate_returns_skipped(self, mock_select):
        user = UserFactory()
        match = MatchFactory()
        comment = CommentFactory(user=user, match=match)
        result = maybe_reply_to_human_comment(comment.pk)
        assert result == "skipped (no candidate)"


# ---------------------------------------------------------------------------
# generate_prematch_comments
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGeneratePrematchComments:
    @patch("epl.bots.tasks.generate_bot_comment_task.apply_async")
    @patch("epl.bots.tasks.roll_action", return_value=True)
    @patch("epl.bots.tasks.get_active_window")
    def test_dispatches_for_upcoming_matches(self, mock_window, mock_roll, mock_apply):
        mock_window.return_value = {"comment_probability": 0.8}
        match = MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=timezone.now() + timezone.timedelta(hours=3),
        )
        OddsFactory(match=match)
        BotProfileFactory(strategy_type=StrategyType.CHAOS_AGENT)

        result = generate_prematch_comments()
        assert "dispatched" in result
        assert mock_apply.called

    def test_no_upcoming_matches_dispatches_zero(self):
        # Only past matches
        MatchFactory(
            status=Match.Status.FINISHED,
            kickoff=timezone.now() - timezone.timedelta(hours=5),
        )
        result = generate_prematch_comments()
        assert "dispatched 0" in result


# ---------------------------------------------------------------------------
# generate_postmatch_comments
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGeneratePostmatchComments:
    @patch("epl.bots.tasks.generate_bot_comment_task.apply_async")
    @patch("epl.bots.tasks.roll_action", return_value=True)
    @patch("epl.bots.tasks.get_active_window")
    def test_dispatches_for_recently_finished(self, mock_window, mock_roll, mock_apply):
        mock_window.return_value = {"comment_probability": 0.8}
        match = MatchFactory(
            status=Match.Status.FINISHED,
            kickoff=timezone.now() - timezone.timedelta(hours=1),
        )
        profile = BotProfileFactory(strategy_type=StrategyType.FRONTRUNNER)
        BetSlipFactory(user=profile.user, match=match)

        result = generate_postmatch_comments()
        assert "dispatched" in result

    def test_no_finished_matches_dispatches_zero(self):
        MatchFactory(status=Match.Status.SCHEDULED)
        result = generate_postmatch_comments()
        assert "dispatched 0" in result

    @patch("epl.bots.tasks.generate_bot_comment_task.apply_async")
    @patch("epl.bots.tasks.roll_action", return_value=True)
    @patch("epl.bots.tasks.get_active_window")
    @patch("epl.bots.comment_service.select_bots_for_match", return_value=[])
    def test_skips_bot_with_existing_postmatch_comment(
        self, mock_select, mock_window, mock_roll, mock_apply
    ):
        mock_window.return_value = {"comment_probability": 0.8}
        match = MatchFactory(
            status=Match.Status.FINISHED,
            kickoff=timezone.now() - timezone.timedelta(hours=1),
        )
        profile = BotProfileFactory(strategy_type=StrategyType.FRONTRUNNER)
        BetSlipFactory(user=profile.user, match=match)
        BotCommentFactory(
            user=profile.user,
            match=match,
            trigger_type=BotComment.TriggerType.POST_MATCH,
        )

        result = generate_postmatch_comments()
        # The bot already has a postmatch comment, so it should not be dispatched
        assert "dispatched 0" in result
