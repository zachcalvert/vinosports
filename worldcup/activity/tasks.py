import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def broadcast_next_activity_event():
    """Pop oldest queued World Cup ActivityEvent and broadcast to WebSocket group."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from django.utils import timezone

    from worldcup.activity.models import ActivityEvent

    event = (
        ActivityEvent.objects.filter(broadcast_at__isnull=True)
        .order_by("created_at")
        .first()
    )
    if not event:
        return

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "wc_site_activity",
        {
            "type": "activity_event",
            "html": f"<!-- activity: {event.message} -->",
        },
    )
    event.broadcast_at = timezone.now()
    event.save(update_fields=["broadcast_at"])


@shared_task
def cleanup_old_activity_events():
    """Delete World Cup activity events older than 7 days."""
    from datetime import timedelta

    from django.utils import timezone

    from worldcup.activity.models import ActivityEvent

    cutoff = timezone.now() - timedelta(days=7)
    deleted, _ = ActivityEvent.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        logger.info("Cleaned up %d old activity events", deleted)
