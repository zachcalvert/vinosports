"""Tests for hub/promo.py — promo code evaluation via Claude API."""

from unittest.mock import MagicMock, patch

from hub.promo import evaluate_promo_code


class TestEvaluatePromoCode:
    @patch("hub.promo.settings")
    def test_returns_zero_without_api_key(self, mock_settings):
        mock_settings.ANTHROPIC_API_KEY = ""
        result = evaluate_promo_code("TESTCODE")
        assert result == 0

    @patch("hub.promo.settings")
    def test_returns_zero_when_api_key_none(self, mock_settings):
        mock_settings.ANTHROPIC_API_KEY = None
        result = evaluate_promo_code("TESTCODE")
        assert result == 0

    @patch("hub.promo.anthropic")
    @patch("hub.promo.settings")
    def test_returns_parsed_score(self, mock_settings, mock_anthropic):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="75000")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )

        result = evaluate_promo_code("VinoVeritasVictory")
        assert result == 75000

    @patch("hub.promo.anthropic")
    @patch("hub.promo.settings")
    def test_clamps_to_minimum_25000(self, mock_settings, mock_anthropic):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="50")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )

        result = evaluate_promo_code("boring")
        assert result == 25000

    @patch("hub.promo.anthropic")
    @patch("hub.promo.settings")
    def test_clamps_to_maximum_100000(self, mock_settings, mock_anthropic):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="999999")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )

        result = evaluate_promo_code("amazing")
        assert result == 100000

    @patch("hub.promo.anthropic")
    @patch("hub.promo.settings")
    def test_returns_zero_on_unparseable_response(self, mock_settings, mock_anthropic):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="no number here")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )

        result = evaluate_promo_code("test")
        assert result == 0

    @patch("hub.promo.anthropic")
    @patch("hub.promo.settings")
    def test_returns_zero_on_api_exception(self, mock_settings, mock_anthropic):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_anthropic.Anthropic.return_value.messages.create.side_effect = Exception(
            "API error"
        )

        result = evaluate_promo_code("test")
        assert result == 0

    @patch("hub.promo.anthropic")
    @patch("hub.promo.settings")
    def test_extracts_number_from_mixed_text(self, mock_settings, mock_anthropic):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="I rate this 60000 points")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )

        result = evaluate_promo_code("test")
        assert result == 60000
