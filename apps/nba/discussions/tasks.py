"""
Celery tasks for bot comment generation on game discussions.

generate_pregame_comments() runs in the afternoon before tip-off.
generate_postgame_comments() runs late night after games finish.
"""

import logging
import random

import anthropic
from activity.models import ActivityEvent
from bots.models import BotProfile
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from games.models import Game, GameStatus

from discussions.models import Comment

logger = logging.getLogger(__name__)

BOTS_PER_GAME = 3


def _generate_comment_body(persona_prompt: str, context: str) -> str:
    """Call Claude API to generate a game discussion comment."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        system=persona_prompt or "You are a passionate NBA betting fan.",
        messages=[{"role": "user", "content": context}],
    )
    return message.content[0].text.strip()


@shared_task
def generate_pregame_comments():
    """
    For today's scheduled games, generate bot comments with predictions.
    Picks up to BOTS_PER_GAME random bots per game (deduped).
    """
    today = timezone.localdate()
    games = Game.objects.filter(
        status=GameStatus.SCHEDULED, game_date=today
    ).select_related("home_team", "away_team")

    if not games.exists():
        return {"commented": 0, "reason": "no_games"}

    profiles = list(BotProfile.objects.filter(is_active=True).select_related("user"))
    if not profiles:
        return {"commented": 0, "reason": "no_bots"}

    commented = 0
    for game in games:
        random.shuffle(profiles)
        candidates = [
            p
            for p in profiles
            if not Comment.objects.filter(user=p.user, game=game).exists()
        ][:BOTS_PER_GAME]

        matchup = f"{game.away_team.abbreviation} @ {game.home_team.abbreviation}"
        context = (
            f"Tonight's game: {matchup}\n\n"
            "Write a short comment (1-3 sentences) sharing your prediction "
            "or thoughts before tip-off. Stay in character."
        )

        for profile in candidates:
            try:
                body = _generate_comment_body(profile.persona_prompt, context)
            except Exception as exc:
                logger.warning("Bot %s pregame comment failed: %s", profile.user, exc)
                continue

            Comment.objects.create(user=profile.user, game=game, body=body)
            ActivityEvent.objects.create(
                event_type=ActivityEvent.EventType.BOT_COMMENT,
                message=f"{profile.user.display_name} commented on {matchup}",
            )
            commented += 1

    logger.info("generate_pregame_comments: created %d comments", commented)
    return {"commented": commented}


@shared_task
def generate_postgame_comments():
    """
    For today's final games, generate bot reaction comments.
    Picks up to BOTS_PER_GAME random bots per game (deduped).
    """
    today = timezone.localdate()
    games = Game.objects.filter(
        status=GameStatus.FINAL, game_date=today
    ).select_related("home_team", "away_team")

    if not games.exists():
        return {"commented": 0, "reason": "no_games"}

    profiles = list(BotProfile.objects.filter(is_active=True).select_related("user"))
    if not profiles:
        return {"commented": 0, "reason": "no_bots"}

    commented = 0
    for game in games:
        random.shuffle(profiles)
        candidates = [
            p
            for p in profiles
            if not Comment.objects.filter(user=p.user, game=game).exists()
        ][:BOTS_PER_GAME]

        matchup = f"{game.away_team.abbreviation} @ {game.home_team.abbreviation}"
        score = f"{game.away_score}-{game.home_score}"
        winner = game.winner
        winner_name = winner.abbreviation if winner else "TBD"

        context = (
            f"Final score: {matchup} — {score} ({winner_name} wins)\n\n"
            "Write a short comment (1-3 sentences) reacting to this result. "
            "Stay in character."
        )

        for profile in candidates:
            try:
                body = _generate_comment_body(profile.persona_prompt, context)
            except Exception as exc:
                logger.warning("Bot %s postgame comment failed: %s", profile.user, exc)
                continue

            Comment.objects.create(user=profile.user, game=game, body=body)
            ActivityEvent.objects.create(
                event_type=ActivityEvent.EventType.BOT_COMMENT,
                message=f"{profile.user.display_name} reacted to {matchup}",
            )
            commented += 1

    logger.info("generate_postgame_comments: created %d comments", commented)
    return {"commented": commented}
