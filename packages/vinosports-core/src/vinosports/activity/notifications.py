import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from vinosports.activity.models import Notification

logger = logging.getLogger(__name__)

NOTIFICATION_TTL = timedelta(hours=48)


def notify_comment_reply(*, parent_comment, reply_comment, match_or_game, league):
    """Create a notification for the parent comment's author.

    Args:
        parent_comment: The comment being replied to.
        reply_comment: The new reply.
        match_or_game: The Match or Game instance (for context).
        league: League string ("epl", "nba", "nfl").
    """
    recipient = parent_comment.user
    actor = reply_comment.user

    # Don't notify yourself
    if recipient == actor:
        return None

    # Don't notify bots
    if recipient.is_bot:
        return None

    subject = _build_match_subject(match_or_game, league)
    url = match_or_game.get_absolute_url()

    body = reply_comment.body[:200]
    if len(reply_comment.body) > 200:
        body += "..."

    actor_name = actor.display_name or "Someone"
    title = f"{actor_name} replied to your comment — {subject}"

    notification = Notification.objects.create(
        recipient=recipient,
        actor=actor,
        category=Notification.Category.REPLY,
        title=title,
        body=body,
        url=url,
        expires_at=timezone.now() + NOTIFICATION_TTL,
    )

    _push_notification_ws(notification)
    return notification


def notify_prop_settlement(*, bet_slip, prop):
    """Create a notification when a prop bet is settled (won, lost, or voided).

    Args:
        bet_slip: PropBetSlip instance (already settled).
        prop: PropBet instance.
    """
    recipient = bet_slip.user

    # Don't notify bots
    if recipient.is_bot:
        return None

    if bet_slip.status == "WON":
        title = f"You won your prop bet: {prop.title}"
        body = (
            f"Your {bet_slip.get_selection_display()} bet paid out "
            f"${bet_slip.payout:,.2f}."
        )
    elif bet_slip.status == "LOST":
        title = f"You lost your prop bet: {prop.title}"
        body = (
            f"Your {bet_slip.get_selection_display()} bet "
            f"(${bet_slip.stake:,.2f}) did not win."
        )
    else:  # VOID
        title = f"Prop bet cancelled: {prop.title}"
        body = f"Your ${bet_slip.stake:,.2f} stake has been refunded."

    notification = Notification.objects.create(
        recipient=recipient,
        category=Notification.Category.BET_SETTLEMENT,
        title=title,
        body=body,
        url="/prop-bets/",
        expires_at=timezone.now() + NOTIFICATION_TTL,
    )

    _push_notification_ws(notification)
    return notification


def _build_match_subject(match_or_game, league):
    """Build an abbreviated match/game string.

    Examples:
        EPL — ARS vs CHE — Mar 29
        NBA — LAL vs BOS — Apr 1
        NFL — KC vs BUF — Jan 12
    """
    league_upper = league.upper()

    if league == "epl":
        home = match_or_game.home_team.tla
        away = match_or_game.away_team.tla
        dt = match_or_game.kickoff
    elif league == "nba":
        home = match_or_game.home_team.abbreviation
        away = match_or_game.away_team.abbreviation
        dt = match_or_game.tip_off
    else:  # nfl
        home = match_or_game.home_team.abbreviation
        away = match_or_game.away_team.abbreviation
        dt = match_or_game.kickoff

    date_str = dt.strftime("%b %-d") if dt else ""
    return f"{league_upper} — {home} vs {away} — {date_str}"


def _push_notification_ws(notification):
    """Push notification event to recipient's WebSocket group."""
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_notifications_{notification.recipient.pk}",
            {
                "type": "inbox_notification",
                "count": _unread_count(notification.recipient),
            },
        )
    except Exception:
        logger.warning("Failed to push inbox notification via WebSocket", exc_info=True)


def _unread_count(user):
    """Return current unread notification count."""
    return Notification.objects.filter(
        recipient=user,
        is_read=False,
        expires_at__gt=timezone.now(),
    ).count()
