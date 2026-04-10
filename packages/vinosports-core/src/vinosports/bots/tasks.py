"""Shared Celery tasks for bot social interactions.

These tasks use the LeagueAdapter pattern so they work for any league.
"""

import logging
import random

from celery import shared_task
from django.contrib.auth import get_user_model

from vinosports.bots.models import BotProfile

User = get_user_model()
logger = logging.getLogger(__name__)


def _get_adapter(league):
    """Import and return the adapter for a league slug."""
    adapters = {
        "epl": "epl.bots.adapter.epl_adapter",
        "nba": "nba.bots.adapter.nba_adapter",
        "nfl": "nfl.bots.adapter.nfl_adapter",
        "ucl": "ucl.bots.adapter.ucl_adapter",
        "worldcup": "worldcup.bots.adapter.worldcup_adapter",
    }
    dotted = adapters.get(league)
    if not dotted:
        raise ValueError(f"Unknown league: {league}")
    module_path, attr = dotted.rsplit(".", 1)
    import importlib

    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


@shared_task(name="vinosports.bots.tasks.spark_conversation")
def spark_conversation(bot_user_id, leagues):
    """Orchestrate a bet-then-conversation sequence for a single bot.

    1. Find an upcoming match/game with odds (tries each league in order)
    2. Place a bet via the bot's strategy (falls back to random bet if strategy is empty)
    3. Post a POST_BET comment
    4. Pick a second bot to reply (with social/curiosity prompt)
    5. The reply pipeline handles question detection → life update → response

    Args:
        bot_user_id: PK of the bot user.
        leagues: List of league slugs to try, in order of preference.

    Designed to be triggered from the BotProfile admin action.
    """
    try:
        bot_user = User.objects.get(pk=bot_user_id, is_bot=True, is_active=True)
    except User.DoesNotExist:
        return f"bot {bot_user_id} not found"

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return "no profile"

    # Step 1: Try each league until we place a bet or find an upcoming event
    event = None
    bet_slip = None
    league = None
    adapter = None

    for try_league in leagues:
        try_adapter = _get_adapter(try_league)
        ev, bs = _place_bet_for_league(try_adapter, try_league, bot_user)
        if ev:
            event, bet_slip, league, adapter = ev, bs, try_league, try_adapter
            break
        logger.debug(
            "Spark: no events in %s for %s, trying next",
            try_league,
            bot_user.display_name,
        )

    # Fallback: if no bet was placed, find any upcoming event and do PRE_MATCH
    if not event:
        for try_league in leagues:
            try_adapter = _get_adapter(try_league)
            ev = _find_any_upcoming_event(try_adapter, try_league)
            if ev:
                event, league, adapter = ev, try_league, try_adapter
                break

    if not event:
        tried = ", ".join(leagues)
        return f"no upcoming events (tried: {tried})"

    # Step 2: Post a comment (POST_BET if we have a bet, PRE_MATCH otherwise)
    from vinosports.bots.comment_pipeline import generate_comment

    trigger = "POST_BET" if bet_slip else "PRE_MATCH"
    comment = generate_comment(adapter, bot_user, event, trigger, bet_slip=bet_slip)
    if not comment:
        return "comment generation failed (dedup or filter)"

    logger.info(
        "Spark: %s %s on %s (%s): %r",
        bot_user.display_name,
        "bet and commented" if bet_slip else "commented (no bet)",
        event,
        league,
        comment.body[:60],
    )

    # Step 3: Pick a second bot to reply (staggered delay)
    _dispatch_social_reply(adapter, league, event, comment, exclude_user_id=bot_user.pk)

    return f"sparked: {bot_user.display_name} bet on {event} ({league}), comment posted"


