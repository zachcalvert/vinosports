"""Tests for activity — inline broadcast via queue_activity_event, cleanup_old_activity_events."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

from nba.activity.tasks import cleanup_old_activity_events
from nba.tests.factories import ActivityEventFactory


@pytest.mark.django_db
class TestQueueActivityEvent:
    @patch("nba.activity.services.get_channel_layer")
    def test_creates_event_and_broadcasts(self, mock_get_layer):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        from nba.activity.services import queue_activity_event

        event = queue_activity_event(
            event_type="score_change",
            message="Lakers 110, Celtics 105 — FINAL",
            url="/nba/game/lal-bos/",
            icon="basketball",
        )

        assert event.pk is not None
        assert event.broadcast_at is not None
        mock_layer.group_send.assert_called_once()

    @patch("nba.activity.services.get_channel_layer")
    def test_event_persists_on_broadcast_failure(self, mock_get_layer):
        mock_get_layer.side_effect = Exception("Redis down")

        from nba.activity.services import queue_activity_event

        event = queue_activity_event(
            event_type="score_change",
            message="Lakers 110, Celtics 105 — FINAL",
        )

        assert event.pk is not None
        assert event.broadcast_at is not None


@pytest.mark.django_db
class TestCleanupOldActivityEvents:
    def test_deletes_events_older_than_7_days(self):
        """Events older than 7 days should be deleted."""
        old_event = ActivityEventFactory()
        from nba.activity.models import ActivityEvent

        ActivityEvent.objects.filter(pk=old_event.pk).update(
            created_at=timezone.now() - timedelta(days=8)
        )

        cleanup_old_activity_events()

        assert not ActivityEvent.objects.filter(pk=old_event.pk).exists()

    def test_keeps_recent_events(self):
        """Events newer than 7 days should not be deleted."""
        recent_event = ActivityEventFactory()

        cleanup_old_activity_events()

        from nba.activity.models import ActivityEvent

        assert ActivityEvent.objects.filter(pk=recent_event.pk).exists()

    def test_keeps_events_exactly_7_days_old(self):
        """Events exactly 7 days old (not past the cutoff) should not be deleted."""
        from nba.activity.models import ActivityEvent

        event = ActivityEventFactory()
        ActivityEvent.objects.filter(pk=event.pk).update(
            created_at=timezone.now() - timedelta(days=6, hours=23)
        )

        cleanup_old_activity_events()

        assert ActivityEvent.objects.filter(pk=event.pk).exists()

    def test_no_events_does_not_raise(self):
        """Task should not raise when there are no events."""
        cleanup_old_activity_events()  # Should complete without error
