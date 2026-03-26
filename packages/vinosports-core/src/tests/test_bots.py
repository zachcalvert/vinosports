"""Tests for vinosports.bots — schedule helpers and BotProfile."""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from vinosports.bots.models import StrategyType
from vinosports.bots.schedule import (
    DEFAULT_WINDOW,
    get_active_window,
    is_bot_active_now,
    roll_action,
)

from .factories import BotProfileFactory, ScheduleTemplateFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# get_active_window
# ---------------------------------------------------------------------------


class TestGetActiveWindow:
    def test_no_template_returns_default(self):
        bot = BotProfileFactory(schedule_template=None)
        window = get_active_window(bot)
        assert window == DEFAULT_WINDOW
        assert window is not DEFAULT_WINDOW

    def test_matching_window_returned(self):
        template = ScheduleTemplateFactory(
            windows=[
                {
                    "days": [0],
                    "hours": [10],
                    "bet_probability": 0.9,
                    "comment_probability": 0.7,
                    "max_bets": 3,
                    "max_comments": 2,
                }
            ]
        )
        bot = BotProfileFactory(schedule_template=template)
        now = datetime(2026, 3, 23, 10, 30)  # Monday
        window = get_active_window(bot, now=now)
        assert window is not None
        assert window["bet_probability"] == 0.9

    def test_no_matching_window_returns_none(self):
        template = ScheduleTemplateFactory(
            windows=[
                {
                    "days": [0],
                    "hours": [10],
                    "bet_probability": 0.9,
                    "comment_probability": 0.7,
                    "max_bets": 3,
                    "max_comments": 2,
                }
            ]
        )
        bot = BotProfileFactory(schedule_template=template)
        now = datetime(2026, 3, 24, 10, 30)  # Tuesday
        window = get_active_window(bot, now=now)
        assert window is None

    def test_before_active_from_returns_none(self):
        template = ScheduleTemplateFactory(
            active_from=date(2026, 6, 1),
            windows=[
                {
                    "days": [0, 1, 2, 3, 4, 5, 6],
                    "hours": list(range(24)),
                    "bet_probability": 0.5,
                    "comment_probability": 0.5,
                    "max_bets": 5,
                    "max_comments": 3,
                }
            ],
        )
        bot = BotProfileFactory(schedule_template=template)
        now = datetime(2026, 3, 23, 10, 0)
        assert get_active_window(bot, now=now) is None

    def test_after_active_to_returns_none(self):
        template = ScheduleTemplateFactory(
            active_to=date(2026, 1, 1),
            windows=[
                {
                    "days": [0, 1, 2, 3, 4, 5, 6],
                    "hours": list(range(24)),
                    "bet_probability": 0.5,
                    "comment_probability": 0.5,
                    "max_bets": 5,
                    "max_comments": 3,
                }
            ],
        )
        bot = BotProfileFactory(schedule_template=template)
        now = datetime(2026, 3, 23, 10, 0)
        assert get_active_window(bot, now=now) is None


# ---------------------------------------------------------------------------
# is_bot_active_now
# ---------------------------------------------------------------------------


class TestIsBotActiveNow:
    def test_true_when_no_template(self):
        bot = BotProfileFactory(schedule_template=None)
        assert is_bot_active_now(bot) is True

    def test_true_when_window_matches(self):
        template = ScheduleTemplateFactory()
        bot = BotProfileFactory(schedule_template=template)
        now = datetime(2026, 3, 23, 10, 0)
        assert is_bot_active_now(bot, now=now) is True

    def test_false_when_no_window_matches(self):
        template = ScheduleTemplateFactory(windows=[{"days": [6], "hours": [23]}])
        bot = BotProfileFactory(schedule_template=template)
        now = datetime(2026, 3, 23, 10, 0)
        assert is_bot_active_now(bot, now=now) is False


# ---------------------------------------------------------------------------
# roll_action
# ---------------------------------------------------------------------------


class TestRollAction:
    def test_always_true_at_1(self):
        assert all(roll_action(1.0) for _ in range(50))

    def test_always_false_at_0(self):
        assert not any(roll_action(0.0) for _ in range(50))

    @patch("vinosports.bots.schedule.random.random", return_value=0.3)
    def test_returns_true_when_roll_below_probability(self, _mock):
        assert roll_action(0.5) is True

    @patch("vinosports.bots.schedule.random.random", return_value=0.7)
    def test_returns_false_when_roll_above_probability(self, _mock):
        assert roll_action(0.5) is False


# ---------------------------------------------------------------------------
# BotProfile model
# ---------------------------------------------------------------------------


class TestBotProfile:
    def test_user_is_bot(self):
        bot = BotProfileFactory()
        assert bot.user.is_bot is True

    def test_strategy_types_exist(self):
        assert len(StrategyType.choices) >= 10

    def test_league_flags_defaults(self):
        bot = BotProfileFactory()
        assert bot.active_in_epl is True
        assert bot.active_in_nba is True
        assert bot.active_in_nfl is False
