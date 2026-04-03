import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def broadcast_next_activity_event():
    """Pop the oldest queued event and broadcast it to all connected clients."""
    from .models import ActivityEvent

    with transaction.atomic():
        event = (
            ActivityEvent.objects.select_for_update(skip_locked=True)
            .filter(broadcast_at__isnull=True)
            .order_by("created_at")
            .first()
        )
        if not event:
            return

        event.broadcast_at = timezone.now()
        event.save(update_fields=["broadcast_at"])

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "site_activity",
        {
            "type": "activity_event",
            "message": event.message,
            "url": event.url,
            "icon": event.icon,
            "event_type": event.event_type,
        },
    )
    logger.debug("Broadcast activity event: %s", event.message)


@shared_task
def cleanup_old_activity_events():
    """Delete activity events older than 7 days."""
    from .models import ActivityEvent

    cutoff = timezone.now() - timedelta(days=7)
    count, _ = ActivityEvent.objects.filter(created_at__lt=cutoff).delete()
    if count:
        logger.info("Cleaned up %d old activity events", count)
