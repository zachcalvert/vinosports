"""World Cup bot tasks — strategy execution and comment generation."""

import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from vinosports.betting.models import BetStatus, UserBalance
from vinosports.bots.models import BotProfile
from worldcup.betting.models import BetSlip
from worldcup.bots.comment_service import generate_bot_comment, select_reply_bot
from worldcup.bots.models import BotComment
from worldcup.bots.strategies import STRATEGY_MAP
from worldcup.discussions.models import Comment
from worldcup.matches.models import Match, Odds

logger = logging.getLogger(__name__)

User = get_user_model()


@shared_task
def run_bot_strategies():
    """Hourly dispatcher — check bot schedules and place bets."""
    from vinosports.bots.models import BotProfile

    active_bots = BotProfile.objects.filter(is_active=True, active_in_worldcup=True)
    for bot in active_bots:
        execute_bot_strategy.delay(bot.pk)


@shared_task
def execute_bot_strategy(bot_profile_pk):
    """Execute a single bot's betting strategy for World Cup matches."""

    try:
        profile = BotProfile.objects.select_related("user").get(pk=bot_profile_pk)
    except BotProfile.DoesNotExist:
        logger.warning("BotProfile %s not found", bot_profile_pk)
        return

    if not profile.is_active or not profile.active_in_worldcup:
        return

    bot_user = profile.user

    try:
        balance_obj = UserBalance.objects.get(user=bot_user)
    except UserBalance.DoesNotExist:
        logger.warning("No UserBalance for bot %s", bot_user.email)
        return

    if balance_obj.balance <= 0:
        return

    strategy_cls = STRATEGY_MAP.get(profile.strategy_type)
    if not strategy_cls:
        logger.warning(
            "Unknown strategy %s for bot %s", profile.strategy_type, bot_user.email
        )
        return

    # Fetch available odds for upcoming scheduled matches
    today = timezone.now().date()
    odds_qs = (
        Odds.objects.filter(
            match__status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
            match__kickoff__date=today,
        )
        .select_related("match__home_team", "match__away_team")
        .order_by("match__kickoff")
    )

    # Count bets already placed today to respect max_daily_bets
    bets_today = BetSlip.objects.filter(
        user=bot_user,
        created_at__date=today,
    ).count()
    remaining = profile.max_daily_bets - bets_today
    if remaining <= 0:
        logger.debug("Bot %s has hit daily bet cap", bot_user.email)
        return

    strategy = strategy_cls(profile, balance_obj.balance)
    instructions = strategy.pick_bets(odds_qs)

    placed = 0
    for instruction in instructions:
        if placed >= remaining:
            break
        try:
            match = Match.objects.get(pk=instruction.match_id)
            odds_row = match.odds.order_by("-fetched_at").first()
            if not odds_row:
                continue

            # Resolve the correct decimal odds for the chosen selection
            odds_map = {
                BetSlip.Selection.HOME_WIN: odds_row.home_win,
                BetSlip.Selection.DRAW: odds_row.draw,
                BetSlip.Selection.AWAY_WIN: odds_row.away_win,
            }
            decimal_odds = odds_map.get(instruction.selection)
            if decimal_odds is None:
                continue

            BetSlip.objects.create(
                user=bot_user,
                match=match,
                selection=instruction.selection,
                odds_at_placement=decimal_odds,
                stake=instruction.stake,
            )
            placed += 1
            logger.info(
                "Bot %s placed %s on %s @ %s (stake %s)",
                bot_user.display_name,
                instruction.selection,
                match,
                decimal_odds,
                instruction.stake,
            )
        except Exception:
            logger.exception(
                "Failed to place bet for bot %s on match %s",
                bot_user.email,
                instruction.match_id,
            )


