from .models import ActivityEvent


def queue_activity_event(event_type, message, url="", icon="lightning"):
    """Queue an activity event for broadcast via the next periodic tick."""
    return ActivityEvent.objects.create(
        event_type=event_type,
        message=message,
        url=url,
        icon=icon,
    )
