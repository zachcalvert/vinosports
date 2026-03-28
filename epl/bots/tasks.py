"""
Celery tasks for running bot betting strategies and generating bot comments.

run_bot_strategies() is the orchestrator — runs hourly and dispatches
execute_bot_strategy() only for bots whose schedule template has an active
window at the current time.
"""

import logging
import random

from celery import shared_task
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from epl.activity.services import queue_activity_event
from epl.bots.models import BotComment
from epl.bots.registry import get_strategy_for_bot
from epl.bots.services import (
    get_available_matches_for_bot,
    get_best_odds_map,
    get_full_odds_map,
    maybe_topup_bot,
    place_bot_bet,
    place_bot_parlay,
)
from vinosports.bots.models import BotProfile
from vinosports.bots.schedule import get_active_window, roll_action

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bot betting tasks
# ---------------------------------------------------------------------------


@shared_task
def run_bot_strategies():
    """Dispatch execute_bot_strategy for active bots whose schedule window matches now."""
    from epl.betting.models import BetSlip

    now = timezone.localtime()
    today = now.date()
    profiles = BotProfile.objects.filter(
        is_active=True, active_in_epl=True
    ).select_related("user", "schedule_template")

    dispatched = 0
    skipped_schedule = 0

    for i, profile in enumerate(profiles):
        window = get_active_window(profile, now)
        if window is None:
            skipped_schedule += 1
            continue

        if not roll_action(window.get("bet_probability", 0.5)):
            continue

        bets_today = BetSlip.objects.filter(
            user=profile.user, created_at__date=today
        ).count()
        if bets_today >= profile.max_daily_bets:
            continue

        delay = random.randint(120, 1800)  # 2-30 minutes stagger
        execute_bot_strategy.apply_async(args=[profile.user_id], countdown=delay)
        dispatched += 1

    logger.info(
        "run_bot_strategies: dispatched %d bots, skipped %d (schedule)",
        dispatched,
        skipped_schedule,
    )
    return {"dispatched": dispatched, "skipped_schedule": skipped_schedule}


@shared_task(bind=True, max_retries=1)
def execute_bot_strategy(self, bot_user_id):
    """Run a single bot's strategy and place its bets."""
    try:
        user = User.objects.get(pk=bot_user_id, is_bot=True, is_active=True)
    except User.DoesNotExist:
        logger.warning("Bot user %s not found or inactive", bot_user_id)
        return "bot not found"

    strategy = get_strategy_for_bot(user)
    if not strategy:
        logger.warning("No strategy registered for bot %s", user.email)
        return "no strategy"

    # Top up if broke
    maybe_topup_bot(user)

    # Get available matches
    available = get_available_matches_for_bot(user)
    if not available.exists():
        return "no matches"

    pk_slug_rows = list(available.values_list("pk", "slug"))
    match_ids = [row[0] for row in pk_slug_rows]
    slug_map = dict(pk_slug_rows)
    odds_map = get_best_odds_map(match_ids)

    if not odds_map:
        return f"no odds for {user.email}"

    # ValueHunter needs full per-bookmaker odds
    from epl.bots.strategies import ValueHunterStrategy

    if isinstance(strategy, ValueHunterStrategy):
        odds_map["_full"] = get_full_odds_map(match_ids)

    # Get current balance for stake calculations
    from vinosports.betting.models import UserBalance

    try:
        balance = UserBalance.objects.get(user=user).balance
    except UserBalance.DoesNotExist:
        return "no balance"

    # Place single bets
    bets_placed = 0
    picks = strategy.pick_bets(available, odds_map, balance)
    for pick in picks:
        result = place_bot_bet(user, pick.match_id, pick.selection, pick.stake)
        if result:
            bets_placed += 1
            queue_activity_event(
                "bot_bet",
                f"{user.display_name} placed a bet on {result.match}",
                url=result.match.get_absolute_url(),
                icon="coin",
            )
            # Post-bet comment (~50% chance, staggered 30s-5min)
            if random.random() < 0.5:
                generate_bot_comment_task.apply_async(
                    args=[
                        user.pk,
                        pick.match_id,
                        BotComment.TriggerType.POST_BET,
                        result.pk,
                    ],
                    countdown=random.randint(30, 300),
                )

    # Place parlays
    parlays_placed = 0
    parlay_picks = strategy.pick_parlays(available, odds_map, balance)
    for pp in parlay_picks:
        result = place_bot_parlay(user, pp.legs, pp.stake)
        if result:
            parlays_placed += 1
            queue_activity_event(
                "bot_bet",
                f"{user.display_name} placed a {len(pp.legs)}-leg parlay",
                url=reverse(
                    "epl_matches:match_detail",
                    kwargs={"slug": slug_map[pp.legs[0]["match_id"]]},
                ),
                icon="coins",
            )

    summary = f"{user.display_name}: {bets_placed} bets, {parlays_placed} parlays"
    logger.info("Bot run complete: %s", summary)
    return summary


