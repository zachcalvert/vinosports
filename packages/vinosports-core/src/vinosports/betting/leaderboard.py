import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import models
from django.db.models import Case, F, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Cast
from django.utils import timezone

from vinosports.betting.models import BalanceTransaction, UserBalance, UserStats

logger = logging.getLogger(__name__)


def mask_email(email):
    local_part, _, domain = email.partition("@")
    if not domain:
        return email

    visible_count = min(2, len(local_part))
    visible_prefix = local_part[:visible_count]
    masked_suffix = "*" * max(len(local_part) - visible_count, 1)
    return f"{visible_prefix}{masked_suffix}@{domain}"


def get_public_identity(user):
    if getattr(user, "display_name", None):
        return user.display_name
    return mask_email(user.email)


BOARD_TYPES = ("balance", "profit", "win_rate", "streak")
WIN_RATE_MIN_BETS = 10
LEADERBOARD_CACHE_TTL = 30  # seconds


def get_leaderboard_entries(limit=10, board_type="balance"):
    cache_key = f"leaderboard:{board_type}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if board_type == "balance":
        result = _get_balance_leaderboard(limit)
    elif board_type == "profit":
        result = _get_profit_leaderboard(limit)
    elif board_type == "win_rate":
        result = _get_win_rate_leaderboard(limit)
    elif board_type == "streak":
        result = _get_streak_leaderboard(limit)
    else:
        result = _get_balance_leaderboard(limit)

    cache.set(cache_key, result, LEADERBOARD_CACHE_TTL)
    return result


def _annotate_identity(entries):
    for entry in entries:
        entry.display_identity = get_public_identity(entry.user)
    return entries


def _balance_at_cutoff_subquery(cutoff):
    """Subquery: last balance_after before the cutoff for each user."""
    return Subquery(
        BalanceTransaction.objects.filter(
            user=OuterRef("user"),
            created_at__lte=cutoff,
        )
        .order_by("-created_at")
        .values("balance_after")[:1]
    )


def _annotate_balance_changes(qs):
    """Annotate a UserBalance queryset with 24h and 7d balance deltas."""
    now = timezone.now()
    return qs.annotate(
        balance_24h_ago=_balance_at_cutoff_subquery(now - timedelta(hours=24)),
        balance_7d_ago=_balance_at_cutoff_subquery(now - timedelta(days=7)),
    )


def _compute_balance_deltas(entries):
    """Set change_24h and change_7d on each entry from annotations."""
    for entry in entries:
        b24 = getattr(entry, "balance_24h_ago", None)
        b7 = getattr(entry, "balance_7d_ago", None)
        entry.change_24h = entry.balance - b24 if b24 is not None else None
        entry.change_7d = entry.balance - b7 if b7 is not None else None
    return entries


def _get_balance_leaderboard(limit):
    qs = (
        UserBalance.objects.select_related("user")
        .filter(user__is_superuser=False, user__is_active=True)
        .order_by("-balance", "user_id")
    )
    qs = _annotate_balance_changes(qs)
    if limit is not None:
        qs = qs[:limit]
    entries = _annotate_identity(list(qs))
    return _compute_balance_deltas(entries)


def _get_profit_leaderboard(limit):
    qs = (
        UserStats.objects.select_related("user")
        .filter(total_bets__gt=0, user__is_superuser=False, user__is_active=True)
        .order_by("-net_profit", "user_id")
    )
    if limit is not None:
        qs = qs[:limit]
    return _annotate_identity(list(qs))


def _get_win_rate_leaderboard(limit):
    qs = (
        UserStats.objects.select_related("user")
        .filter(
            total_bets__gte=WIN_RATE_MIN_BETS,
            user__is_superuser=False,
            user__is_active=True,
        )
        .annotate(
            _win_rate=Case(
                When(total_bets=0, then=Value(0.0)),
                default=Cast(F("total_wins"), models.FloatField())
                / Cast(F("total_bets"), models.FloatField())
                * 100.0,
            )
        )
        .order_by("-_win_rate", "-total_bets", "user_id")
    )
    if limit is not None:
        qs = qs[:limit]
    return _annotate_identity(list(qs))


