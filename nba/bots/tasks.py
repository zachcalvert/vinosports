"""
Celery tasks for bot betting.

run_bot_strategies() is the orchestrator — runs hourly and dispatches
execute_bot_strategy() only for bots whose schedule template has an active
window at the current time.
"""

import logging
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from nba.betting.models import BetSlip
from nba.betting.settlement import BANKRUPTCY_THRESHOLD, grant_bailout
from nba.bots.services import place_bot_bets
from nba.bots.strategies import STRATEGY_MAP
from nba.games.models import Game, GameStatus, Odds
from nba.games.services import today_et
from vinosports.betting.models import UserBalance
from vinosports.bots.models import BotProfile
from vinosports.bots.schedule import get_active_window, roll_action

logger = logging.getLogger(__name__)

BAILOUT_AMOUNT = Decimal("500.00")
MIN_BALANCE = Decimal("5.00")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def run_bot_strategies(self):
    """Dispatch execute_bot_strategy for active bots whose schedule window matches now."""
    now = timezone.localtime()
    today = today_et()
    profiles = BotProfile.objects.filter(
        is_active=True, active_in_nba=True
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

        window_max_bets = window.get("max_bets", profile.max_daily_bets)

        execute_bot_strategy.apply_async(
            args=[profile.user_id, window_max_bets],
            countdown=i * 10,
        )
        dispatched += 1

    logger.info(
        "run_bot_strategies: dispatched %d bots, skipped %d (schedule)",
        dispatched,
        skipped_schedule,
    )
    return {"dispatched": dispatched, "skipped_schedule": skipped_schedule}


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def execute_bot_strategy(self, bot_user_id: int, window_max_bets: int | None = None):
    """Run a single bot's strategy and place bets."""
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        user = User.objects.get(pk=bot_user_id, is_bot=True)
    except User.DoesNotExist:
        logger.warning("Bot user %d not found or not a bot", bot_user_id)
        return {"error": "user_not_found"}

    try:
        profile = user.bot_profile
    except BotProfile.DoesNotExist:
        logger.warning("No BotProfile for user %d", bot_user_id)
        return {"error": "no_profile"}

    balance_obj, _ = UserBalance.objects.get_or_create(
        user=user, defaults={"balance": Decimal("1000.00")}
    )

    if balance_obj.balance < MIN_BALANCE:
        if balance_obj.balance <= BANKRUPTCY_THRESHOLD:
            try:
                grant_bailout(user, BAILOUT_AMOUNT)
                balance_obj.refresh_from_db()
            except ValueError:
                pass
        else:
            logger.info(
                "Bot %s balance too low ($%s), skipping", user, balance_obj.balance
            )
            return {"error": "low_balance"}

    today = today_et()
    games = Game.objects.filter(status=GameStatus.SCHEDULED, game_date=today)
    if not games.exists():
        return {"bets": 0, "reason": "no_games"}

    odds_qs = (
        Odds.objects.filter(game__in=games)
        .select_related("game", "game__home_team", "game__away_team")
        .order_by("game_id", "-fetched_at")
        .distinct("game_id")
    )

    bets_today = BetSlip.objects.filter(user=user, created_at__date=today).count()
    daily_remaining = max(0, profile.max_daily_bets - bets_today)
    # Also respect the window-level cap if provided
    remaining = (
        min(daily_remaining, window_max_bets) if window_max_bets else daily_remaining
    )
    if remaining == 0:
        return {"bets": 0, "reason": "daily_limit"}

    strategy_cls = STRATEGY_MAP.get(profile.strategy_type)
    if not strategy_cls:
        logger.warning("Unknown strategy %s for bot %s", profile.strategy_type, user)
        return {"error": "unknown_strategy"}

    strategy = strategy_cls(profile, balance_obj.balance)
    instructions = strategy.pick_bets(odds_qs)
    instructions = instructions[:remaining]

    if not instructions:
        return {"bets": 0, "reason": "no_picks"}

    result = place_bot_bets(user, instructions)
    logger.info(
        "Bot %s placed %d bets (skipped %d)", user, result["placed"], result["skipped"]
    )
    return result