# ---------------------------------------------------------------------------
# Bot comment tasks
# ---------------------------------------------------------------------------


@shared_task
def generate_bot_comment_task(bot_user_id, match_id, trigger_type, bet_slip_id=None):
    """Generate and post a single bot comment. Dedup-safe via BotComment constraint."""
    from epl.betting.models import BetSlip
    from epl.bots.comment_service import generate_bot_comment
    from epl.matches.models import Match

    try:
        bot_user = User.objects.get(pk=bot_user_id, is_bot=True, is_active=True)
    except User.DoesNotExist:
        return "bot not found"

    try:
        match = Match.objects.select_related("home_team", "away_team").get(pk=match_id)
    except Match.DoesNotExist:
        return "match not found"

    bet_slip = None
    if bet_slip_id:
        try:
            bet_slip = BetSlip.objects.get(pk=bet_slip_id, user=bot_user, match=match)
        except BetSlip.DoesNotExist:
            pass

    comment = generate_bot_comment(bot_user, match, trigger_type, bet_slip)
    if not comment:
        return "skipped (dedup or filter)"

    queue_activity_event(
        "bot_comment",
        f"{bot_user.display_name} commented on {match}",
        url=match.get_absolute_url(),
        icon="chat-circle",
    )

    # After posting a non-reply comment, maybe trigger a reply from another bot
    if trigger_type != BotComment.TriggerType.REPLY:
        _maybe_dispatch_reply(match, comment)

    return f"posted: {comment.body[:60]}"


@shared_task
def generate_bot_reply_task(bot_user_id, match_id, parent_comment_id):
    """Generate and post a bot reply to an existing comment."""
    from epl.bots.comment_service import generate_bot_comment
    from epl.discussions.models import Comment as DiscussionComment
    from epl.matches.models import Match

    try:
        bot_user = User.objects.get(pk=bot_user_id, is_bot=True, is_active=True)
    except User.DoesNotExist:
        return "bot not found"

    try:
        match = Match.objects.select_related("home_team", "away_team").get(pk=match_id)
    except Match.DoesNotExist:
        return "match not found"

    try:
        parent = DiscussionComment.objects.select_related("user").get(
            pk=parent_comment_id,
            match=match,
        )
    except DiscussionComment.DoesNotExist:
        return "parent comment not found"

    comment = generate_bot_comment(
        bot_user,
        match,
        BotComment.TriggerType.REPLY,
        parent_comment=parent,
    )
    if comment:
        return f"replied: {comment.body[:60]}"
    return "skipped (dedup or filter)"


@shared_task
def maybe_reply_to_human_comment(comment_id):
    """Maybe dispatch a bot reply to a human-authored comment."""
    from epl.bots.comment_service import select_reply_bot
    from epl.discussions.models import Comment as DiscussionComment

    try:
        comment = DiscussionComment.objects.select_related(
            "user",
            "match",
            "match__home_team",
            "match__away_team",
        ).get(pk=comment_id)
    except DiscussionComment.DoesNotExist:
        return "comment not found"

    if comment.user.is_bot:
        return "skipped (bot author)"

    if not comment.match:
        return "skipped (no match)"

    bot = select_reply_bot(comment.match, comment)
    if not bot:
        return "skipped (no candidate)"

    delay = random.randint(120, 480)  # 2-8 min stagger
    generate_bot_reply_task.apply_async(
        args=[bot.pk, comment.match.pk, comment.pk],
        countdown=delay,
    )
    return f"dispatched reply from {bot.display_name}"


