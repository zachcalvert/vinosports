"""Tests for activity — inline broadcast via queue_activity_event, cleanup_old_activity_events."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

from epl.activity.models import ActivityEvent
from epl.activity.tasks import cleanup_old_activity_events

pytestmark = pytest.mark.django_db


class TestQueueActivityEvent:
    @patch("epl.activity.services.get_channel_layer")
    def test_creates_event_and_broadcasts(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        from epl.activity.services import queue_activity_event

        event = queue_activity_event(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="GOAL! Arsenal 1-0 Chelsea",
            url="/epl/match/ars-che-2025-09-20/",
            icon="soccer-ball",
        )

        assert event.broadcast_at is not None
        mock_layer.group_send.assert_called_once()

    @patch("epl.activity.services.get_channel_layer")
    def test_event_persists_on_broadcast_failure(self, mock_get_layer):
        mock_get_layer.side_effect = Exception("Redis down")

        from epl.activity.services import queue_activity_event

        event = queue_activity_event(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message="GOAL! Arsenal 1-0 Chelsea",
        )

        assert event.pk is not None
        assert event.broadcast_at is not None


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
