"""World Cup bot tasks — strategy execution and comment generation."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_bot_strategies():
    """Hourly dispatcher — check bot schedules and place bets."""
    from vinosports.bots.models import BotProfile

    active_bots = BotProfile.objects.filter(active_in_worldcup=True)
    for bot in active_bots:
        execute_bot_strategy.delay(bot.pk)


@shared_task
def execute_bot_strategy(bot_profile_pk):
    """Execute a single bot's betting strategy for World Cup matches."""
    logger.info("Executing bot strategy for profile %s", bot_profile_pk)


@shared_task
def generate_bot_comment_task(bot_profile_pk, match_pk, trigger_type):
    """Generate and post a bot comment for a World Cup match."""
    logger.info(
        "Generating %s comment for bot %s on match %s",
        trigger_type,
        bot_profile_pk,
        match_pk,
    )


@shared_task
def generate_prematch_comments(bot_user_ids=None):
    """Dispatch pre-match hype comments for upcoming World Cup matches."""
    logger.info("Generating World Cup pre-match comments")


@shared_task
def generate_postmatch_comments(bot_user_ids=None):
    """Dispatch post-match reaction comments for finished World Cup matches."""
    logger.info("Generating World Cup post-match comments")


@shared_task
def generate_featured_parlays():
    """Build themed World Cup parlays for the featured section."""
    logger.info("Generating World Cup featured parlays")