# Per-run dispatch caps — keeps Celery queue and API costs manageable.
MAX_PREMATCH_DISPATCHES = 20
MAX_POSTMATCH_DISPATCHES = 30


@shared_task
def generate_prematch_comments():
    """Find upcoming matches and dispatch pre-match hype comments for 1-2 bots each.

    Checks each bot's schedule window and rolls comment_probability before dispatching.
    """
    from epl.bots.comment_service import select_bots_for_match
    from epl.matches.models import Match

    now = timezone.localtime()
    upcoming = Match.objects.filter(
        status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
        kickoff__gte=now + timezone.timedelta(hours=1),
        kickoff__lte=now + timezone.timedelta(hours=24),
    ).select_related("home_team", "away_team")

    from epl.betting.models import BetSlip
    from vinosports.betting.models import BetStatus

    dispatched = 0
    for match in upcoming:
        if dispatched >= MAX_PREMATCH_DISPATCHES:
            break
        bots = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)
        for bot in bots:
            if dispatched >= MAX_PREMATCH_DISPATCHES:
                break

            # Check schedule window before dispatching
            try:
                profile = bot.bot_profile
            except BotProfile.DoesNotExist:
                continue
            window = get_active_window(profile, now)
            if window is None:
                continue
            if not roll_action(window.get("comment_probability", 0.5)):
                continue

            existing_bet = BetSlip.objects.filter(
                user=bot, match=match, status=BetStatus.PENDING
            ).first()
            bet_slip_id = existing_bet.pk if existing_bet else None
            delay = random.randint(60, 600)  # 1-10 min stagger
            generate_bot_comment_task.apply_async(
                args=[bot.pk, match.pk, BotComment.TriggerType.PRE_MATCH, bet_slip_id],
                countdown=delay,
            )
            dispatched += 1

    logger.info(
        "Dispatched %d pre-match comment tasks (cap %d)",
        dispatched,
        MAX_PREMATCH_DISPATCHES,
    )
    return f"dispatched {dispatched} pre-match comments"


@shared_task
def generate_postmatch_comments():
    """Find recently finished matches and dispatch post-match reaction comments.

    Checks each bot's schedule window and rolls comment_probability before dispatching.
    """
    from epl.betting.models import BetSlip
    from epl.bots.comment_service import select_bots_for_match
    from epl.matches.models import Match

    now = timezone.localtime()
    recently_finished = Match.objects.filter(
        status=Match.Status.FINISHED,
        updated_at__gte=now - timezone.timedelta(hours=2),
        kickoff__gte=now - timezone.timedelta(weeks=1),
    ).select_related("home_team", "away_team")

    dispatched = 0
    for match in recently_finished:
        if dispatched >= MAX_POSTMATCH_DISPATCHES:
            break

        # One reaction per bot user — pick their most recent bet on this match
        seen_user_ids = set()
        bot_bets = (
            BetSlip.objects.filter(
                user__is_bot=True,
                user__is_active=True,
                match=match,
            )
            .select_related("user")
            .order_by("user_id", "-created_at")
        )

        for bet in bot_bets:
            if dispatched >= MAX_POSTMATCH_DISPATCHES:
                break
            if bet.user_id in seen_user_ids:
                continue
            seen_user_ids.add(bet.user_id)

            # Check schedule window before dispatching
            try:
                profile = bet.user.bot_profile
            except BotProfile.DoesNotExist:
                continue
            window = get_active_window(profile, now)
            if window is None:
                continue
            if not roll_action(window.get("comment_probability", 0.5)):
                continue

            if BotComment.objects.filter(
                user=bet.user,
                match=match,
                trigger_type=BotComment.TriggerType.POST_MATCH,
            ).exists():
                continue
            delay = random.randint(60, 600)
            generate_bot_comment_task.apply_async(
                args=[bet.user.pk, match.pk, BotComment.TriggerType.POST_MATCH, bet.pk],
                countdown=delay,
            )
            dispatched += 1

        if dispatched >= MAX_POSTMATCH_DISPATCHES:
            break

        # Pick 1 non-betting bot for color commentary, excluding bots already enqueued
        color_bots = select_bots_for_match(
            match,
            BotComment.TriggerType.POST_MATCH,
            max_bots=1,
            exclude_user_ids=seen_user_ids,
        )
        for bot in color_bots:
            # Check schedule window for color commentary bots too
            try:
                profile = bot.bot_profile
            except BotProfile.DoesNotExist:
                continue
            window = get_active_window(profile, now)
            if window is None:
                continue
            if not roll_action(window.get("comment_probability", 0.5)):
                continue

            delay = random.randint(120, 900)
            generate_bot_comment_task.apply_async(
                args=[bot.pk, match.pk, BotComment.TriggerType.POST_MATCH, None],
                countdown=delay,
            )
            dispatched += 1

    logger.info(
        "Dispatched %d post-match comment tasks (cap %d)",
        dispatched,
        MAX_POSTMATCH_DISPATCHES,
    )
    return f"dispatched {dispatched} post-match comments"


