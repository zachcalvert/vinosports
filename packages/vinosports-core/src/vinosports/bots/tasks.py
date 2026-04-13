"""Shared Celery tasks for bot social interactions.

These tasks use the LeagueAdapter pattern so they work for any league.
"""

import importlib
import logging
import random
from decimal import Decimal

from celery import shared_task
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import F

from epl.bots.registry import get_strategy_for_bot
from epl.bots.services import (
    get_available_matches_for_bot,
    get_best_odds_map,
    maybe_topup_bot,
    place_bot_bet,
)
from epl.matches.models import Match as EplMatch
from nba.betting.models import BetSlip as NbaBetSlip
from nba.games.models import (
    Game as NbaGame,
)
from nba.games.models import (
    GameStatus as NbaGameStatus,
)
from nba.games.models import (
    Odds as NbaOdds,
)
from news.models import NewsArticle
from nfl.betting.models import BetSlip as NflBetSlip
from nfl.betting.models import Odds as NflOdds
from nfl.bots.services import place_bot_bets
from nfl.bots.strategies import STRATEGY_MAP
from nfl.games.models import Game as NflGame
from nfl.games.models import GameStatus as NflGameStatus
from ucl.betting.models import BetSlip as UclBetSlip
from ucl.matches.models import Match as UclMatch
from ucl.matches.models import Odds as UclOdds
from vinosports.betting.balance import log_transaction
from vinosports.betting.models import (
    Bailout,
    BalanceTransaction,
    Bankruptcy,
    PropBet,
    PropBetSlip,
    PropBetStatus,
    UserBalance,
)
from vinosports.bots.comment_pipeline import (
    build_conversation_reply,
    generate_comment,
    pick_conversation_bots,
    select_reply_bot,
)
from vinosports.bots.models import BotProfile, StrategyType
from vinosports.reactions.models import ArticleReaction, CommentReaction
from worldcup.betting.models import BetSlip as WcBetSlip
from worldcup.matches.models import Match as WcMatch
from worldcup.matches.models import Odds as WcOdds

User = get_user_model()
logger = logging.getLogger(__name__)

# Strategy types that favor the "favorite" side (lower odds)
_FAVORITE_STRATEGIES = {
    StrategyType.FRONTRUNNER,
    StrategyType.HOMER,
    StrategyType.DRAW_SPECIALIST,
}

