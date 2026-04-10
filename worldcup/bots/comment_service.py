"""Bot comment generation service for World Cup — thin delegation to centralized pipeline."""

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
from worldcup.bots.adapter import FOOTBALL_KEYWORDS, worldcup_adapter

MAX_REPLIES_PER_MATCH = DEFAULT_MAX_REPLIES
_trim_to_last_sentence = trim_to_last_sentence


def _get_bot_profile(bot_user):
    from vinosports.bots.comment_pipeline import get_bot_profile

    return get_bot_profile(bot_user)


def _filter_comment(text, match):
    home = match.home_team
    away = match.away_team
    team_terms = {
        home.name.lower(),
        away.name.lower(),
        (home.short_name or "").lower(),
        (away.short_name or "").lower(),
        (home.tla or "").lower(),
        (away.tla or "").lower(),
        (home.country_code or "").lower(),
        (away.country_code or "").lower(),
    }
    team_terms.discard("")
    return filter_comment(text, team_terms, FOOTBALL_KEYWORDS)


def _homer_team_mentioned(profile, text):
    return homer_team_mentioned(worldcup_adapter, profile, text)


def _is_bot_relevant(profile, match):
    return worldcup_adapter.is_bot_relevant(profile, match)


def _build_user_prompt(
    match,
    trigger_type,
    bet_slip=None,
    parent_comment=None,
    bot_stats=None,
    target_stats=None,
):
    from reddit.context import build_reddit_context
    from vinosports.bots.comment_pipeline import build_user_prompt

    match_ctx = worldcup_adapter.build_match_context(match)
    reddit_ctx = build_reddit_context("worldcup")
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
    bot_user, match, trigger_type, bet_slip=None, parent_comment=None
):
    return generate_comment(
        worldcup_adapter, bot_user, match, trigger_type, bet_slip, parent_comment
    )


def select_reply_bot(match, target_comment):
    return _core_select_reply(worldcup_adapter, match, target_comment)
