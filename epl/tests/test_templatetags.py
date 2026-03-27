"""Tests for matches/templatetags/match_tags.py."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from django.utils import timezone

from epl.matches.templatetags.match_tags import (
    _coerce_datetime,
    _humanize_delta,
    format_odds,
    get_item,
    ordinal,
    relative_time,
    score_display,
    status_badge,
)


class TestStatusBadge:
    def test_scheduled_match_shows_time(self):
        match = MagicMock()
        match.status = "SCHEDULED"
        match.kickoff = timezone.now() + timedelta(hours=2)
        result = status_badge(match)
        assert "time" in result
        assert "datetime" in result

    def test_timed_match_shows_time(self):
        match = MagicMock()
        match.status = "TIMED"
        match.kickoff = timezone.now() + timedelta(hours=1)
        result = status_badge(match)
        assert "time" in result

    def test_in_play_shows_live(self):
        match = MagicMock()
        match.status = "IN_PLAY"
        result = status_badge(match)
        assert "LIVE" in result

    def test_paused_shows_ht(self):
        match = MagicMock()
        match.status = "PAUSED"
        result = status_badge(match)
        assert "HT" in result

    def test_finished_shows_ft(self):
        match = MagicMock()
        match.status = "FINISHED"
        result = status_badge(match)
        assert "FT" in result

    def test_postponed_shows_pp(self):
        match = MagicMock()
        match.status = "POSTPONED"
        result = status_badge(match)
        assert "PP" in result

    def test_cancelled_shows_can(self):
        match = MagicMock()
        match.status = "CANCELLED"
        result = status_badge(match)
        assert "CAN" in result

    def test_unknown_status_uses_fallback(self):
        match = MagicMock()
        match.status = "UNKNOWN_STATUS"
        result = status_badge(match)
        assert "UNKNOWN_STATUS" in result


class TestScoreDisplay:
    def test_displays_score_for_finished_match(self):
        match = MagicMock()
        match.status = "FINISHED"
        match.home_score = 2
        match.away_score = 1
        result = score_display(match)
        assert "2 - 1" in result
        assert "font-bold" in result

    def test_displays_vs_for_scheduled_match(self):
        match = MagicMock()
        match.status = "SCHEDULED"
        match.home_score = None
        match.away_score = None
        result = score_display(match)
        assert "vs" in result

    def test_displays_vs_when_no_score(self):
        match = MagicMock()
        match.status = "IN_PLAY"
        match.home_score = None
        match.away_score = None
        result = score_display(match)
        assert "vs" in result

    def test_displays_score_for_in_play(self):
        match = MagicMock()
        match.status = "IN_PLAY"
        match.home_score = 1
        match.away_score = 0
        result = score_display(match)
        assert "1 - 0" in result


class TestFormatOdds:
    def test_formats_decimal_value(self):
        assert format_odds(Decimal("2.10")) == "2.10"

    def test_formats_float(self):
        assert format_odds(2.5) == "2.50"

    def test_none_returns_dash(self):
        assert format_odds(None) == "-"

    def test_non_numeric_returns_dash(self):
        assert format_odds("abc") == "-"

    def test_zero_formats(self):
        assert format_odds(0) == "0.00"


class TestOrdinal:
    def test_first(self):
        assert ordinal(1) == "1st"

    def test_second(self):
        assert ordinal(2) == "2nd"

    def test_third(self):
        assert ordinal(3) == "3rd"

    def test_fourth(self):
        assert ordinal(4) == "4th"

    def test_eleventh(self):
        assert ordinal(11) == "11th"

    def test_twelfth(self):
        assert ordinal(12) == "12th"

    def test_thirteenth(self):
        assert ordinal(13) == "13th"

    def test_twenty_first(self):
        assert ordinal(21) == "21st"

    def test_twenty_second(self):
        assert ordinal(22) == "22nd"

    def test_hundred_eleventh(self):
        assert ordinal(111) == "111th"

    def test_non_numeric_returns_value(self):
        assert ordinal("abc") == "abc"

    def test_none_returns_none(self):
        assert ordinal(None) is None

    def test_string_number(self):
        assert ordinal("5") == "5th"


class TestGetItem:
    def test_gets_key(self):
        assert get_item({"a": 1}, "a") == 1

    def test_missing_key_returns_none(self):
        assert get_item({"a": 1}, "b") is None

    def test_none_dict_returns_none(self):
        assert get_item(None, "a") is None


class TestCoerceDatetime:
    def test_datetime_object(self):
        dt = timezone.now()
        result = _coerce_datetime(dt)
        assert result is not None

    def test_iso_string(self):
        result = _coerce_datetime("2025-09-20T15:00:00+00:00")
        assert result is not None

    def test_iso_string_with_z(self):
        result = _coerce_datetime("2025-09-20T15:00:00Z")
        assert result is not None

    def test_invalid_string_returns_none(self):
        assert _coerce_datetime("not-a-date") is None

    def test_non_string_non_datetime_returns_none(self):
        assert _coerce_datetime(12345) is None

    def test_naive_datetime_made_aware(self):
        naive = datetime(2025, 9, 20, 15, 0)
        result = _coerce_datetime(naive)
        assert result is not None
        assert timezone.is_aware(result)


class TestHumanizeDelta:
    def test_just_now(self):
        assert _humanize_delta(5) == "just now"

    def test_seconds(self):
        assert _humanize_delta(30) == "30 seconds ago"

    def test_one_minute(self):
        assert _humanize_delta(60) == "1 minute ago"

    def test_minutes(self):
        assert _humanize_delta(300) == "5 minutes ago"

    def test_one_hour(self):
        assert _humanize_delta(3600) == "1 hour ago"

    def test_hours(self):
        assert _humanize_delta(7200) == "2 hours ago"

    def test_one_day(self):
        assert _humanize_delta(86400) == "1 day ago"

    def test_days(self):
        assert _humanize_delta(172800) == "2 days ago"


class TestRelativeTime:
    def test_past_time(self):
        past = timezone.now() - timedelta(hours=2)
        result = relative_time(past)
        assert "hours ago" in result

    def test_future_time(self):
        future = timezone.now() + timedelta(hours=2)
        result = relative_time(future)
        assert result.startswith("in ")

    def test_future_under_a_minute(self):
        future = timezone.now() + timedelta(seconds=30)
        result = relative_time(future)
        assert "under a minute" in result

    def test_future_one_minute(self):
        future = timezone.now() + timedelta(seconds=61)
        result = relative_time(future)
        assert "minute" in result

    def test_future_one_hour(self):
        future = timezone.now() + timedelta(minutes=61)
        result = relative_time(future)
        assert "hour" in result

    def test_none_value_returns_empty(self):
        assert relative_time(None) == ""

    def test_invalid_value_returns_empty(self):
        assert relative_time("not-a-date") == ""

    def test_iso_string_input(self):
        past = (timezone.now() - timedelta(minutes=5)).isoformat()
        result = relative_time(past)
        assert "minutes ago" in result