# Strategy types that favor the "underdog" side (higher odds)
_UNDERDOG_STRATEGIES = {
    StrategyType.UNDERDOG,
    StrategyType.CHAOS_AGENT,
    StrategyType.ALL_IN_ALICE,
}


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
        matches = EplMatch.objects.filter(
            status__in=["SCHEDULED", "TIMED"]
        ).select_related("home_team", "away_team")
        if not matches.exists():
            return None
        match_ids = list(matches.values_list("pk", flat=True))
        odds_map = get_best_odds_map(match_ids)
        with_odds = [m for m in matches if m.pk in odds_map]
        return random.choice(with_odds) if with_odds else None
    elif league == "nba":
        games = NbaGame.objects.filter(status=NbaGameStatus.SCHEDULED).select_related(
            "home_team", "away_team"
        )
        return games.first()
    elif league == "nfl":
        games = NflGame.objects.filter(status=NflGameStatus.SCHEDULED).select_related(
            "home_team", "away_team"
        )
        return games.first()
    elif league == "ucl":
        matches = UclMatch.objects.filter(
            status__in=["SCHEDULED", "TIMED"]
        ).select_related("home_team", "away_team")
        return matches.first()
    elif league == "worldcup":
        matches = WcMatch.objects.filter(
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

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    picks = strategy.pick_bets(available, odds_map, balance)

    if picks:
        pick = picks[0]
        match = EplMatch.objects.get(pk=pick.match_id)
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
    from nba.games.services import today_et

    maybe_topup_bot(bot_user)

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return None, None

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    games = NbaGame.objects.filter(status=NbaGameStatus.SCHEDULED, game_date=today_et())
    if not games.exists():
        return None, None

    odds_qs = (
        NbaOdds.objects.filter(game__in=games)
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
    bet_slip = NbaBetSlip.objects.filter(user=bot_user).order_by("-created_at").first()
    if not bet_slip:
        return None, None
    return bet_slip.game, bet_slip


def _place_nfl_bet(bot_user):
    maybe_topup_bot(bot_user)

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return None, None

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    games = NflGame.objects.filter(status=NflGameStatus.SCHEDULED)
    if not games.exists():
        return None, None

    odds_qs = (
        NflOdds.objects.filter(game__in=games)
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

    bet_slip = NflBetSlip.objects.filter(user=bot_user).order_by("-created_at").first()
    if not bet_slip:
        return None, None
    return bet_slip.game, bet_slip


def _place_ucl_bet(bot_user):
    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return None, None

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    matches = UclMatch.objects.filter(status__in=["SCHEDULED", "TIMED"])
    if not matches.exists():
        return None, None

    odds_qs = (
        UclOdds.objects.filter(match__in=matches)
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
        match = UclMatch.objects.get(pk=pick.match_id)
        odds_row = match.odds.order_by("-fetched_at").first()
        if not odds_row:
            return None, None

        odds_map = {
            UclBetSlip.Selection.HOME_WIN: odds_row.home_win,
            UclBetSlip.Selection.DRAW: odds_row.draw,
            UclBetSlip.Selection.AWAY_WIN: odds_row.away_win,
        }
        decimal_odds = odds_map.get(pick.selection)
        if decimal_odds is None:
            return None, None

        bet_slip = UclBetSlip.objects.create(
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
    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return None, None

    try:
        balance = UserBalance.objects.get(user=bot_user).balance
    except UserBalance.DoesNotExist:
        return None, None

    matches = WcMatch.objects.filter(status__in=["SCHEDULED", "TIMED"])
    if not matches.exists():
        return None, None

    odds_qs = (
        WcOdds.objects.filter(match__in=matches)
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
        match = WcMatch.objects.get(pk=pick.match_id)
        odds_row = match.odds.order_by("-fetched_at").first()
        if not odds_row:
            return None, None

        odds_map = {
            WcBetSlip.Selection.HOME_WIN: odds_row.home_win,
            WcBetSlip.Selection.DRAW: odds_row.draw,
            WcBetSlip.Selection.AWAY_WIN: odds_row.away_win,
        }
        decimal_odds = odds_map.get(pick.selection)
        if decimal_odds is None:
            return None, None

        bet_slip = WcBetSlip.objects.create(
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


# ---------------------------------------------------------------------------
# Prop bet bot betting
# ---------------------------------------------------------------------------


def _ensure_bot_has_balance(bot_user, min_balance=Decimal("5000.00")):
    """League-agnostic bailout for bots with low balance."""
    try:
        balance = UserBalance.objects.get(user=bot_user)
    except UserBalance.DoesNotExist:
        return

    if balance.balance >= min_balance:
        return

    with transaction.atomic():
        balance = UserBalance.objects.select_for_update().get(user=bot_user)
        if balance.balance >= min_balance:
            return

        bankruptcy = Bankruptcy.objects.create(
            user=bot_user,
            balance_at_bankruptcy=balance.balance,
        )
        amount = Decimal(str(random.randint(100000, 300000)))
        Bailout.objects.create(
            user=bot_user,
            bankruptcy=bankruptcy,
            amount=amount,
        )
        log_transaction(
            balance,
            amount,
            BalanceTransaction.Type.BAILOUT,
            "Bot bailout (prop bet)",
        )
    logger.info(
        "Topped up bot %s with %s for prop betting", bot_user.display_name, amount
    )


def _pick_prop_selection(profile, yes_odds, no_odds):
    """Choose YES or NO based on the bot's strategy type and prop odds."""
    # Determine which side is the "favorite" (lower odds = higher implied probability)
    favorite = "YES" if yes_odds <= no_odds else "NO"
    underdog = "NO" if favorite == "YES" else "YES"

    if profile.strategy_type in _FAVORITE_STRATEGIES:
        return favorite
    if profile.strategy_type in _UNDERDOG_STRATEGIES:
        return underdog

    # Everyone else: weighted random based on implied probability
    # implied_prob = 1 / decimal_odds
    yes_prob = float(1 / yes_odds)
    no_prob = float(1 / no_odds)
    total = yes_prob + no_prob
    return "YES" if random.random() < (yes_prob / total) else "NO"


def _pick_prop_stake(balance, risk_multiplier):
    """Choose a stake for a prop bet: 1-3% of balance, scaled by risk multiplier."""
    pct = random.uniform(0.01, 0.03) * risk_multiplier
    stake = (balance * Decimal(str(pct))).quantize(Decimal("1"))
    return max(Decimal("10"), min(stake, Decimal("2000")))


@shared_task(name="vinosports.bots.tasks.place_bot_prop_bets")
def place_bot_prop_bets(prop_id):
    """Dispatch 3-5 bots to bet on a newly created prop bet."""
    try:
        prop = PropBet.objects.get(pk=prop_id)
    except PropBet.DoesNotExist:
        return f"prop {prop_id} not found"

    if prop.status != PropBetStatus.OPEN:
        return f"prop {prop_id} not open"

    # Pick 3-5 random active bots, excluding the creator
    bots = list(
        BotProfile.objects.filter(user__is_active=True)
        .exclude(user=prop.creator)
        .select_related("user")
    )
    if not bots:
        return "no active bots"

    count = min(random.randint(3, 5), len(bots))
    chosen = random.sample(bots, count)

    for i, profile in enumerate(chosen):
        delay = random.randint(5, 30) + (i * random.randint(10, 30))
        place_single_bot_prop_bet.apply_async(
            args=[profile.user_id, prop_id],
            countdown=delay,
        )
        logger.info(
            "Dispatched prop bet for %s on '%s' in %ds",
            profile.user.display_name,
            prop.title[:40],
            delay,
        )

    return f"dispatched {count} bots for prop '{prop.title[:40]}'"


@shared_task(name="vinosports.bots.tasks.place_single_bot_prop_bet")
def place_single_bot_prop_bet(bot_user_id, prop_id):
    """Place a single bot's bet on a prop bet."""
    try:
        bot_user = User.objects.get(pk=bot_user_id, is_bot=True, is_active=True)
    except User.DoesNotExist:
        return f"bot {bot_user_id} not found"

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return "no profile"

    try:
        prop = PropBet.objects.get(pk=prop_id)
    except PropBet.DoesNotExist:
        return f"prop {prop_id} not found"

    if prop.status != PropBetStatus.OPEN:
        return f"prop {prop_id} not open"

    # Skip if bot already bet on this prop
    if PropBetSlip.objects.filter(user=bot_user, prop=prop).exists():
        return f"{bot_user.display_name} already bet on this prop"

    _ensure_bot_has_balance(bot_user)

    selection = _pick_prop_selection(profile, prop.yes_odds, prop.no_odds)
    odds_val = prop.yes_odds if selection == "YES" else prop.no_odds

    try:
        with transaction.atomic():
            balance = UserBalance.objects.select_for_update().get(user=bot_user)
            stake = _pick_prop_stake(balance.balance, profile.risk_multiplier)

            if balance.balance < stake:
                return f"{bot_user.display_name} insufficient balance"

            log_transaction(
                balance,
                -stake,
                BalanceTransaction.Type.BET_PLACEMENT,
                f"Bet on prop: {prop.title}",
            )

            PropBetSlip.objects.create(
                user=bot_user,
                prop=prop,
                selection=selection,
                odds=odds_val,
                stake=stake,
            )

            if selection == "YES":
                PropBet.objects.filter(pk=prop.pk).update(
                    total_stake_yes=F("total_stake_yes") + stake
                )
            else:
                PropBet.objects.filter(pk=prop.pk).update(
                    total_stake_no=F("total_stake_no") + stake
                )

    except UserBalance.DoesNotExist:
        return f"{bot_user.display_name} no balance record"

    logger.info(
        "Bot %s bet %s on prop '%s' (%s @ %s, stake=%s)",
        bot_user.display_name,
        selection,
        prop.title[:40],
        selection,
        odds_val,
        stake,
    )
    return f"{bot_user.display_name} bet {selection} on '{prop.title[:40]}'"


def _dispatch_social_reply(adapter, league, event, comment, exclude_user_id):
    """Pick a second bot and dispatch a social reply with a staggered delay."""
    bot = select_reply_bot(adapter, event, comment)
    if not bot:
        # Fallback: pick any relevant bot that isn't the author

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


# ---------------------------------------------------------------------------
# Bot Reactions
# ---------------------------------------------------------------------------

# Positive-only reaction weights: (thumbs_up, party_cup)
# Bots are upbeat by default — thumbs_down is only used situationally.
_POSITIVE_WEIGHTS = {
    "frontrunner": (75, 25),
    "underdog": (60, 40),
    "spread_shark": (80, 20),
    "parlay": (60, 40),
    "total_guru": (70, 30),
    "draw_specialist": (60, 40),
    "value_hunter": (75, 25),
    "chaos_agent": (40, 60),
    "all_in_alice": (45, 55),
    "homer": (70, 30),
    "anti_homer": (65, 35),
}
_DEFAULT_POSITIVE_WEIGHTS = (65, 35)
_POSITIVE_CHOICES = ["thumbs_up", "party_cup"]


def _pick_positive_reaction(strategy_type):
    """Pick a positive reaction type (thumbs_up or party_cup)."""
    weights = _POSITIVE_WEIGHTS.get(strategy_type, _DEFAULT_POSITIVE_WEIGHTS)
    return random.choices(_POSITIVE_CHOICES, weights=weights, k=1)[0]


def _bot_team_lost(profile, comment_obj):
    """Check if the bot's favourite team lost the game/match this comment is on.

    Returns True if the game is finished and the bot's team lost.
    Returns False if no team affiliation, game not finished, or team didn't lose.
    """
    # Determine the game/match from the comment
    event = getattr(comment_obj, "match", None) or getattr(comment_obj, "game", None)
    if not event:
        return False

    # Need home/away teams with scores
    home_team = getattr(event, "home_team", None)
    away_team = getattr(event, "away_team", None)
    if not home_team or not away_team:
        return False

    home_score = getattr(event, "home_score", None)
    away_score = getattr(event, "away_score", None)
    if home_score is None or away_score is None:
        return False

    # Check if the game is finished
    status = str(getattr(event, "status", "")).upper()
    if status not in ("FINISHED", "FINAL", "FINAL_OT", "FT"):
        return False

    # Determine which TLA/abbreviation field to check based on app_label
    app_label = type(event)._meta.app_label
    tla_field_map = {
        "epl_matches": ("epl_team_tla", "tla"),
        "nba_games": ("nba_team_abbr", "abbreviation"),
        "nfl_games": ("nfl_team_abbr", "abbreviation"),
        "worldcup_matches": ("worldcup_team_tla", "tla"),
        "ucl_matches": ("ucl_team_tla", "tla"),
    }
    mapping = tla_field_map.get(app_label)
    if not mapping:
        return False

    bot_tla_field, team_tla_field = mapping
    bot_tla = getattr(profile, bot_tla_field, "")
    if not bot_tla:
        return False

    home_tla = getattr(home_team, team_tla_field, "")
    away_tla = getattr(away_team, team_tla_field, "")

    if bot_tla == home_tla and home_score < away_score:
        return True
    if bot_tla == away_tla and away_score < home_score:
        return True

    return False


def _bot_team_lost_article(profile, article):
    """Check if the bot's favourite team lost the game referenced by a recap article.

    Only applies to recap articles with a game_id_hash.
    """
    if article.article_type != "recap" or not article.game_id_hash:
        return False

    league = article.league
    if not league:
        return False

    # Look up the game/match by id_hash
    league_model_map = {
        "epl": ("epl.matches.models", "Match"),
        "nba": ("nba.games.models", "Game"),
        "nfl": ("nfl.games.models", "Game"),
        "worldcup": ("worldcup.matches.models", "Match"),
        "ucl": ("ucl.matches.models", "Match"),
    }
    model_info = league_model_map.get(league)
    if not model_info:
        return False

    module_path, class_name = model_info
    try:
        module = importlib.import_module(module_path)
        model_class = getattr(module, class_name)
        event = model_class.objects.select_related("home_team", "away_team").get(
            id_hash=article.game_id_hash
        )
    except Exception:
        return False

    # Reuse the same logic — create a fake "comment-like" wrapper isn't needed,
    # just inline the check
    home_score = getattr(event, "home_score", None)
    away_score = getattr(event, "away_score", None)
    if home_score is None or away_score is None:
        return False

    status = str(getattr(event, "status", "")).upper()
    if status not in ("FINISHED", "FINAL", "FINAL_OT", "FT"):
        return False

    tla_field_map = {
        "epl": ("epl_team_tla", "tla"),
        "nba": ("nba_team_abbr", "abbreviation"),
        "nfl": ("nfl_team_abbr", "abbreviation"),
        "worldcup": ("worldcup_team_tla", "tla"),
        "ucl": ("ucl_team_tla", "tla"),
    }
    bot_tla_field, team_tla_field = tla_field_map[league]
    bot_tla = getattr(profile, bot_tla_field, "")
    if not bot_tla:
        return False

    home_tla = getattr(event.home_team, team_tla_field, "")
    away_tla = getattr(event.away_team, team_tla_field, "")

    if bot_tla == home_tla and home_score < away_score:
        return True
    if bot_tla == away_tla and away_score < home_score:
        return True

    return False


@shared_task(name="vinosports.bots.tasks.dispatch_bot_comment_reactions")
def dispatch_bot_comment_reactions(content_type_id, object_id, author_user_id):
    """Dispatch 2-6 bots to react to a comment."""
    bots = list(
        BotProfile.objects.filter(user__is_active=True)
        .exclude(user_id=author_user_id)
        .select_related("user")
    )
    if not bots:
        return "no active bots"

    count = min(random.randint(2, 6), len(bots))
    chosen = random.sample(bots, count)

    for i, profile in enumerate(chosen):
        delay = random.randint(10, 60) + (i * random.randint(5, 15))
        react_as_bot_to_comment.apply_async(
            args=[profile.user_id, content_type_id, object_id],
            countdown=delay,
        )
        logger.info(
            "Dispatched reaction from %s on comment %s/%s in %ds",
            profile.user.display_name,
            content_type_id,
            object_id,
            delay,
        )

    return f"dispatched {count} bot reactions for comment {content_type_id}/{object_id}"


@shared_task(name="vinosports.bots.tasks.react_as_bot_to_comment")
def react_as_bot_to_comment(bot_user_id, content_type_id, object_id, force_type=None):
    """Single bot reacts to a comment.

    Args:
        force_type: If set, use this reaction type instead of picking one.
                    Used for pile-on downvotes triggered by human thumbs_down.
    """
    try:
        bot_user = User.objects.get(pk=bot_user_id, is_bot=True, is_active=True)
    except User.DoesNotExist:
        return f"bot {bot_user_id} not found"

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return "no profile"

    # Verify the comment still exists
    try:
        ct = ContentType.objects.get(pk=content_type_id)
        model_class = ct.model_class()
        if model_class is None:
            return "invalid content type"
        comment_obj = model_class.objects.select_related(
            "match__home_team",
            "match__away_team",
            "game__home_team",
            "game__away_team",
        ).get(pk=object_id)
    except (ContentType.DoesNotExist, model_class.DoesNotExist):
        return "comment not found"
    except Exception:
        # select_related fields may not exist on all comment models — fall back
        try:
            comment_obj = model_class.objects.get(pk=object_id)
        except model_class.DoesNotExist:
            return "comment not found"

    # Skip if bot already reacted
    if CommentReaction.objects.filter(
        user=bot_user, content_type_id=content_type_id, object_id=object_id
    ).exists():
        return f"{bot_user.display_name} already reacted"

    if force_type:
        reaction_type = force_type
    elif _bot_team_lost(profile, comment_obj):
        reaction_type = "thumbs_down"
    else:
        reaction_type = _pick_positive_reaction(profile.strategy_type)

    CommentReaction.objects.create(
        user=bot_user,
        content_type_id=content_type_id,
        object_id=object_id,
        reaction_type=reaction_type,
    )

    logger.info(
        "Bot %s reacted %s on comment %s/%s",
        bot_user.display_name,
        reaction_type,
        content_type_id,
        object_id,
    )
    return f"{bot_user.display_name} reacted {reaction_type}"


@shared_task(name="vinosports.bots.tasks.dispatch_bot_article_reactions")
def dispatch_bot_article_reactions(article_id, author_user_id=None):
    """Dispatch 2-6 bots to react to a news article."""
    bots = list(BotProfile.objects.filter(user__is_active=True).select_related("user"))
    if author_user_id:
        bots = [b for b in bots if b.user_id != author_user_id]
    if not bots:
        return "no active bots"

    count = min(random.randint(2, 6), len(bots))
    chosen = random.sample(bots, count)

    for i, profile in enumerate(chosen):
        delay = random.randint(10, 60) + (i * random.randint(5, 15))
        react_as_bot_to_article.apply_async(
            args=[profile.user_id, article_id],
            countdown=delay,
        )
        logger.info(
            "Dispatched reaction from %s on article %s in %ds",
            profile.user.display_name,
            article_id,
            delay,
        )

    return f"dispatched {count} bot reactions for article {article_id}"


@shared_task(name="vinosports.bots.tasks.react_as_bot_to_article")
def react_as_bot_to_article(bot_user_id, article_id):
    """Single bot reacts to a news article."""
    try:
        bot_user = User.objects.get(pk=bot_user_id, is_bot=True, is_active=True)
    except User.DoesNotExist:
        return f"bot {bot_user_id} not found"

    profile = BotProfile.objects.filter(user=bot_user).first()
    if not profile:
        return "no profile"

    try:
        article = NewsArticle.objects.get(pk=article_id)
    except NewsArticle.DoesNotExist:
        return f"article {article_id} not found"

    # Skip if bot already reacted
    if ArticleReaction.objects.filter(user=bot_user, article_id=article_id).exists():
        return f"{bot_user.display_name} already reacted"

    if _bot_team_lost_article(profile, article):
        reaction_type = "thumbs_down"
    else:
        reaction_type = _pick_positive_reaction(profile.strategy_type)

    ArticleReaction.objects.create(
        user=bot_user,
        article_id=article_id,
        reaction_type=reaction_type,
    )

    logger.info(
        "Bot %s reacted %s on article %s",
        bot_user.display_name,
        reaction_type,
        article_id,
    )
    return f"{bot_user.display_name} reacted {reaction_type}"


@shared_task(name="vinosports.bots.tasks.dispatch_bot_pile_on_downvotes")
def dispatch_bot_pile_on_downvotes(content_type_id, object_id, downvoter_user_id):
    """Dispatch 1-3 bots to pile on with thumbs_down after a human downvotes."""
    # Exclude the downvoter and any bots that already reacted
    already_reacted = set(
        CommentReaction.objects.filter(
            content_type_id=content_type_id, object_id=object_id
        ).values_list("user_id", flat=True)
    )
    exclude_ids = already_reacted | {downvoter_user_id}

    bots = list(
        BotProfile.objects.filter(user__is_active=True)
        .exclude(user_id__in=exclude_ids)
        .select_related("user")
    )
    if not bots:
        return "no available bots for pile-on"

    count = min(random.randint(1, 3), len(bots))
    chosen = random.sample(bots, count)

    for i, profile in enumerate(chosen):
        delay = random.randint(5, 30) + (i * random.randint(5, 15))
        react_as_bot_to_comment.apply_async(
            args=[profile.user_id, content_type_id, object_id],
            kwargs={"force_type": "thumbs_down"},
            countdown=delay,
        )
        logger.info(
            "Pile-on: dispatched thumbs_down from %s on comment %s/%s in %ds",
            profile.user.display_name,
            content_type_id,
            object_id,
            delay,
        )

    return f"dispatched {count} pile-on downvotes"
