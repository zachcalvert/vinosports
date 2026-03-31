"""
Celery tasks for bot betting.

run_bot_strategies() is the orchestrator — runs hourly and dispatches
execute_bot_strategy() only for bots whose schedule template has an active
window at the current time.
"""

import logging
import random
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from nfl.betting.models import BetSlip, Odds
from nfl.betting.settlement import BANKRUPTCY_THRESHOLD, grant_bailout
from nfl.bots.services import place_bot_bets
from nfl.bots.strategies import STRATEGY_MAP
from nfl.games.models import Game, GameStatus
from nfl.games.services import today_et
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
        is_active=True, active_in_nfl=True
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
            user=profile.user, game__game_date=today
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

    bets_today = BetSlip.objects.filter(user=user, game__game_date=today).count()
    daily_remaining = max(0, profile.max_daily_bets - bets_today)
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


# ---------------------------------------------------------------------------
# Featured Parlays
# ---------------------------------------------------------------------------


@shared_task(name="nfl.bots.tasks.generate_featured_parlays")
def generate_featured_parlays():
    """Generate featured parlay proposals for today's NFL games.

    Scheduled daily (10am). Builds 1-2 themed parlays using
    ParlayBuilder.preview(), then asks Claude for a catchy title and description.
    Skips if not enough games are scheduled today.
    """
    from datetime import timedelta

    from vinosports.betting.featured import FeaturedParlay, FeaturedParlayLeg
    from vinosports.betting.featured_utils import generate_parlay_copy
    from vinosports.betting.parlay_builder import ParlayBuilder, ParlayValidationError

    today = today_et()
    games = list(
        Game.objects.filter(status=GameStatus.SCHEDULED, game_date=today)
        .select_related("home_team", "away_team")
        .order_by("kickoff")
    )
    if len(games) < 2:
        logger.info("NFL featured parlays: not enough games (%d), skipping", len(games))
        return

    # Get latest odds per game
    odds_by_game = {}
    for odds in (
        Odds.objects.filter(game__in=games)
        .select_related("game")
        .order_by("game_id", "-fetched_at")
        .distinct("game_id")
    ):
        odds_by_game[odds.game_id] = odds

    if not odds_by_game:
        logger.info("NFL featured parlays: no odds available, skipping")
        return

    # Get all active NFL bots and shuffle them so each parlay gets a unique sponsor
    available_bots = list(
        BotProfile.objects.filter(is_active=True, active_in_nfl=True).select_related(
            "user"
        )
    )
    if not available_bots:
        logger.warning("NFL featured parlays: no active NFL bot found")
        return
    random.shuffle(available_bots)
    bot_iter = iter(available_bots)

    themes = _build_nfl_parlay_themes(games, odds_by_game)

    last_kickoff = max(
        (g.kickoff for g in games if g.kickoff),
        default=timezone.now(),
    )
    expires_at = last_kickoff + timedelta(hours=5)

    created = 0
    for theme_name, legs_data in themes.items():
        if len(legs_data) < 2:
            continue

        sponsor_bot = next(bot_iter, None)
        if not sponsor_bot:
            logger.info(
                "NFL featured parlays: no remaining bot for theme '%s', skipping",
                theme_name,
            )
            continue

        try:
            builder = ParlayBuilder("nfl")
            for leg in legs_data:
                builder.add_leg(
                    leg["game_id"],
                    leg["selection"],
                    odds=leg.get("decimal_odds"),
                    market=leg["market"],
                    line=leg.get("line"),
                )
            preview = builder.preview(stake=Decimal("10.00"))
        except ParlayValidationError as e:
            logger.info("NFL featured parlay '%s' skipped: %s", theme_name, e)
            continue

        legs_summary = [
            {
                "event": leg["label"],
                "selection": leg["selection_label"],
                "odds": str(leg.get("decimal_odds", "")),
            }
            for leg in legs_data
        ]
        copy = generate_parlay_copy(legs_summary, "nfl", theme_name)

        fp = FeaturedParlay.objects.create(
            league="nfl",
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
                    event_label=_game_label(resolved.event),
                    selection=resolved.leg.selection,
                    selection_label=_nfl_selection_label(
                        resolved.leg.extras.get("market", "MONEYLINE"),
                        resolved.leg.selection,
                        resolved.leg.extras.get("line"),
                    ),
                    odds_snapshot=resolved.decimal_odds,
                    extras_json={
                        k: v for k, v in resolved.leg.extras.items() if v is not None
                    },
                )
                for resolved in preview.legs
            ]
        )
        created += 1

    logger.info("NFL featured parlays: created %d parlays", created)


def _build_nfl_parlay_themes(games, odds_by_game):
    """Build themed leg lists from today's games and odds.

    Returns: {"favorites": [...], "value": [...]}
    """
    from nfl.betting.settlement import american_to_decimal

    favorites, spread_picks = [], []

    for game in games:
        odds = odds_by_game.get(game.pk)
        if not odds:
            continue

        label = _game_label(game)

        # Moneyline favorites
        if odds.home_moneyline is not None and odds.away_moneyline is not None:
            if odds.home_moneyline < odds.away_moneyline:
                fav_sel, fav_odds = "HOME", odds.home_moneyline
            else:
                fav_sel, fav_odds = "AWAY", odds.away_moneyline

            favorites.append(
                {
                    "game_id": game.pk,
                    "selection": fav_sel,
                    "selection_label": f"{game.home_team.short_name if fav_sel == 'HOME' else game.away_team.short_name} ML",
                    "market": "MONEYLINE",
                    "label": label,
                    "decimal_odds": american_to_decimal(fav_odds),
                    "american_odds": fav_odds,
                }
            )

        # Spread picks: home team spread
        if odds.spread_home is not None and odds.spread_line is not None:
            spread_picks.append(
                {
                    "game_id": game.pk,
                    "selection": "HOME",
                    "selection_label": f"{game.home_team.short_name} {odds.spread_line:+g}",
                    "market": "SPREAD",
                    "line": odds.spread_line,
                    "label": label,
                    "decimal_odds": american_to_decimal(odds.spread_home),
                    "american_odds": odds.spread_home,
                }
            )

    # Trim to 3-4 legs, sorted by likelihood
    favorites.sort(key=lambda x: x["decimal_odds"])

    return {
        "favorites": favorites[:4],
        "value": spread_picks[:4],
    }


def _game_label(game):
    return f"{game.home_team.short_name} vs {game.away_team.short_name}"


def _nfl_selection_label(market, selection, line=None):
    if market == "MONEYLINE":
        return f"{selection.title()} ML"
    elif market == "SPREAD":
        line_str = f" {line:+g}" if line is not None else ""
        return f"{selection.title()}{line_str}"
    elif market == "TOTAL":
        line_str = f" {line:g}" if line is not None else ""
        return f"{selection.title()}{line_str}"
    return selection
