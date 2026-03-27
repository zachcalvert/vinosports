"""Tests for activity/tasks.py — broadcast_next_activity_event, cleanup_old_activity_events."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

from epl.activity.models import ActivityEvent
from epl.activity.tasks import (
    broadcast_next_activity_event,
    cleanup_old_activity_events,
)

pytestmark = pytest.mark.django_db


class TestBroadcastNextActivityEvent:
    @patch("epl.activity.tasks.get_channel_layer")
    def test_broadcasts_oldest_queued_event(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        event = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="GOAL! Arsenal 1-0 Chelsea",
            url="/epl/match/ars-che-2025-09-20/",
            icon="soccer-ball",
        )

        broadcast_next_activity_event()

        event.refresh_from_db()
        assert event.broadcast_at is not None
        mock_layer.group_send.assert_called_once()

    @patch("epl.activity.tasks.get_channel_layer")
    def test_noop_when_no_queued_events(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        broadcast_next_activity_event()
        mock_layer.group_send.assert_not_called()

    @patch("epl.activity.tasks.get_channel_layer")
    def test_skips_already_broadcast_events(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="Already sent",
            broadcast_at=timezone.now(),
        )

        broadcast_next_activity_event()
        mock_layer.group_send.assert_not_called()

    @patch("epl.activity.tasks.get_channel_layer")
    def test_broadcasts_in_order(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        # Create two events — only the oldest should be broadcast
        ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.BOT_COMMENT,
            message="Second event",
        )
        first = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="First event",
        )
        # Force ordering: make the "first" event older
        ActivityEvent.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )

        broadcast_next_activity_event()

        first.refresh_from_db()
        assert first.broadcast_at is not None

        # The second event should still be queued
        second = ActivityEvent.objects.filter(
            event_type=ActivityEvent.EventType.BOT_COMMENT,
        ).first()
        assert second.broadcast_at is None


class TestCleanupOldActivityEvents:
    def test_deletes_old_events(self):
        # Old event
        old = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="Old event",
        )
        ActivityEvent.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=10),
        )

        # Recent event
        recent = ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="Recent event",
        )

        cleanup_old_activity_events()

        assert not ActivityEvent.objects.filter(pk=old.pk).exists()
        assert ActivityEvent.objects.filter(pk=recent.pk).exists()

    def test_no_old_events_noop(self):
        ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="Recent event",
        )

        cleanup_old_activity_events()
        assert ActivityEvent.objects.count() == 1
