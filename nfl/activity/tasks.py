"""
Celery tasks for NFL activity feed cleanup.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def cleanup_old_activity_events():
    """Delete NFL activity events older than 7 days."""
    from .models import ActivityEvent

    cutoff = timezone.now() - timedelta(days=7)
    count, _ = ActivityEvent.objects.filter(created_at__lt=cutoff).delete()
    if count:
        logger.info("Cleaned up %d old NFL activity events", count)