@shared_task(name="vinosports.bots.tasks.social_reply")
def social_reply(bot_user_id, league, event_id, parent_comment_id):
    """Generate a social reply from one bot to another's comment.

    Uses build_conversation_reply for full thread context and social prompts.
    The life update trigger in post-processing handles question → response.
    """
    adapter = _get_adapter(league)
    CommentModel = adapter.get_comment_model()
    fk_name = adapter.get_event_fk_name()

    try:
        bot_user = User.objects.get(pk=bot_user_id, is_bot=True, is_active=True)
    except User.DoesNotExist:
        return "bot not found"

    try:
        parent = CommentModel.objects.select_related("user").get(pk=parent_comment_id)
    except CommentModel.DoesNotExist:
        return "parent comment not found"

    # Resolve the event
    event = getattr(parent, fk_name)

    # Get thread context
    thread_comments = list(
        CommentModel.objects.filter(**{fk_name: event})
        .select_related("user")
        .order_by("created_at")[:20]
    )

    from vinosports.bots.comment_pipeline import build_conversation_reply

    comment = build_conversation_reply(
        adapter, bot_user, event, thread_comments, parent
    )
    if not comment:
        return "reply failed (filter or error)"

    logger.info(
        "Social reply: %s → %r",
        bot_user.display_name,
        comment.body[:60],
    )
    return f"replied: {comment.body[:60]}"


def _find_any_upcoming_event(_adapter, league):
    """Find any upcoming event with odds, without placing a bet."""
    if league == "epl":
        from epl.bots.services import get_best_odds_map
        from epl.matches.models import Match

        matches = Match.objects.filter(
            status__in=["SCHEDULED", "TIMED"]
        ).select_related("home_team", "away_team")
        if not matches.exists():
            return None
        match_ids = list(matches.values_list("pk", flat=True))
        odds_map = get_best_odds_map(match_ids)
        with_odds = [m for m in matches if m.pk in odds_map]
        return random.choice(with_odds) if with_odds else None
    elif league == "nba":
        from nba.games.models import Game, GameStatus

        games = Game.objects.filter(status=GameStatus.SCHEDULED).select_related(
            "home_team", "away_team"
        )
        return games.first()
    elif league == "nfl":
        from nfl.games.models import Game, GameStatus

        games = Game.objects.filter(status=GameStatus.SCHEDULED).select_related(
            "home_team", "away_team"
        )
        return games.first()
    elif league == "ucl":
        from ucl.matches.models import Match

        matches = Match.objects.filter(
            status__in=["SCHEDULED", "TIMED"]
        ).select_related("home_team", "away_team")
        return matches.first()
    elif league == "worldcup":
        from worldcup.matches.models import Match

        matches = Match.objects.filter(
            status__in=["SCHEDULED", "TIMED"]
        ).select_related("home_team", "away_team")
        return matches.first()
    return None


def _place_bet_for_league(adapter, league, bot_user):
    """Place a single bet for a bot on an upcoming event.

    Returns (event, bet_slip) or (None, None) if no suitable event found.
    """
    if league == "epl":
        return _place_epl_bet(bot_user)
    elif league == "nba":
        return _place_nba_bet(bot_user)
    elif league == "nfl":
        return _place_nfl_bet(bot_user)
    elif league == "ucl":
        return _place_ucl_bet(bot_user)
    elif league == "worldcup":
        return _place_worldcup_bet(bot_user)
    return None, None


def _place_epl_bet(bot_user):
    from epl.bots.registry import get_strategy_for_bot
    from epl.bots.services import (
        get_available_matches_for_bot,
        get_best_odds_map,
        maybe_topup_bot,
        place_bot_bet,
    )

    maybe_topup_bot(bot_user)
    available = get_available_matches_for_bot(bot_user)
    if not available.exists():
        return None, None

    match_ids = list(available.values_list("pk", flat=True))
    odds_map = get_best_odds_map(match_ids)
    if not odds_map:
        return None, None

    strategy = get_strategy_for_bot(bot_user)
    if not strategy:
        return None, None

    from vinosports.betting.models import UserBalance

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    picks = strategy.pick_bets(available, odds_map, balance)

    if picks:
        pick = picks[0]
        from epl.matches.models import Match

        match = Match.objects.get(pk=pick.match_id)
        bet_slip = place_bot_bet(bot_user, pick.match_id, pick.selection, pick.stake)
        if bet_slip:
            return match, bet_slip

    # Fallback: strategy returned nothing (e.g. homer bot's team not playing).
    # Pick a random match with odds and place a simple home/away bet.
    match_with_odds = [m for m in available if m.pk in odds_map]
    if not match_with_odds:
        return None, None

    match = random.choice(match_with_odds)
    odds = odds_map[match.pk]
    # Pick the side with better odds (the favorite)
    selection = (
        "HOME_WIN"
        if odds.get("home_win", 99) < odds.get("away_win", 99)
        else "AWAY_WIN"
    )
    from decimal import Decimal

    stake = min(int(balance * Decimal("0.02")), 500)  # 2% of balance, max 500
    bet_slip = place_bot_bet(bot_user, match.pk, selection, stake)
    if not bet_slip:
        return None, None

    return match, bet_slip


