"""World Cup match template tags."""

from django import template
from django.utils import timezone

register = template.Library()


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
