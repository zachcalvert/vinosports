import math
from datetime import datetime

from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

register = template.Library()


def _coerce_datetime(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def _humanize_delta(delta_seconds):
    if delta_seconds < 10:
        return "just now"
    if delta_seconds < 60:
        return f"{delta_seconds} seconds ago"

    minutes = delta_seconds // 60
    if minutes == 1:
        return "1 minute ago"
    if minutes < 60:
        return f"{minutes} minutes ago"

    hours = minutes // 60
    if hours == 1:
        return "1 hour ago"
    if hours < 24:
        return f"{hours} hours ago"

    days = hours // 24
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


STATUS_BADGE_MAP = {
    "SCHEDULED": ("gray", "text-gray-400 bg-gray-400/10", ""),
    "TIMED": ("gray", "text-gray-400 bg-gray-400/10", ""),
    "IN_PLAY": ("live", "text-accent bg-accent/10", "LIVE"),
    "PAUSED": ("live", "text-accent bg-accent/10", "HT"),
    "FINISHED": ("finished", "text-muted bg-muted/10", "FT"),
    "POSTPONED": ("postponed", "text-warning bg-warning/10", "PP"),
    "CANCELLED": ("cancelled", "text-danger bg-danger/10", "CAN"),
}


@register.simple_tag
def status_badge(match):
    status = match.status
    _, classes, label = STATUS_BADGE_MAP.get(
        status, ("gray", "text-gray-400 bg-gray-400/10", status)
    )

    if status in ("SCHEDULED", "TIMED"):
        iso = match.kickoff.isoformat()
        local_kickoff = timezone.localtime(match.kickoff)
        label = f'<time datetime="{iso}" data-format="badge">{local_kickoff.strftime("%a %H:%M")}</time>'

    return mark_safe(
        f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium {classes}">'
        f"{label}</span>"
    )


@register.simple_tag
def score_display(match):
    if match.home_score is not None and match.away_score is not None:
        return mark_safe(
            f'<span class="text-2xl font-bold font-mono">{match.home_score} - {match.away_score}</span>'
        )
    return mark_safe('<span class="text-lg text-muted">vs</span>')


@register.filter
def format_odds(value):
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (ValueError, TypeError):
        return "-"


@register.filter
def ordinal(value):
    """Convert an integer to its ordinal string: 1 → '1st', 2 → '2nd', etc."""
    try:
        n = int(value)
    except (ValueError, TypeError):
        return value
    suffix = (
        "th" if 11 <= (n % 100) <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"


@register.filter
def get_item(dictionary, key):
    """Lookup a dictionary value by key in templates."""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def relative_time(value):
    dt = _coerce_datetime(value)
    if dt is None:
        return ""

    now = timezone.localtime(timezone.now())
    delta_seconds = int((now - dt).total_seconds())

    if delta_seconds < 0:
        future_seconds = abs(delta_seconds)
        if future_seconds < 60:
            return "in under a minute"
        future_minutes = math.ceil(future_seconds / 60)
        if future_minutes == 1:
            return "in 1 minute"
        if future_minutes < 60:
            return f"in {future_minutes} minutes"
        future_hours = math.ceil(future_minutes / 60)
        if future_hours == 1:
            return "in 1 hour"
        return f"in {future_hours} hours"

    return _humanize_delta(delta_seconds)
