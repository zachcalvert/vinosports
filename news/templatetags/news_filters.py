from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def smart_timesince(value):
    """Show 'X minutes ago' only if published within the last 60 minutes."""
    if not value:
        return ""
    now = timezone.now()
    delta = now - value
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes >= 60:
        return ""
    if total_minutes >= 1:
        return f"{total_minutes} minute{'s' if total_minutes != 1 else ''} ago"
    return "just now"