# ---------------------------------------------------------------------------
# Reply dispatch helper (called inline after a bot comment is posted)
# ---------------------------------------------------------------------------


def _maybe_dispatch_reply(match, comment):
    """Maybe dispatch a bot reply to the given comment."""
    from epl.bots.comment_service import select_reply_bot

    bot = select_reply_bot(match, comment)
    if not bot:
        return

    delay = random.randint(120, 480)  # 2-8 min stagger
    generate_bot_reply_task.apply_async(
        args=[bot.pk, match.pk, comment.pk],
        countdown=delay,
    )
    logger.info(
        "Dispatched reply from %s to %s's comment on %s",
        bot.display_name,
        comment.user.display_name,
        match,
    )


# ---------------------------------------------------------------------------
# Featured Parlays
# ---------------------------------------------------------------------------


@shared_task(name="epl.bots.tasks.generate_featured_parlays")
def generate_featured_parlays():
    """Generate featured parlay proposals for the upcoming EPL matchday.

    Scheduled weekly (Friday 8am). Builds 2-3 themed parlays using
    ParlayBuilder.preview(), then asks Claude for a catchy title and description.
    """
    from datetime import timedelta
    from decimal import Decimal

    from epl.bots.services import get_best_odds_map
    from epl.matches.models import Match
    from vinosports.betting.featured import FeaturedParlay, FeaturedParlayLeg
    from vinosports.betting.featured_utils import generate_parlay_copy
    from vinosports.betting.parlay_builder import ParlayBuilder, ParlayValidationError

    # Get upcoming bettable matches
    matches = list(
        Match.objects.filter(
            status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
        )
        .select_related("home_team", "away_team")
        .order_by("kickoff")[:20]
    )
    if len(matches) < 3:
        logger.info(
            "EPL featured parlays: not enough matches (%d), skipping", len(matches)
        )
        return

    match_ids = [m.pk for m in matches]
    odds_map = get_best_odds_map(match_ids)
    if not odds_map:
        logger.info("EPL featured parlays: no odds available, skipping")
        return

    # Get all active EPL bots and shuffle them so each parlay gets a unique sponsor
    available_bots = list(
        BotProfile.objects.filter(is_active=True, active_in_epl=True)
        .select_related("user")
    )
    if not available_bots:
        logger.warning("EPL featured parlays: no active EPL bot found")
        return
    random.shuffle(available_bots)
    bot_iter = iter(available_bots)

    # Build themed parlays
    themes = _build_epl_parlay_themes(matches, odds_map)

    last_kickoff = max(
        (m.kickoff for m in matches if m.kickoff), default=timezone.now()
    )
    expires_at = last_kickoff + timedelta(hours=2)

    created = 0
    for theme_name, legs_data in themes.items():
        if len(legs_data) < 2:
            continue

        sponsor_bot = next(bot_iter, None)
        if not sponsor_bot:
            logger.info(
                "EPL featured parlays: no remaining bot for theme '%s', skipping",
                theme_name,
            )
            continue

        try:
            builder = ParlayBuilder("epl")
            for leg in legs_data:
                builder.add_leg(leg["match_id"], leg["selection"])
            preview = builder.preview(stake=Decimal("10.00"))
        except ParlayValidationError as e:
            logger.info("EPL featured parlay '%s' skipped: %s", theme_name, e)
            continue

        # Generate copy via Claude
        legs_summary = [
            {
                "event": leg["label"],
                "selection": leg["selection_label"],
                "odds": str(leg["odds"]),
            }
            for leg in legs_data
        ]
        copy = generate_parlay_copy(legs_summary, "epl", theme_name)

        fp = FeaturedParlay.objects.create(
            league="epl",
            sponsor=sponsor_bot.user,
            title=copy["title"],
            description=copy["description"],
            expires_at=expires_at,
            combined_odds=preview.combined_odds,
            potential_payout=preview.potential_payout,
        )
        FeaturedParlayLeg.objects.bulk_create(
            [
                FeaturedParlayLeg(
                    featured_parlay=fp,
                    event_id=resolved.leg.event_id,
                    event_label=_match_label(resolved.event),
                    selection=resolved.leg.selection,
                    selection_label=_epl_selection_label(resolved.leg.selection),
                    odds_snapshot=resolved.decimal_odds,
                    extras_json={},
                )
                for resolved in preview.legs
            ]
        )
        created += 1

    logger.info("EPL featured parlays: created %d parlays", created)


