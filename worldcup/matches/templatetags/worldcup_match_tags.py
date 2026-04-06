"""World Cup match template tags."""

import math
from datetime import datetime

from django import template
from django.utils import timezone

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


@register.inclusion_tag("worldcup_matches/partials/status_badge.html")
def wc_status_badge(match):
    return {"match": match}


@register.inclusion_tag("worldcup_matches/partials/score_display.html")
def wc_score_display(match):
    return {"match": match}


@register.filter
def wc_result_label(match, team):
    """Return 'W', 'D', or 'L' from the perspective of `team`."""
    if match.home_score is None or match.away_score is None:
        return ""
    winner = match.winner
    if winner is None:
        return "D"
    return "W" if winner == team else "L"


@register.simple_tag(takes_context=True)
def wc_is_today(context, match):
    """True if the match kicks off today (server-side date)."""
    today = timezone.now().date()
    return match.kickoff.date() == today


@register.filter
def get_item(dictionary, key):
    """Dict lookup by variable key: {{ my_dict|get_item:key_var }}"""
    return dictionary.get(key)
