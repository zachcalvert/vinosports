"""Shared utilities for building bot prompt context."""

from vinosports.betting.models import BetStatus, UserBalance, UserStats


def build_user_stats_context(user, recent_bets_qs):
    """Return a one-line stats summary for use in bot prompts.

    recent_bets_qs: a queryset of BetSlip for this user (league-specific,
    unfiltered by status). This function applies its own filters.

    Returns an empty string if no data is available.
    """
    parts = []

    try:
        balance = UserBalance.objects.get(user=user).balance
        parts.append(f"Balance: {int(balance):,} credits")
    except UserBalance.DoesNotExist:
        pass

    try:
        stats = UserStats.objects.get(user=user)
        profit = stats.net_profit
        sign = "+" if profit >= 0 else ""
        parts.append(f"Net profit: {sign}{int(profit):,}")
        if stats.total_bets:
            parts.append(f"Overall: {stats.total_wins}W-{stats.total_losses}L")
        if stats.current_streak:
            direction = "W" if stats.current_streak > 0 else "L"
            parts.append(f"Streak: {abs(stats.current_streak)}{direction}")
    except UserStats.DoesNotExist:
        pass

    settled = list(
        recent_bets_qs.filter(status__in=[BetStatus.WON, BetStatus.LOST]).order_by(
            "-created_at"
        )[:10]
    )
    if settled:
        wins = sum(1 for b in settled if b.status == BetStatus.WON)
        losses = len(settled) - wins
        parts.append(f"Last {len(settled)}: {wins}W-{losses}L")

    return " | ".join(parts)
