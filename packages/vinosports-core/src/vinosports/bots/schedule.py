"""Schedule resolution helpers for bot activity windows.

Each bot can have a ScheduleTemplate with activity windows that define
when it's "online" and the probability of betting/commenting per hourly tick.

These helpers are sport-agnostic — league tasks import them directly.
"""

import random
from datetime import datetime

from django.utils import timezone

# Default window used for bots without a schedule template (always eligible).
DEFAULT_WINDOW = {
    "days": [0, 1, 2, 3, 4, 5, 6],
    "hours": list(range(24)),
    "bet_probability": 0.5,
    "comment_probability": 0.5,
    "max_bets": 5,
    "max_comments": 3,
}


def get_active_window(bot_profile, now=None):
    """Return the matching activity window for the current time, or None.

    If the bot has no schedule_template, returns DEFAULT_WINDOW (always-on).
    If the bot has a template but no window matches, returns None (inactive).
    """
    template = bot_profile.schedule_template
    if template is None:
        return dict(DEFAULT_WINDOW)

    if now is None:
        now = timezone.localtime()

    # Check date range
    today = now.date() if isinstance(now, datetime) else now
    if template.active_from and today < template.active_from:
        return None
    if template.active_to and today > template.active_to:
        return None

    day_of_week = today.weekday()  # 0=Mon..6=Sun
    hour = now.hour if isinstance(now, datetime) else 0

    for window in template.windows:
        if day_of_week in window.get("days", []) and hour in window.get("hours", []):
            return window

    return None


def is_bot_active_now(bot_profile, now=None):
    """Check whether a bot should be active at the given time.

    Returns True if:
    - Bot has no template (always-on fallback), OR
    - Bot's template has a window matching the current day+hour and the
      date range (active_from/active_to) is satisfied.
    """
    return get_active_window(bot_profile, now) is not None


def roll_action(probability):
    """Return True with the given probability (0.0 to 1.0)."""
    return random.random() < probability
