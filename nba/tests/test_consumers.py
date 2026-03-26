"""Tests for games/consumers.py (LiveUpdatesConsumer WebSocket)."""

from unittest.mock import MagicMock, patch

import pytest

from nba.games.consumers import LiveUpdatesConsumer


class TestLiveUpdatesConsumer:
    """Test consumer logic by calling methods directly with mocked internals."""

    def _make_consumer(self, scope_param):
        consumer = LiveUpdatesConsumer()
        consumer.scope = {
            "url_route": {"kwargs": {"scope": scope_param}},
        }
        consumer.channel_name = "test-channel-123"
        consumer.channel_layer = MagicMock()
        consumer.accept = MagicMock()
        consumer.send = MagicMock()
        return consumer

    @patch("nba.games.consumers.async_to_sync")
    def test_connect_dashboard_joins_live_scores_group(self, mock_a2s):
        mock_a2s.return_value = MagicMock()
        consumer = self._make_consumer("dashboard")
        consumer.connect()
        assert consumer.group_name == "live_scores"
        consumer.accept.assert_called_once()

    @patch("nba.games.consumers.async_to_sync")
    def test_connect_game_scope_joins_game_group(self, mock_a2s):
        mock_a2s.return_value = MagicMock()
        consumer = self._make_consumer("abc123")
        consumer.connect()
        assert consumer.group_name == "game_abc123"
        consumer.accept.assert_called_once()

    @patch("nba.games.consumers.async_to_sync")
    def test_disconnect_leaves_group(self, mock_a2s):
        mock_a2s.return_value = MagicMock()
        consumer = self._make_consumer("dashboard")
        consumer.connect()
        consumer.disconnect(close_code=1000)
        # group_discard called via async_to_sync
        assert mock_a2s.call_count == 2  # group_add + group_discard

    @pytest.mark.django_db
    def test_score_update_no_game_does_not_send(self):
        consumer = self._make_consumer("dashboard")
        consumer.score_update({"game_pk": 999999})
        consumer.send.assert_not_called()

    @pytest.mark.django_db
    def test_game_score_update_no_game_does_not_send(self):
        consumer = self._make_consumer("game42")
        consumer.game_score_update({"game_pk": 999999})
        consumer.send.assert_not_called()

    @pytest.mark.django_db
    def test_score_update_no_game_pk_does_not_send(self):
        consumer = self._make_consumer("dashboard")
        consumer.score_update({})
        consumer.send.assert_not_called()
