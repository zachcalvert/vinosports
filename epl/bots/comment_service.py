"""Bot comment generation service — thin delegation to centralized pipeline.

All shared logic lives in vinosports.bots.comment_pipeline. This module
preserves the original function signatures so that epl/bots/tasks.py and
tests continue to work without changes.
"""

from epl.bots.adapter import BOT_REPLY_AFFINITIES, FOOTBALL_KEYWORDS, epl_adapter
from vinosports.bots.comment_pipeline import (
    DEFAULT_MAX_REPLIES,
    PROFANITY_BLOCKLIST,
    _homer_team_cache,  # noqa: F401 — tests clear this between runs
    filter_comment,
    generate_comment,
    homer_team_mentioned,
    select_bots_for_event,
    trim_to_last_sentence,
)
from vinosports.bots.comment_pipeline import (
    select_reply_bot as _core_select_reply,
)

# Re-export constants used by tests
MAX_REPLIES_PER_MATCH = DEFAULT_MAX_REPLIES

# Keep private names importable for tests that reference them directly
_trim_to_last_sentence = trim_to_last_sentence


def _get_bot_profile(bot_user):
    from vinosports.bots.comment_pipeline import get_bot_profile

    return get_bot_profile(bot_user)


def _filter_comment(text, match):
    """Legacy signature: accepts a match object, extracts team terms."""
    home = match.home_team
    away = match.away_team
    team_terms = {
        home.name.lower(),
        away.name.lower(),
        (home.short_name or "").lower(),
        (away.short_name or "").lower(),
        (home.tla or "").lower(),
        (away.tla or "").lower(),
    }
    team_terms.discard("")
    return filter_comment(text, team_terms, FOOTBALL_KEYWORDS)


def _homer_team_mentioned(profile, text):
    """Legacy signature: delegates to core with EPL adapter."""
    return homer_team_mentioned(epl_adapter, profile, text)


def _is_bot_relevant(profile, match, match_odds=None):
    """Legacy signature: delegates to adapter."""
    return epl_adapter.is_bot_relevant(profile, match, match_odds)


def _build_user_prompt(
    match,
    trigger_type,
    bet_slip=None,
    parent_comment=None,
    bot_stats=None,
    target_stats=None,
):
    """Legacy signature: builds MatchContext then delegates to core."""
    from reddit.context import build_reddit_context
    from vinosports.bots.comment_pipeline import build_user_prompt

    match_ctx = epl_adapter.build_match_context(match)
    reddit_ctx = build_reddit_context("epl")
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
    """Generate and post an LLM-powered comment for a bot user."""
    return generate_comment(
        epl_adapter, bot_user, match, trigger_type, bet_slip, parent_comment
    )


def select_bots_for_match(match, trigger_type, max_bots=2, exclude_user_ids=None):
    """Pick up to max_bots relevant bots for a match + trigger."""
    return select_bots_for_event(
        epl_adapter, match, trigger_type, max_bots, exclude_user_ids
    )


def select_reply_bot(match, target_comment):
    """Pick a bot to reply to the given comment, or None."""
    return _core_select_reply(epl_adapter, match, target_comment)


# Re-export for any code that imports these from here
__all__ = [
    "BOT_REPLY_AFFINITIES",
    "FOOTBALL_KEYWORDS",
    "MAX_REPLIES_PER_MATCH",
    "PROFANITY_BLOCKLIST",
    "generate_bot_comment",
    "select_bots_for_match",
    "select_reply_bot",
]
