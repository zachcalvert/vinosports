"""
Badge criteria and awarding logic.

Each badge maps to a slug defined in BADGE_DEFINITIONS and a criterion
callable checked after every bet settlement.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from betting.models import BetSlip

logger = logging.getLogger(__name__)

BADGE_DEFINITIONS = [
    {
        "slug": "first_blood",
        "name": "First Blood",
        "description": "Place your first bet.",
        "icon": "drop",
        "rarity": "common",
    },
    {
        "slug": "called_the_upset",
        "name": "Called the Upset",
        "description": "Win a bet on a team with odds greater than 4.00.",
        "icon": "megaphone",
        "rarity": "uncommon",
    },
    {
        "slug": "perfect_matchweek",
        "name": "Perfect Matchweek",
        "description": "Win every settled bet placed in a single matchweek.",
        "icon": "trophy",
        "rarity": "rare",
    },
    {
        "slug": "parlay_king",
        "name": "Parlay King",
        "description": "Hit a 5-leg or longer parlay.",
        "icon": "crown",
        "rarity": "epic",
    },
    {
        "slug": "underdog_hunter",
        "name": "Underdog Hunter",
        "description": "Win 10 or more upset bets (odds > 4.00) all time.",
        "icon": "dog",
        "rarity": "rare",
    },
    {
        "slug": "streak_master",
        "name": "Streak Master",
        "description": "Achieve a 10-win streak.",
        "icon": "fire",
        "rarity": "epic",
    },
    {
        "slug": "high_roller",
        "name": "High Roller",
        "description": "Place a max-stake bet and win.",
        "icon": "diamond",
        "rarity": "uncommon",
    },
    {
        "slug": "sharp_eye",
        "name": "Sharp Eye",
        "description": "Maintain a 60%+ win rate over 50 or more settled bets.",
        "icon": "target",
        "rarity": "rare",
    },
    {
        "slug": "century",
        "name": "Century",
        "description": "Place 100 bets.",
        "icon": "medal",
        "rarity": "common",
    },
]

UPSET_ODDS_THRESHOLD = Decimal("4.00")
STREAK_MASTER_THRESHOLD = 10
SHARP_EYE_MIN_BETS = 50
SHARP_EYE_WIN_RATE = Decimal("60.0")
PARLAY_KING_MIN_LEGS = 5
UNDERDOG_HUNTER_THRESHOLD = 10
CENTURY_THRESHOLD = 100


@dataclass
class BetContext:
    won: bool
    odds: Decimal
    is_parlay: bool
    leg_count: int
    stake: Decimal
    max_stake: Decimal
    matchday: int | None = None


def _first_blood(stats, ctx):
    return stats.total_bets >= 1


def _called_the_upset(stats, ctx):
    return ctx.won and ctx.odds > UPSET_ODDS_THRESHOLD


def _perfect_matchweek(stats, ctx):
    if not ctx.won or ctx.matchday is None:
        return False

    settled_statuses = list(
        BetSlip.objects.filter(
            user=stats.user,
            match__matchday=ctx.matchday,
            status__in=[BetSlip.Status.WON, BetSlip.Status.LOST],
        ).values_list("status", flat=True)
    )
    return len(settled_statuses) >= 1 and all(
        s == BetSlip.Status.WON for s in settled_statuses
    )


def _parlay_king(stats, ctx):
    return ctx.won and ctx.is_parlay and ctx.leg_count >= PARLAY_KING_MIN_LEGS


def _underdog_hunter(stats, ctx):
    from betting.models import BetSlip, Parlay

    user = stats.user
    single_upsets = BetSlip.objects.filter(
        user=user,
        status=BetSlip.Status.WON,
        odds_at_placement__gt=UPSET_ODDS_THRESHOLD,
    ).count()
    parlay_upsets = Parlay.objects.filter(
        user=user,
        status=Parlay.Status.WON,
        combined_odds__gt=UPSET_ODDS_THRESHOLD,
    ).count()
    return (single_upsets + parlay_upsets) >= UNDERDOG_HUNTER_THRESHOLD


def _streak_master(stats, ctx):
    return stats.best_streak >= STREAK_MASTER_THRESHOLD


def _high_roller(stats, ctx):
    return ctx.won and not ctx.is_parlay and ctx.stake >= ctx.max_stake


def _sharp_eye(stats, ctx):
    return (
        stats.total_bets >= SHARP_EYE_MIN_BETS
        and stats.win_rate >= SHARP_EYE_WIN_RATE
    )


def _century(stats, ctx):
    return stats.total_bets >= CENTURY_THRESHOLD


CRITERIA = [
    ("first_blood", _first_blood),
    ("called_the_upset", _called_the_upset),
    ("perfect_matchweek", _perfect_matchweek),
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