def _get_streak_leaderboard(limit):
    qs = (
        UserStats.objects.select_related("user")
        .filter(total_bets__gt=0, user__is_superuser=False, user__is_active=True)
        .order_by("-best_streak", "-current_streak", "user_id")
    )
    if limit is not None:
        qs = qs[:limit]
    return _annotate_identity(list(qs))


def get_user_balance_with_deltas(user):
    """Return the user's UserBalance with change_24h and change_7d, or None."""
    try:
        ub = _annotate_balance_changes(UserBalance.objects.filter(user=user)).get()
    except UserBalance.DoesNotExist:
        return None
    _compute_balance_deltas([ub])
    return ub


def get_user_rank(user, leaderboard=None, board_type="balance"):
    if not getattr(user, "is_authenticated", False):
        return None
    if user.is_superuser:
        return None

    leaderboard_user_ids = {entry.user_id for entry in leaderboard or []}
    if user.id in leaderboard_user_ids:
        return None

    if board_type == "balance":
        return _get_balance_rank(user)
    elif board_type in ("profit", "win_rate", "streak"):
        return _get_stats_rank(user, board_type)
    return _get_balance_rank(user)


def _get_balance_rank(user):
    try:
        qs = _annotate_balance_changes(UserBalance.objects.filter(user=user))
        balance = qs.get()
    except UserBalance.DoesNotExist:
        return None

    higher_ranked_count = (
        UserBalance.objects.filter(
            Q(balance__gt=balance.balance)
            | Q(balance=balance.balance, user_id__lt=user.id)
        )
        .filter(user__is_superuser=False, user__is_active=True)
        .count()
    )

    balance.display_identity = get_public_identity(user)
    balance.rank = higher_ranked_count + 1
    _compute_balance_deltas([balance])
    return balance


def _get_stats_rank(user, board_type):
    try:
        stats = user.stats
    except UserStats.DoesNotExist:
        return None

    if stats.total_bets == 0:
        return None

    if board_type == "profit":
        higher = (
            UserStats.objects.filter(
                Q(net_profit__gt=stats.net_profit)
                | Q(net_profit=stats.net_profit, user_id__lt=user.id)
            )
            .filter(total_bets__gt=0, user__is_superuser=False, user__is_active=True)
            .count()
        )
    elif board_type == "win_rate":
        if stats.total_bets < WIN_RATE_MIN_BETS:
            return None
        user_wins = stats.total_wins
        user_bets = stats.total_bets
        higher = (
            UserStats.objects.filter(
                total_bets__gte=WIN_RATE_MIN_BETS,
                user__is_superuser=False,
                user__is_active=True,
            )
            .annotate(
                _cross_theirs=F("total_wins") * Value(user_bets),
                _cross_user=Value(user_wins) * F("total_bets"),
            )
            .filter(
                Q(_cross_theirs__gt=F("_cross_user"))
                | Q(
                    _cross_theirs=F("_cross_user"),
                    total_bets__gt=user_bets,
                )
                | Q(
                    _cross_theirs=F("_cross_user"),
                    total_bets=user_bets,
                    user_id__lt=user.id,
                )
            )
            .count()
        )
    elif board_type == "streak":
        higher = (
            UserStats.objects.filter(
                Q(best_streak__gt=stats.best_streak)
                | Q(
                    best_streak=stats.best_streak,
                    current_streak__gt=stats.current_streak,
                )
                | Q(
                    best_streak=stats.best_streak,
                    current_streak=stats.current_streak,
                    user_id__lt=user.id,
                )
            )
            .filter(total_bets__gt=0, user__is_superuser=False, user__is_active=True)
            .count()
        )
    else:
        return None

    stats.display_identity = get_public_identity(user)
    stats.rank = higher + 1
    return stats
