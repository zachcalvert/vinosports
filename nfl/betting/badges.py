"""
Badge criteria and awarding logic for NFL.

Each badge maps to a slug defined in BADGE_DEFINITIONS and a criterion
callable checked after every bet settlement.

Uses American odds (converted to decimal for threshold comparisons).
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from vinosports.betting.models import BetStatus

logger = logging.getLogger(__name__)

# American odds threshold equivalent to decimal 4.00 (i.e., +300)
UPSET_ODDS_AMERICAN_THRESHOLD = 300
UPSET_ODDS_DECIMAL_THRESHOLD = Decimal("4.00")
STREAK_MASTER_THRESHOLD = 10
SHARP_EYE_MIN_BETS = 50
SHARP_EYE_WIN_RATE = Decimal("60.0")
PARLAY_KING_MIN_LEGS = 5
UNDERDOG_HUNTER_THRESHOLD = 10
CENTURY_THRESHOLD = 100


@dataclass
class BetContext:
    won: bool
    odds: Decimal  # decimal odds (converted from American)
    is_parlay: bool
    leg_count: int
    stake: Decimal
    max_stake: Decimal


def american_to_decimal(odds: int) -> Decimal:
    """Convert American odds to decimal odds."""
    if odds > 0:
        return Decimal(odds) / 100 + 1
    else:
        return Decimal(100) / Decimal(abs(odds)) + 1


def _first_blood(stats, ctx):
    return stats.total_bets >= 1


def _called_the_upset(stats, ctx):
    return ctx.won and ctx.odds > UPSET_ODDS_DECIMAL_THRESHOLD


def _parlay_king(stats, ctx):
    return ctx.won and ctx.is_parlay and ctx.leg_count >= PARLAY_KING_MIN_LEGS


def _underdog_hunter(stats, ctx):
    from nfl.betting.models import BetSlip, Parlay

    user = stats.user
    single_upsets = BetSlip.objects.filter(
        user=user,
        status=BetStatus.WON,
        odds_at_placement__gt=UPSET_ODDS_AMERICAN_THRESHOLD,
    ).count()
    parlay_upsets = Parlay.objects.filter(
        user=user,
        status=BetStatus.WON,
        combined_odds__gt=UPSET_ODDS_AMERICAN_THRESHOLD,
    ).count()
    return (single_upsets + parlay_upsets) >= UNDERDOG_HUNTER_THRESHOLD


def _streak_master(stats, ctx):
    return stats.best_streak >= STREAK_MASTER_THRESHOLD


def _high_roller(stats, ctx):
    return ctx.won and not ctx.is_parlay and ctx.stake >= ctx.max_stake


def _sharp_eye(stats, ctx):
    return (
        stats.total_bets >= SHARP_EYE_MIN_BETS and stats.win_rate >= SHARP_EYE_WIN_RATE
    )


def _century(stats, ctx):
    return stats.total_bets >= CENTURY_THRESHOLD


CRITERIA = [
    ("first_blood", _first_blood),
    ("called_the_upset", _called_the_upset),
    ("parlay_king", _parlay_king),
    ("underdog_hunter", _underdog_hunter),
    ("streak_master", _streak_master),
    ("high_roller", _high_roller),
    ("sharp_eye", _sharp_eye),
    ("century", _century),
]


def check_and_award_badges(user, stats, ctx: BetContext):
    from vinosports.betting.models import Badge, UserBadge

    already_earned = set(
        UserBadge.objects.filter(user=user).values_list("badge__slug", flat=True)
    )

    candidate_slugs = [slug for slug, _ in CRITERIA if slug not in already_earned]
    if not candidate_slugs:
        return []

    badge_map = {b.slug: b for b in Badge.objects.filter(slug__in=candidate_slugs)}

    newly_earned = []
    for slug, criterion in CRITERIA:
        if slug in already_earned or slug not in badge_map:
            continue
        try:
            earned = criterion(stats, ctx)
        except Exception:
            logger.exception("Badge criterion error for slug=%s user=%s", slug, user.pk)
            continue

        if earned:
            user_badge, created = UserBadge.objects.get_or_create(
                user=user, badge=badge_map[slug]
            )
            if created:
                newly_earned.append(user_badge)
                logger.info("Badge awarded: %s → %s", slug, user.pk)

    return newly_earned
