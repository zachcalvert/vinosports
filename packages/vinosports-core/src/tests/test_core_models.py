"""Tests for vinosports.core.models — BaseModel and generate_short_id."""

from vinosports.core.models import generate_short_id


class TestGenerateShortId:
    def test_returns_8_chars(self):
        result = generate_short_id()
        assert len(result) == 8

    def test_alphanumeric_only(self):
        result = generate_short_id()
        assert result.isalnum()

    def test_unique_across_calls(self):
        ids = {generate_short_id() for _ in range(100)}
        assert len(ids) == 100
