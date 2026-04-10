"""Activity event queueing for World Cup."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from worldcup.activity.models import ActivityEvent

logger = logging.getLogger(__name__)


def queue_activity_event(event_type, message, url="", icon=""):
    """Create an activity event and broadcast it immediately via WebSocket."""
    event = ActivityEvent.objects.create(
        event_type=event_type,
        message=message,
        url=url,
        icon=icon,
        broadcast_at=timezone.now(),
    )
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "wc_site_activity",
            {
                "type": "activity_event",
                "message": event.message,
                "url": event.url,
                "icon": event.icon,
                "event_type": event.event_type,
            },
        )
    except Exception:
        logger.warning("Failed to broadcast activity event: %s", message)
    return event