@shared_task
def generate_bot_comment_task(
    bot_user_pk, match_pk, trigger_type, bet_slip_pk=None, parent_comment_pk=None
):
    """Generate and post a bot comment for a World Cup match."""
    try:
        bot_user = User.objects.get(pk=bot_user_pk)
        match = Match.objects.select_related(
            "home_team", "away_team", "stage", "group"
        ).get(pk=match_pk)
    except (User.DoesNotExist, Match.DoesNotExist):
        logger.warning(
            "generate_bot_comment_task: missing user %s or match %s",
            bot_user_pk,
            match_pk,
        )
        return

    bet_slip = None
    if bet_slip_pk:
        try:
            bet_slip = BetSlip.objects.get(pk=bet_slip_pk)
        except BetSlip.DoesNotExist:
            pass

    parent_comment = None
    if parent_comment_pk:
        try:
            parent_comment = Comment.objects.select_related("user").get(
                pk=parent_comment_pk
            )
        except Comment.DoesNotExist:
            pass

    generate_bot_comment(
        bot_user,
        match,
        trigger_type,
        bet_slip=bet_slip,
        parent_comment=parent_comment,
    )


@shared_task
def generate_prematch_comments(bot_user_ids=None):
    """Dispatch pre-match hype comments for upcoming World Cup matches."""
    now = timezone.now()

    upcoming = Match.objects.filter(
        status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
        kickoff__gte=now,
        kickoff__lte=now + timezone.timedelta(hours=3),
    )
    if not upcoming.exists():
        return

    profiles_qs = BotProfile.objects.filter(
        is_active=True,
        active_in_worldcup=True,
        user__is_bot=True,
        user__is_active=True,
        persona_prompt__gt="",
    ).select_related("user")

    if bot_user_ids:
        profiles_qs = profiles_qs.filter(user_id__in=bot_user_ids)

    for match in upcoming:
        for profile in profiles_qs:
            already = BotComment.objects.filter(
                user=profile.user,
                match=match,
                trigger_type=BotComment.TriggerType.PRE_MATCH,
            ).exists()
            if already:
                continue
            generate_bot_comment_task.delay(
                profile.user_id,
                match.pk,
                BotComment.TriggerType.PRE_MATCH,
            )


@shared_task
def generate_postmatch_comments(bot_user_ids=None):
    """Dispatch post-match reaction comments for finished World Cup matches."""
    now = timezone.now()

    recently_finished = Match.objects.filter(
        status=Match.Status.FINISHED,
        kickoff__gte=now - timezone.timedelta(hours=3),
    )
    if not recently_finished.exists():
        return

    profiles_qs = BotProfile.objects.filter(
        is_active=True,
        active_in_worldcup=True,
        user__is_bot=True,
        user__is_active=True,
        persona_prompt__gt="",
    ).select_related("user")

    if bot_user_ids:
        profiles_qs = profiles_qs.filter(user_id__in=bot_user_ids)

    for match in recently_finished:
        for profile in profiles_qs:
            already = BotComment.objects.filter(
                user=profile.user,
                match=match,
                trigger_type=BotComment.TriggerType.POST_MATCH,
            ).exists()
            if already:
                continue
            # Look up any settled bet this bot placed on the match
            bet_slip = BetSlip.objects.filter(
                user=profile.user,
                match=match,
                status__in=[BetStatus.WON, BetStatus.LOST],
            ).first()
            generate_bot_comment_task.delay(
                profile.user_id,
                match.pk,
                BotComment.TriggerType.POST_MATCH,
                bet_slip_pk=bet_slip.pk if bet_slip else None,
            )


@shared_task
def maybe_reply_to_human_comment(match_pk, comment_pk):
    """Possibly trigger a bot reply to a human comment on a World Cup match."""
    try:
        match = Match.objects.select_related("home_team", "away_team").get(pk=match_pk)
        comment = Comment.objects.select_related("user").get(pk=comment_pk)
    except (Match.DoesNotExist, Comment.DoesNotExist):
        return

    bot_user = select_reply_bot(match, comment)
    if not bot_user:
        return

    generate_bot_comment(
        bot_user,
        match,
        BotComment.TriggerType.REPLY,
        parent_comment=comment,
    )


@shared_task
def generate_featured_parlays():
    """Build themed World Cup parlays for the featured section."""
    logger.info("Generating World Cup featured parlays")
