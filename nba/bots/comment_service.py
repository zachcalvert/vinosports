"""Bot comment generation service for NBA — thin delegation to centralized pipeline."""

from nba.bots.adapter import BASKETBALL_KEYWORDS, nba_adapter
from vinosports.bots.comment_pipeline import (
    DEFAULT_MAX_REPLIES,
    filter_comment,
    generate_comment,
    homer_team_mentioned,
    trim_to_last_sentence,
)
from vinosports.bots.comment_pipeline import (
    select_reply_bot as _core_select_reply,
)

MAX_REPLIES_PER_GAME = DEFAULT_MAX_REPLIES
_trim_to_last_sentence = trim_to_last_sentence


def _get_bot_profile(bot_user):
    from vinosports.bots.comment_pipeline import get_bot_profile

    return get_bot_profile(bot_user)


def _filter_comment(text, game):
    home = game.home_team
    away = game.away_team
    team_terms = {
        home.name.lower(),
        away.name.lower(),
        (home.short_name or "").lower(),
        (away.short_name or "").lower(),
        (home.abbreviation or "").lower(),
        (away.abbreviation or "").lower(),
    }
    team_terms.discard("")
    return filter_comment(text, team_terms, BASKETBALL_KEYWORDS)


def _homer_team_mentioned(profile, text):
    return homer_team_mentioned(nba_adapter, profile, text)


def _is_bot_relevant(profile, game):
    return nba_adapter.is_bot_relevant(profile, game)


def _build_user_prompt(
    game,
    trigger_type,
    bet_slip=None,
    parent_comment=None,
    bot_stats=None,
    target_stats=None,
):
    from reddit.context import build_reddit_context
    from vinosports.bots.comment_pipeline import build_user_prompt

    match_ctx = nba_adapter.build_match_context(game)
    reddit_ctx = build_reddit_context("nba")
    return build_user_prompt(
        match_ctx,
        trigger_type,
        bet_slip,
        parent_comment,
        bot_stats=bot_stats,
        target_stats=target_stats,
        reddit_context=reddit_ctx,
    )


def generate_bot_comment(
    bot_user, game, trigger_type, bet_slip=None, parent_comment=None
):
    return generate_comment(
        nba_adapter, bot_user, game, trigger_type, bet_slip, parent_comment
    )


def select_reply_bot(game, target_comment):
    return _core_select_reply(nba_adapter, game, target_comment)
