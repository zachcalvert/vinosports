"""Cross-league orchestrator tasks.

Each task fans out to per-league subtasks via .delay(), so a failure
in one league doesn't block others.
"""

import importlib
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

ALL_LEAGUES = ["epl", "nba", "nfl", "worldcup", "ucl"]

# Maps league slug → dotted path to the per-league task function.
ODDS_TASKS = {
    "epl": "epl.betting.tasks.generate_odds",
    "nba": "nba.betting.tasks.generate_odds",
    "nfl": "nfl.betting.tasks.generate_odds",
    "worldcup": "worldcup.betting.tasks.generate_odds",
    "ucl": "ucl.betting.tasks.generate_odds",
}

FUTURES_TASKS = {
    "epl": "epl.betting.tasks.update_futures_odds",
    "nba": "nba.betting.tasks.update_futures_odds",
    "nfl": "nfl.betting.tasks.update_futures_odds",
    "worldcup": "worldcup.betting.tasks.update_futures_odds",
    "ucl": "ucl.betting.tasks.update_futures_odds",
}

BOT_STRATEGY_TASKS = {
    "epl": "epl.bots.tasks.run_bot_strategies",
    "nba": "nba.bots.tasks.run_bot_strategies",
    "nfl": "nfl.bots.tasks.run_bot_strategies",
    "worldcup": "worldcup.bots.tasks.run_bot_strategies",
    "ucl": "ucl.bots.tasks.run_bot_strategies",
}

PREMATCH_COMMENT_TASKS = {
    "epl": "epl.bots.tasks.generate_prematch_comments",
    "nba": "nba.discussions.tasks.generate_pregame_comments",
    "nfl": "nfl.discussions.tasks.generate_pregame_comments",
    "worldcup": "worldcup.bots.tasks.generate_prematch_comments",
    "ucl": "ucl.bots.tasks.generate_prematch_comments",
}

FEATURED_PARLAY_TASKS = {
    "epl": "epl.bots.tasks.generate_featured_parlays",
    "nba": "nba.bots.tasks.generate_featured_parlays",
    "nfl": "nfl.bots.tasks.generate_featured_parlays",
    "worldcup": "worldcup.bots.tasks.generate_featured_parlays",
    "ucl": "ucl.bots.tasks.generate_featured_parlays",
}

FETCH_TEAMS_TASKS = {
    "epl": "epl.matches.tasks.fetch_teams",
    "nba": "nba.games.tasks.fetch_teams",
    "nfl": "nfl.games.tasks.fetch_teams",
    "worldcup": "worldcup.matches.tasks.fetch_teams",
    "ucl": "ucl.matches.tasks.fetch_teams",
}

CLEANUP_ACTIVITY_TASKS = {
    "epl": "epl.activity.tasks.cleanup_old_activity_events",
    "nba": "nba.activity.tasks.cleanup_old_activity_events",
    "nfl": "nfl.activity.tasks.cleanup_old_activity_events",
    "worldcup": "worldcup.activity.tasks.cleanup_old_activity_events",
    "ucl": "ucl.activity.tasks.cleanup_old_activity_events",
}


def _resolve_task(dotted_path):
    """Import and return a task function from a dotted path."""
    module_path, attr = dotted_path.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


def _fan_out(task_map, label):
    """Dispatch per-league tasks, logging any failures."""
    dispatched = 0
    for league, dotted_path in task_map.items():
        try:
            task = _resolve_task(dotted_path)
            task.delay()
            dispatched += 1
        except Exception:
            logger.exception("Failed to dispatch %s for %s", label, league)
    return dispatched


@shared_task(name="vinosports.core.tasks.all_generate_odds")
def all_generate_odds():
    """Fan out odds generation to all leagues."""
    return _fan_out(ODDS_TASKS, "generate_odds")


@shared_task(name="vinosports.core.tasks.all_update_futures_odds")
def all_update_futures_odds():
    """Fan out futures odds update to all leagues."""
    return _fan_out(FUTURES_TASKS, "update_futures_odds")


@shared_task(name="vinosports.core.tasks.all_run_bot_strategies")
def all_run_bot_strategies():
    """Fan out bot strategy execution to all leagues."""
    return _fan_out(BOT_STRATEGY_TASKS, "run_bot_strategies")


@shared_task(name="vinosports.core.tasks.all_generate_prematch_comments")
def all_generate_prematch_comments():
    """Fan out pre-match/pregame comment generation to all leagues."""
    return _fan_out(PREMATCH_COMMENT_TASKS, "generate_prematch_comments")


@shared_task(name="vinosports.core.tasks.all_generate_featured_parlays")
def all_generate_featured_parlays():
    """Fan out featured parlay generation to all leagues."""
    return _fan_out(FEATURED_PARLAY_TASKS, "generate_featured_parlays")


@shared_task(name="vinosports.core.tasks.all_fetch_teams")
def all_fetch_teams():
    """Fan out team roster fetch to all leagues."""
    return _fan_out(FETCH_TEAMS_TASKS, "fetch_teams")


@shared_task(name="vinosports.core.tasks.all_cleanup_activity_events")
def all_cleanup_activity_events():
    """Fan out activity event cleanup to all leagues."""
    return _fan_out(CLEANUP_ACTIVITY_TASKS, "cleanup_old_activity_events")
