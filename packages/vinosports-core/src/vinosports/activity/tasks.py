from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from vinosports.activity.models import Notification


@shared_task
def dismiss_expired_notifications():
    """Delete unread notifications past their expiry and old read notifications.

    Runs every hour via Celery beat.
    """
    now = timezone.now()

    # Unread past expiry
    expired = Notification.objects.filter(is_read=False, expires_at__lte=now)
    expired_count = expired.count()
    expired.delete()

    # Read notifications older than 30 days
    old_read = Notification.objects.filter(
        is_read=True,
        created_at__lte=now - timedelta(days=30),
    )
    old_count = old_read.count()
    old_read.delete()

    return f"Dismissed {expired_count} expired, {old_count} old read notifications"
