"""Shared betting tasks (cross-league)."""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="vinosports.betting.tasks.expire_featured_parlays")
def expire_featured_parlays():
    """Mark expired featured parlays. Runs every 30 minutes."""
    from vinosports.betting.featured import FeaturedParlay

    now = timezone.now()
    updated = FeaturedParlay.objects.filter(
        status=FeaturedParlay.Status.ACTIVE,
        expires_at__lt=now,
    ).update(status=FeaturedParlay.Status.EXPIRED)

    if updated:
        logger.info("Expired %d featured parlays", updated)
