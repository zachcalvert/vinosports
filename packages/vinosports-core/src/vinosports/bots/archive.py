"""Automatic BotArchiveEntry creation for system events.

Provides signal handlers and utility functions that create archive entries
when bots receive awards, complete challenges, or have notable betting moments.
"""

import logging

from vinosports.bots.models import BotArchiveEntry, BotProfile, EntryType

logger = logging.getLogger(__name__)


def _get_bot_profile(user):
    """Return BotProfile if user is a bot, else None."""
    if not user.is_bot:
        return None
    try:
        return user.bot_profile
    except BotProfile.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Signal: RewardDistribution created → AWARD archive entry
# ---------------------------------------------------------------------------


def on_reward_distributed(sender, instance, created, **kwargs):
    """Create an AWARD archive entry when a bot receives a reward."""
    if not created:
        return

    profile = _get_bot_profile(instance.user)
    if not profile:
        return

    reward = instance.reward
    BotArchiveEntry.objects.create(
        bot_profile=profile,
        entry_type=EntryType.AWARD,
        summary=f"Won '{reward.name}' award ({reward.amount:,.2f} credits)",
        raw_source=f"RewardDistribution #{instance.pk}: {reward.name} — {reward.amount} credits",
    )
    logger.info(
        "Archive: %s received award '%s'", profile.user.display_name, reward.name
    )


# ---------------------------------------------------------------------------
# Signal: UserChallenge completed → CHALLENGE archive entry
# ---------------------------------------------------------------------------


def on_challenge_completed(sender, instance, **kwargs):
    """Create a CHALLENGE archive entry when a bot completes a challenge."""
    if instance.status != "COMPLETED":
        return

    profile = _get_bot_profile(instance.user)
    if not profile:
        return

    # Avoid duplicate entries — check if we already archived this challenge
    challenge = instance.challenge
    if BotArchiveEntry.objects.filter(
        bot_profile=profile,
        entry_type=EntryType.CHALLENGE,
        raw_source__contains=f"UserChallenge #{instance.pk}",
    ).exists():
        return

    BotArchiveEntry.objects.create(
        bot_profile=profile,
        entry_type=EntryType.CHALLENGE,
        summary=f"Completed the '{challenge.name}' challenge",
        raw_source=f"UserChallenge #{instance.pk}: {challenge.name}",
    )
    logger.info(
        "Archive: %s completed challenge '%s'",
        profile.user.display_name,
        challenge.name,
    )


# ---------------------------------------------------------------------------
# Utility: Betting highlight (called from league settlement tasks)
# ---------------------------------------------------------------------------


def maybe_create_betting_highlight(user, summary, league="", raw_source=""):
    """Create a BETTING_HIGHLIGHT archive entry if the user is a bot.

    Called from league-specific bet settlement code when a notable betting
    moment occurs (big win, devastating loss, long streak, parlay near-miss).

    Args:
        user: The User who placed the bet.
        summary: Human-readable description (e.g. "Won 5,000 credits on a 4-leg parlay").
        league: League slug (e.g. "epl", "nba").
        raw_source: Optional raw data for debugging.
    """
    profile = _get_bot_profile(user)
    if not profile:
        return None

    entry = BotArchiveEntry.objects.create(
        bot_profile=profile,
        entry_type=EntryType.BETTING_HIGHLIGHT,
        summary=summary,
        raw_source=raw_source,
        league=league,
    )
    logger.info(
        "Archive: %s betting highlight — %s", profile.user.display_name, summary
    )
    return entry
