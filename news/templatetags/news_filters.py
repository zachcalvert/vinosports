from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def smart_timesince(value):
    """Show 'X days ago' for dates over 24h old, detailed timesince for recent."""
    if not value:
        return ""
    now = timezone.now()
    delta = now - value
    days = delta.days
    if days >= 1:
        return f"{days} day{'s' if days != 1 else ''} ago"
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if hours >= 1:
        parts = f"{hours} hour{'s' if hours != 1 else ''}"
        if minutes:
            parts += f", {minutes} minute{'s' if minutes != 1 else ''}"
        return f"{parts} ago"
    if minutes >= 1:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    return "just now"
