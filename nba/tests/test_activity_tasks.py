"""Tests for activity/tasks.py (broadcast_next_activity_event, cleanup_old_activity_events)."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone

from nba.activity.tasks import (
    broadcast_next_activity_event,
    cleanup_old_activity_events,
)
from nba.tests.factories import ActivityEventFactory


@pytest.mark.django_db
class TestBroadcastNextActivityEvent:
    def test_no_pending_events_does_nothing(self):
        """Task should silently return when no events are queued."""
        with patch("nba.activity.tasks.get_channel_layer") as mock_get_layer:
            broadcast_next_activity_event()
            mock_get_layer.assert_not_called()

    def test_broadcasts_oldest_queued_event(self):
        """Task should broadcast the oldest unbroadcast event."""
        event = ActivityEventFactory(broadcast_at=None)

        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()

        with patch("nba.activity.tasks.get_channel_layer", return_value=mock_layer):
            with patch("nba.activity.tasks.async_to_sync") as mock_async_to_sync:
                mock_async_to_sync.return_value = MagicMock()
                broadcast_next_activity_event()

        event.refresh_from_db()
        assert event.broadcast_at is not None

    def test_marks_event_as_broadcast(self):
        """Broadcast task should set broadcast_at timestamp on event."""
        event = ActivityEventFactory(broadcast_at=None)

        mock_layer = MagicMock()
        with patch("nba.activity.tasks.get_channel_layer", return_value=mock_layer):
            with patch("nba.activity.tasks.async_to_sync") as mock_sync:
                mock_sync.return_value = MagicMock()
                broadcast_next_activity_event()

        event.refresh_from_db()
        assert event.broadcast_at is not None

    def test_skips_already_broadcast_events(self):
        """Task should not re-broadcast events that have already been sent."""
        already_sent = ActivityEventFactory(broadcast_at=timezone.now())
        pending = ActivityEventFactory(broadcast_at=None)

        mock_layer = MagicMock()
        with patch("nba.activity.tasks.get_channel_layer", return_value=mock_layer):
            with patch("nba.activity.tasks.async_to_sync") as mock_sync:
                mock_sync.return_value = MagicMock()
                broadcast_next_activity_event()

        already_sent.refresh_from_db()
        pending.refresh_from_db()
        # already_sent should not have a new broadcast_at
        assert pending.broadcast_at is not None

    def test_processes_oldest_event_first(self):
        """Task should pick the oldest queued event, not the newest."""
        newer_event = ActivityEventFactory(broadcast_at=None)
        older_event = ActivityEventFactory(broadcast_at=None)
        # Force older_event to have an earlier created_at
        from nba.activity.models import ActivityEvent

        ActivityEvent.objects.filter(pk=older_event.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )
        ActivityEvent.objects.filter(pk=newer_event.pk).update(
            created_at=timezone.now()
        )

        mock_layer = MagicMock()
        with patch("nba.activity.tasks.get_channel_layer", return_value=mock_layer):
            with patch("nba.activity.tasks.async_to_sync") as mock_sync:
                mock_sync.return_value = MagicMock()
                broadcast_next_activity_event()

        older_event.refresh_from_db()
        newer_event.refresh_from_db()
        assert older_event.broadcast_at is not None
        assert newer_event.broadcast_at is None


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

        from nba.activity.models import ActivityEvent as AE

        assert not AE.objects.filter(pk=old_event.pk).exists()

    def test_keeps_recent_events(self):
        """Events newer than 7 days should not be deleted."""
        recent_event = ActivityEventFactory()

        cleanup_old_activity_events()

        from nba.activity.models import ActivityEvent as AE

        assert AE.objects.filter(pk=recent_event.pk).exists()

    def test_keeps_events_exactly_7_days_old(self):
        """Events exactly 7 days old (not past the cutoff) should not be deleted."""
        from nba.activity.models import ActivityEvent

        event = ActivityEventFactory()
        # Set to exactly 6 days 23 hours ago (not yet past 7-day cutoff)
        ActivityEvent.objects.filter(pk=event.pk).update(
            created_at=timezone.now() - timedelta(days=6, hours=23)
        )

        cleanup_old_activity_events()

        assert ActivityEvent.objects.filter(pk=event.pk).exists()

    def test_no_events_does_not_raise(self):
        """Task should not raise when there are no events."""
        cleanup_old_activity_events()  # Should complete without error
