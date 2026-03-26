"""Tests for hub.templatetags.currency_tags."""

from hub.templatetags.currency_tags import (
    currency,
    currency_rounded,
    format_currency,
    get_currency_symbol,
)


class _FakeUser:
    def __init__(self, currency_code="USD"):
        self.currency = currency_code


class TestFormatCurrency:
    def test_usd(self):
        assert format_currency(1234.56, "USD") == "$1,234.56"

    def test_gbp(self):
        assert format_currency(1234.56, "GBP") == "£1,234.56"

    def test_eur(self):
        assert format_currency(1234.56, "EUR") == "€1,234.56"

    def test_rounded(self):
        assert format_currency(1234.56, "USD", decimals=0) == "$1,235"

    def test_unknown_currency_falls_back_to_usd(self):
        assert format_currency(100, "XYZ") == "$100.00"


class TestGetCurrencySymbol:
    def test_usd(self):
        assert get_currency_symbol(_FakeUser("USD")) == "$"

    def test_gbp(self):
        assert get_currency_symbol(_FakeUser("GBP")) == "£"

    def test_none_user(self):
        assert get_currency_symbol(None) == "$"


class TestCurrencyFilter:
    def test_formats_with_user_currency(self):
        assert currency(1000, _FakeUser("GBP")) == "£1,000.00"

    def test_none_value(self):
        assert currency(None, _FakeUser()) == ""

    def test_empty_string_value(self):
        assert currency("", _FakeUser()) == ""


class TestCurrencyRoundedFilter:
    def test_rounds_to_whole(self):
        assert currency_rounded(1234.56, _FakeUser("EUR")) == "€1,235"

    def test_none_value(self):
        assert currency_rounded(None, _FakeUser()) == ""
