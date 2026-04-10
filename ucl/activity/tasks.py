import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def cleanup_old_activity_events():
    """Delete UCL activity events older than 7 days."""
    from ucl.activity.models import ActivityEvent

    cutoff = timezone.now() - timedelta(days=7)
    deleted, _ = ActivityEvent.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        logger.info("Cleaned up %d old activity events", deleted)
