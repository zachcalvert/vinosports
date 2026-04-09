"""Tests for NBA template tags: currency_tags, dashboard_tags, game_tags."""

from decimal import Decimal

from hub.templatetags.currency_tags import (
    currency,
    currency_rounded,
    currency_symbol,
    format_currency,
    negate,
)
from nba.games.templatetags.nba_game_tags import get_item as games_get_item
from nba.website.templatetags.dashboard_tags import get_item

# ---------------------------------------------------------------------------
# nba/website/templatetags/dashboard_tags.py — get_item
# ---------------------------------------------------------------------------


class TestDashboardGetItem:
    def test_returns_value_for_existing_key(self):
        assert get_item({"a": 1}, "a") == 1

    def test_returns_none_for_missing_key(self):
        assert get_item({"a": 1}, "b") is None

    def test_returns_none_for_none_dict(self):
        assert get_item(None, "key") is None


# ---------------------------------------------------------------------------
# nba/games/templatetags/game_tags.py — get_item
# ---------------------------------------------------------------------------


class TestGamesGetItem:
    def test_returns_value_for_existing_key(self):
        assert games_get_item({"x": 99}, "x") == 99

    def test_returns_none_for_non_dict(self):
        assert games_get_item("not a dict", "key") is None

    def test_returns_none_for_missing_key(self):
        assert games_get_item({"a": 1}, "b") is None


# ---------------------------------------------------------------------------
# nba/website/templatetags/currency_tags.py
# ---------------------------------------------------------------------------


class TestFormatCurrency:
    def test_default_usd_with_decimals(self):
        assert format_currency(1234.5) == "$1,234.50"

    def test_usd_rounded(self):
        assert format_currency(1234.6, decimals=0) == "$1,235"

    def test_gbp_symbol(self):
        result = format_currency(100, currency_code="GBP")
        assert result.startswith("£")

    def test_eur_symbol(self):
        result = format_currency(100, currency_code="EUR")
        assert result.startswith("€")

    def test_unknown_currency_falls_back_to_usd(self):
        result = format_currency(100, currency_code="XYZ")
        assert result.startswith("$")


class TestCurrencyFilter:
    def _make_user(self, currency_code="USD"):
        user = type("User", (), {"currency": currency_code})()
        return user

    def test_none_value_returns_empty_string(self):
        assert currency(None, self._make_user()) == ""

    def test_empty_string_returns_empty_string(self):
        assert currency("", self._make_user()) == ""

    def test_formats_decimal_value(self):
        result = currency(Decimal("100.50"), self._make_user("USD"))
        assert result == "$100.50"

    def test_respects_user_currency(self):
        result = currency(Decimal("100.00"), self._make_user("GBP"))
        assert "£" in result

    def test_none_user_defaults_to_usd(self):
        result = currency(Decimal("50.00"), None)
        assert result.startswith("$")


class TestCurrencyRoundedFilter:
    def _make_user(self, currency_code="USD"):
        return type("User", (), {"currency": currency_code})()

    def test_none_value_returns_empty_string(self):
        assert currency_rounded(None, self._make_user()) == ""

    def test_empty_string_returns_empty_string(self):
        assert currency_rounded("", self._make_user()) == ""

    def test_rounds_to_whole_unit(self):
        result = currency_rounded(Decimal("100.75"), self._make_user("USD"))
        assert result == "$101"

    def test_respects_user_currency(self):
        result = currency_rounded(Decimal("200.00"), self._make_user("GBP"))
        assert "£" in result


class TestCurrencySymbolTag:
    def _make_user(self, currency_code="USD"):
        return type("User", (), {"currency": currency_code})()

    def test_usd_symbol(self):
        assert currency_symbol(self._make_user("USD")) == "$"

    def test_gbp_symbol(self):
        assert currency_symbol(self._make_user("GBP")) == "£"

    def test_eur_symbol(self):
        assert currency_symbol(self._make_user("EUR")) == "€"

    def test_none_user_returns_usd_symbol(self):
        assert currency_symbol(None) == "$"


class TestNegateFilter:
    def test_negates_positive_integer(self):
        assert negate(5) == -5

    def test_negates_negative_integer(self):
        assert negate(-10) == 10

    def test_negates_decimal(self):
        assert negate(Decimal("3.14")) == Decimal("-3.14")

    def test_returns_value_on_type_error(self):
        assert negate("not a number") == "not a number"