def _place_nba_bet(bot_user):
    from nba.bots.services import maybe_topup_bot, place_bot_bets
    from nba.bots.strategies import STRATEGY_MAP
    from nba.games.models import Game, GameStatus, Odds
    from nba.games.services import today_et
    from vinosports.betting.models import UserBalance
    from vinosports.bots.models import BotProfile

    maybe_topup_bot(bot_user)

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return None, None

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    games = Game.objects.filter(status=GameStatus.SCHEDULED, game_date=today_et())
    if not games.exists():
        return None, None

    odds_qs = (
        Odds.objects.filter(game__in=games)
        .select_related("game", "game__home_team", "game__away_team")
        .order_by("game_id", "-fetched_at")
        .distinct("game_id")
    )

    strategy_cls = STRATEGY_MAP.get(profile.strategy_type)
    if not strategy_cls:
        return None, None

    strategy = strategy_cls(profile, balance)
    picks = strategy.pick_bets(odds_qs)
    if not picks:
        return None, None

    pick = picks[0]
    result = place_bot_bets(bot_user, [pick])
    if not result or result.get("placed", 0) == 0:
        return None, None

    # Get the bet slip that was just created
    from nba.betting.models import BetSlip

    bet_slip = BetSlip.objects.filter(user=bot_user).order_by("-created_at").first()
    if not bet_slip:
        return None, None
    return bet_slip.game, bet_slip


def _place_nfl_bet(bot_user):
    from nfl.bots.services import maybe_topup_bot, place_bot_bets
    from nfl.bots.strategies import STRATEGY_MAP
    from nfl.games.models import Game, GameStatus, Odds
    from vinosports.betting.models import UserBalance
    from vinosports.bots.models import BotProfile

    maybe_topup_bot(bot_user)

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return None, None

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    games = Game.objects.filter(status=GameStatus.SCHEDULED)
    if not games.exists():
        return None, None

    odds_qs = (
        Odds.objects.filter(game__in=games)
        .select_related("game", "game__home_team", "game__away_team")
        .order_by("game_id", "-fetched_at")
        .distinct("game_id")
    )

    strategy_cls = STRATEGY_MAP.get(profile.strategy_type)
    if not strategy_cls:
        return None, None

    strategy = strategy_cls(profile, balance)
    picks = strategy.pick_bets(odds_qs)
    if not picks:
        return None, None

    pick = picks[0]
    result = place_bot_bets(bot_user, [pick])
    if not result or result.get("placed", 0) == 0:
        return None, None

    from nfl.betting.models import BetSlip

    bet_slip = BetSlip.objects.filter(user=bot_user).order_by("-created_at").first()
    if not bet_slip:
        return None, None
    return bet_slip.game, bet_slip


