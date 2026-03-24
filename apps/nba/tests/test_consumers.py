"""Tests for games/consumers.py (LiveUpdatesConsumer WebSocket)."""

from unittest.mock import MagicMock, patch

from games.consumers import LiveUpdatesConsumer


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

    @patch("games.consumers.async_to_sync" if False else "asgiref.sync.async_to_sync")
    def test_connect_dashboard_joins_live_scores_group(self, mock_a2s):
        mock_a2s.return_value = MagicMock()
        consumer = self._make_consumer("dashboard")
        consumer.connect()
        assert consumer.group_name == "live_scores"
        consumer.accept.assert_called_once()

    @patch("asgiref.sync.async_to_sync")
    def test_connect_game_scope_joins_game_group(self, mock_a2s):
        mock_a2s.return_value = MagicMock()
        consumer = self._make_consumer("abc123")
        consumer.connect()
        assert consumer.group_name == "game_abc123"
        consumer.accept.assert_called_once()

    @patch("asgiref.sync.async_to_sync")
    def test_disconnect_leaves_group(self, mock_a2s):
        mock_a2s.return_value = MagicMock()
        consumer = self._make_consumer("dashboard")
        consumer.connect()
        consumer.disconnect(close_code=1000)
        # group_discard called via async_to_sync
        assert mock_a2s.call_count == 2  # group_add + group_discard

    def test_score_update_sends_html(self):
        consumer = self._make_consumer("dashboard")
        consumer.score_update({"html": "<div>Score!</div>"})
        consumer.send.assert_called_once_with(text_data="<div>Score!</div>")

    def test_game_score_update_sends_html(self):
        consumer = self._make_consumer("game42")
        consumer.game_score_update({"html": "<div>Updated</div>"})
        consumer.send.assert_called_once_with(text_data="<div>Updated</div>")

    def test_score_update_empty_html(self):
        consumer = self._make_consumer("dashboard")
        consumer.score_update({})
        consumer.send.assert_called_once_with(text_data="")
