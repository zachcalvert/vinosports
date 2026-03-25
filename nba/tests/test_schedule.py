"""Tests for bot schedule window resolution."""

from datetime import date, datetime
from unittest.mock import MagicMock

from vinosports.bots.schedule import (
    DEFAULT_WINDOW,
    get_active_window,
    is_bot_active_now,
    roll_action,
)


class TestGetActiveWindow:
    """Tests for get_active_window() — no DB needed for most cases."""

    def _make_profile(self, template=None):
        profile = MagicMock()
        profile.schedule_template = template
        return profile

    def _make_template(self, windows, active_from=None, active_to=None):
        template = MagicMock()
        template.windows = windows
        template.active_from = active_from
        template.active_to = active_to
        return template

    def test_no_template_returns_default(self):
        profile = self._make_profile(template=None)
        result = get_active_window(profile)
        assert result == DEFAULT_WINDOW

    def test_no_template_returns_copy(self):
        """Mutating the returned dict should not affect DEFAULT_WINDOW."""
        profile = self._make_profile(template=None)
        result = get_active_window(profile)
        result["bet_probability"] = 0.0
        assert DEFAULT_WINDOW["bet_probability"] == 0.5

    def test_matching_window(self):
        # Monday at 10am
        now = datetime(2026, 3, 23, 10, 0)  # Monday
        window = {"days": [0], "hours": [10], "bet_probability": 0.9}
        template = self._make_template(windows=[window])
        profile = self._make_profile(template=template)
        result = get_active_window(profile, now)
        assert result["bet_probability"] == 0.9

    def test_no_matching_window(self):
        # Monday at 10am, but only Tuesday windows defined
        now = datetime(2026, 3, 23, 10, 0)  # Monday
        window = {"days": [1], "hours": [10]}  # Tuesday only
        template = self._make_template(windows=[window])
        profile = self._make_profile(template=template)
        result = get_active_window(profile, now)
        assert result is None

    def test_no_matching_hour(self):
        now = datetime(2026, 3, 23, 10, 0)  # Monday 10am
        window = {"days": [0], "hours": [14]}  # Right day, wrong hour
        template = self._make_template(windows=[window])
        profile = self._make_profile(template=template)
        assert get_active_window(profile, now) is None

    def test_active_from_future(self):
        now = datetime(2026, 3, 23, 10, 0)
        window = {"days": [0], "hours": [10]}
        template = self._make_template(windows=[window], active_from=date(2026, 4, 1))
        profile = self._make_profile(template=template)
        assert get_active_window(profile, now) is None

    def test_active_to_past(self):
        now = datetime(2026, 3, 23, 10, 0)
        window = {"days": [0], "hours": [10]}
        template = self._make_template(windows=[window], active_to=date(2026, 3, 1))
        profile = self._make_profile(template=template)
        assert get_active_window(profile, now) is None

    def test_active_within_date_range(self):
        now = datetime(2026, 3, 23, 10, 0)
        window = {"days": [0], "hours": [10], "bet_probability": 0.7}
        template = self._make_template(
            windows=[window],
            active_from=date(2026, 3, 1),
            active_to=date(2026, 4, 1),
        )
        profile = self._make_profile(template=template)
        result = get_active_window(profile, now)
        assert result is not None
        assert result["bet_probability"] == 0.7

    def test_multiple_windows_returns_first_match(self):
        now = datetime(2026, 3, 23, 10, 0)  # Monday 10am
        windows = [
            {"days": [0], "hours": [10], "bet_probability": 0.1},
            {"days": [0], "hours": [10], "bet_probability": 0.9},
        ]
        template = self._make_template(windows=windows)
        profile = self._make_profile(template=template)
        result = get_active_window(profile, now)
        assert result["bet_probability"] == 0.1


class TestIsBotActiveNow:
    def test_active_no_template(self):
        profile = MagicMock()
        profile.schedule_template = None
        assert is_bot_active_now(profile) is True

    def test_inactive_wrong_time(self):
        now = datetime(2026, 3, 23, 10, 0)
        template = MagicMock()
        template.windows = [{"days": [1], "hours": [14]}]
        template.active_from = None
        template.active_to = None
        profile = MagicMock()
        profile.schedule_template = template
        assert is_bot_active_now(profile, now) is False


class TestRollAction:
    def test_probability_zero_always_false(self):
        for _ in range(50):
            assert roll_action(0.0) is False

    def test_probability_one_always_true(self):
        for _ in range(50):
            assert roll_action(1.0) is True

    def test_probability_half_returns_bool(self):
        result = roll_action(0.5)
        assert isinstance(result, bool)
