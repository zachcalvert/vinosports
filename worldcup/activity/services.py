"""Activity event queueing for World Cup."""

from worldcup.activity.models import ActivityEvent


def queue_activity_event(event_type, message, url="", icon=""):
    """Create an ActivityEvent to be broadcast on the next tick."""
    return ActivityEvent.objects.create(
        event_type=event_type,
        message=message,
        url=url,
        icon=icon,
    )