def _place_ucl_bet(bot_user):
    from ucl.betting.models import BetSlip
    from ucl.bots.strategies import STRATEGY_MAP
    from ucl.matches.models import Match, Odds
    from vinosports.betting.models import UserBalance
    from vinosports.bots.models import BotProfile

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return None, None

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    matches = Match.objects.filter(status__in=["SCHEDULED", "TIMED"])
    if not matches.exists():
        return None, None

    odds_qs = (
        Odds.objects.filter(match__in=matches)
        .select_related("match__home_team", "match__away_team")
        .order_by("match_id", "-fetched_at")
        .distinct("match_id")
    )

    strategy_cls = STRATEGY_MAP.get(profile.strategy_type)
    if not strategy_cls:
        return None, None

    strategy = strategy_cls(profile, balance)
    picks = strategy.pick_bets(odds_qs)
    if not picks:
        return None, None

    pick = picks[0]
    try:
        match = Match.objects.get(pk=pick.match_id)
        odds_row = match.odds.order_by("-fetched_at").first()
        if not odds_row:
            return None, None

        odds_map = {
            BetSlip.Selection.HOME_WIN: odds_row.home_win,
            BetSlip.Selection.DRAW: odds_row.draw,
            BetSlip.Selection.AWAY_WIN: odds_row.away_win,
        }
        decimal_odds = odds_map.get(pick.selection)
        if decimal_odds is None:
            return None, None

        bet_slip = BetSlip.objects.create(
            user=bot_user,
            match=match,
            selection=pick.selection,
            odds_at_placement=decimal_odds,
            stake=pick.stake,
        )
        return match, bet_slip
    except Exception:
        logger.exception("Failed to place UCL bet for %s", bot_user.display_name)
        return None, None


def _place_worldcup_bet(bot_user):
    from vinosports.betting.models import UserBalance
    from vinosports.bots.models import BotProfile
    from worldcup.betting.models import BetSlip
    from worldcup.bots.strategies import STRATEGY_MAP
    from worldcup.matches.models import Match, Odds

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return None, None

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    matches = Match.objects.filter(status__in=["SCHEDULED", "TIMED"])
    if not matches.exists():
        return None, None

    odds_qs = (
        Odds.objects.filter(match__in=matches)
        .select_related("match__home_team", "match__away_team")
        .order_by("match_id", "-fetched_at")
        .distinct("match_id")
    )

    strategy_cls = STRATEGY_MAP.get(profile.strategy_type)
    if not strategy_cls:
        return None, None

    strategy = strategy_cls(profile, balance)
    picks = strategy.pick_bets(odds_qs)
    if not picks:
        return None, None

    pick = picks[0]
    try:
        match = Match.objects.get(pk=pick.match_id)
        odds_row = match.odds.order_by("-fetched_at").first()
        if not odds_row:
            return None, None

        odds_map = {
            BetSlip.Selection.HOME_WIN: odds_row.home_win,
            BetSlip.Selection.DRAW: odds_row.draw,
            BetSlip.Selection.AWAY_WIN: odds_row.away_win,
        }
        decimal_odds = odds_map.get(pick.selection)
        if decimal_odds is None:
            return None, None

        bet_slip = BetSlip.objects.create(
            user=bot_user,
            match=match,
            selection=pick.selection,
            odds_at_placement=decimal_odds,
            stake=pick.stake,
        )
        return match, bet_slip
    except Exception:
        logger.exception("Failed to place worldcup bet for %s", bot_user.display_name)
        return None, None


def _dispatch_social_reply(adapter, league, event, comment, exclude_user_id):
    """Pick a second bot and dispatch a social reply with a staggered delay."""
    from vinosports.bots.comment_pipeline import select_reply_bot

    bot = select_reply_bot(adapter, event, comment)
    if not bot:
        # Fallback: pick any relevant bot that isn't the author
        from vinosports.bots.comment_pipeline import pick_conversation_bots

        bots = pick_conversation_bots(adapter, event, count=3)
        bots = [b for b in bots if b.pk != exclude_user_id]
        if not bots:
            logger.info("Spark: no reply candidate found for %s", event)
            return
        bot = random.choice(bots)

    delay = random.randint(120, 300)  # 2-5 min
    social_reply.apply_async(
        args=[bot.pk, league, event.pk, comment.pk],
        countdown=delay,
    )
    logger.info(
        "Spark: dispatched social reply from %s in %ds",
        bot.display_name,
        delay,
    )