def _build_epl_parlay_themes(matches, odds_map):
    """Build themed leg lists from available matches and odds.

    Returns: {"favorites": [...], "underdogs": [...], "value": [...]}
    Each leg dict has: match_id, selection, label, selection_label, odds
    """
    favorites, underdogs, value = [], [], []

    for match in matches:
        odds = odds_map.get(match.pk)
        if not odds:
            continue

        label = _match_label(match)
        hw, dr, aw = odds.get("home_win"), odds.get("draw"), odds.get("away_win")
        if not all([hw, dr, aw]):
            continue

        # Favorites: lowest odds selection (most likely outcome)
        best_sel, best_odds = min(
            [("HOME_WIN", hw), ("AWAY_WIN", aw)], key=lambda x: x[1]
        )
        favorites.append(
            {
                "match_id": match.pk,
                "selection": best_sel,
                "selection_label": _epl_selection_label(best_sel),
                "label": label,
                "odds": best_odds,
            }
        )

        # Underdogs: highest odds selection
        dog_sel, dog_odds = max(
            [("HOME_WIN", hw), ("DRAW", dr), ("AWAY_WIN", aw)], key=lambda x: x[1]
        )
        underdogs.append(
            {
                "match_id": match.pk,
                "selection": dog_sel,
                "selection_label": _epl_selection_label(dog_sel),
                "label": label,
                "odds": dog_odds,
            }
        )

        # Value: draw selections in the 2.5-4.0 range
        from decimal import Decimal

        if Decimal("2.50") <= dr <= Decimal("4.00"):
            value.append(
                {
                    "match_id": match.pk,
                    "selection": "DRAW",
                    "selection_label": "Draw",
                    "label": label,
                    "odds": dr,
                }
            )

    # Trim to 3-4 legs each, picking the best candidates
    favorites.sort(key=lambda x: x["odds"])
    underdogs.sort(key=lambda x: x["odds"], reverse=True)

    return {
        "favorites": favorites[:4],
        "underdogs": underdogs[:4],
        "value": value[:4],
    }


def _match_label(match):
    return f"{match.home_team.name} vs {match.away_team.name}"


_EPL_SELECTION_LABELS = {
    "HOME_WIN": "Home Win",
    "DRAW": "Draw",
    "AWAY_WIN": "Away Win",
}


def _epl_selection_label(selection):
    return _EPL_SELECTION_LABELS.get(selection, selection)
