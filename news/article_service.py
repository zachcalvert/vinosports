"""
Article generation service for news recaps.

Follows the same pattern as epl/bots/comment_service.py:
- System prompt = bot personality (persona_prompt)
- User prompt = game data + article writing instructions
- Claude API call with structured response parsing
- Post-hoc filter before publishing
"""

import logging
import re

import anthropic
from django.conf import settings
from django.db import IntegrityError
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from news.models import NewsArticle
from vinosports.bots.models import BotProfile

logger = logging.getLogger(__name__)

# Claude API settings — same model as comment generation, higher token limit
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 800
TEMPERATURE = 0.9

# Post-hoc filter thresholds (wider than comment filter's 10-500)
MIN_BODY_LENGTH = 100
MAX_BODY_LENGTH = 3000
MIN_TITLE_LENGTH = 5
MAX_TITLE_LENGTH = 200

# Same blocklist as epl/bots/comment_service.py
PROFANITY_BLOCKLIST = {
    "fuck",
    "shit",
    "bitch",
    "bastard",
    "asshole",
    "cunt",
    "dick",
    "piss",
    "slut",
    "whore",
    "retard",
    "faggot",
    "nigger",
    "nigga",
    "spic",
    "chink",
    "kike",
}

# Broader than FOOTBALL_KEYWORDS — covers all three leagues
SPORTS_KEYWORDS = {
    "game",
    "match",
    "win",
    "loss",
    "score",
    "goal",
    "goals",
    "point",
    "points",
    "spread",
    "over",
    "under",
    "cover",
    "covered",
    "bet",
    "odds",
    "moneyline",
    "parlay",
    "total",
    "team",
    "half",
    "halftime",
    "quarter",
    "overtime",
    "final",
    "season",
    "playoff",
    "upset",
    "underdog",
    "favorite",
    "line",
    "pick",
    "streak",
    "record",
    "standings",
    "division",
    "conference",
    "league",
    "draw",
    "nil",
    "clean sheet",
    "assist",
    "rebound",
    "turnover",
    "touchdown",
    "field goal",
    "three-pointer",
    "dunk",
    "interception",
    "sack",
    "fumble",
}

# Maps league to (BotProfile affiliation field, Team abbreviation field)
LEAGUE_BOT_FIELDS = {
    "epl": ("epl_team_tla", "tla"),
    "nba": ("nba_team_abbr", "abbreviation"),
    "nfl": ("nfl_team_abbr", "abbreviation"),
}

LEAGUE_ACTIVE_FLAGS = {
    "epl": "active_in_epl",
    "nba": "active_in_nba",
    "nfl": "active_in_nfl",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_game_recap(league, game_obj):
    """
    Generate a game recap article for a completed game.

    Returns the created NewsArticle, or None if generation failed.
    """
    bot_user = _select_recap_bot(league, game_obj)
    if bot_user is None:
        logger.warning(
            "No bot available for recap: league=%s, game=%s", league, game_obj
        )
        return None

    bot_profile = BotProfile.objects.get(user=bot_user)
    system_prompt = bot_profile.persona_prompt
    user_prompt = _build_recap_prompt(league, game_obj, bot_profile)

    # Call Claude API
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text
    except Exception as exc:
        logger.error(
            "Claude API error for recap: league=%s, game=%s, error=%s",
            league,
            game_obj,
            exc,
        )
        return None

    # Parse structured response
    title, subtitle, body = _parse_article_response(raw_text)

    # Post-hoc filter
    ok, reason = _filter_article(title, body)
    status = NewsArticle.Status.PUBLISHED if ok else NewsArticle.Status.DRAFT

    # Create article
    try:
        article = NewsArticle.objects.create(
            league=league,
            author=bot_user,
            article_type=NewsArticle.ArticleType.RECAP,
            title=title[:200],
            subtitle=subtitle[:300],
            body=body,
            game_id_hash=game_obj.id_hash,
            game_url=_get_game_url(league, game_obj),
            game_summary=_format_game_summary(league, game_obj),
            status=status,
            published_at=timezone.now() if ok else None,
            prompt_used=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            raw_response=raw_text,
        )
    except IntegrityError:
        # UniqueConstraint: recap already exists for this game
        logger.info(
            "Recap already exists: league=%s, game=%s", league, game_obj.id_hash
        )
        return None

    if not ok:
        logger.warning(
            "Article filtered (%s): league=%s, game=%s",
            reason,
            league,
            game_obj.id_hash,
        )

    return article


# ---------------------------------------------------------------------------
# Bot selection
# ---------------------------------------------------------------------------


def _select_recap_bot(league, game_obj):
    """
    Pick a bot author for the recap. 3-tier fallback:
    1. Winner's team bot (homer celebrating is entertaining)
    2. Loser's team bot (homer lamenting is also entertaining)
    3. Any active bot for this league
    """
    affiliation_field, team_abbr_field = LEAGUE_BOT_FIELDS[league]
    active_flag = LEAGUE_ACTIVE_FLAGS[league]

    active_bots = (
        BotProfile.objects.filter(is_active=True, **{active_flag: True})
        .exclude(persona_prompt="")
        .select_related("user")
    )

    if not active_bots.exists():
        return None

    # Get team abbreviations
    winner = _get_winner(league, game_obj)
    loser = _get_loser(league, game_obj)

    # Tier 1: winner's team bot
    if winner:
        winner_abbr = getattr(winner, team_abbr_field, "")
        if winner_abbr:
            bot = active_bots.filter(**{affiliation_field: winner_abbr}).first()
            if bot:
                return bot.user

    # Tier 2: loser's team bot
    if loser:
        loser_abbr = getattr(loser, team_abbr_field, "")
        if loser_abbr:
            bot = active_bots.filter(**{affiliation_field: loser_abbr}).first()
            if bot:
                return bot.user

    # Tier 3: any active bot
    bot = active_bots.order_by("?").first()
    return bot.user if bot else None


def _get_winner(league, game_obj):
    """Return the winning team object, or None for draws/ties."""
    if game_obj.home_score is None or game_obj.away_score is None:
        return None
    if game_obj.home_score > game_obj.away_score:
        return game_obj.home_team
    elif game_obj.away_score > game_obj.home_score:
        return game_obj.away_team
    return None  # draw/tie


def _get_loser(league, game_obj):
    """Return the losing team object, or None for draws/ties."""
    winner = _get_winner(league, game_obj)
    if winner is None:
        return None
    if winner == game_obj.home_team:
        return game_obj.away_team
    return game_obj.home_team


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _build_recap_prompt(league, game_obj, bot_profile):
    """Dispatch to league-specific prompt builder."""
    builders = {
        "epl": _build_epl_recap,
        "nba": _build_nba_recap,
        "nfl": _build_nfl_recap,
    }
    return builders[league](game_obj, bot_profile)


def _build_epl_recap(match, bot_profile):
    """Build recap prompt for an EPL match."""
    from epl.matches.models import MatchNotes

    lines = [
        "You are writing a game recap article for a sports betting platform.",
        "",
        f"**Match**: {match.home_team.name} {match.home_score} - {match.away_team.name} {match.away_score} (FINAL)",
        f"**Competition**: Premier League — Matchday {match.matchday}",
        f"**Date**: {match.kickoff.strftime('%A, %B %d, %Y')}",
    ]

    if match.home_team.venue:
        lines.append(f"**Venue**: {match.home_team.venue}")

    # Odds
    odds = match.odds.order_by("-fetched_at").first()
    if odds:
        lines.extend(
            [
                "",
                f"**Odds at kickoff**: {match.home_team.tla} {odds.home_win} | Draw {odds.draw} | {match.away_team.tla} {odds.away_win}",
            ]
        )

    # Game notes
    try:
        notes = MatchNotes.objects.get(match=match)
        if notes.body.strip():
            lines.extend(
                ["", "**Game notes (from a real viewer)**:", notes.body.strip()]
            )
    except MatchNotes.DoesNotExist:
        pass

    # Community betting stats
    bet_count = match.bets.count()
    if bet_count:
        popular = (
            match.bets.values("selection")
            .annotate(count=Count("id"))
            .order_by("-count")
            .first()
        )
        lines.extend(
            [
                "",
                f"**Community betting**: {bet_count} bets placed",
            ]
        )
        if popular:
            lines.append(f"**Most popular selection**: {popular['selection']}")

    # Bot team affiliation context
    if bot_profile.epl_team_tla:
        lines.extend(["", f"**Your team**: {bot_profile.epl_team_tla}"])

    lines.extend(_article_format_instructions())
    return "\n".join(lines)


def _build_nba_recap(game, bot_profile):
    """Build recap prompt for an NBA game."""
    from nba.games.models import GameNotes, Odds

    lines = [
        "You are writing a game recap article for a sports betting platform.",
        "",
        f"**Game**: {game.away_team.name} {game.away_score} @ {game.home_team.name} {game.home_score} (FINAL)",
        f"**Date**: {game.game_date.strftime('%A, %B %d, %Y')}",
    ]

    if game.arena:
        lines.append(f"**Arena**: {game.arena}")

    if game.postseason:
        lines.append("**Postseason game**")

    # Odds
    odds = Odds.objects.filter(game=game).order_by("-fetched_at").first()
    if odds:
        odds_lines = []
        if odds.home_moneyline is not None:
            odds_lines.append(
                f"ML: {game.home_team.abbreviation} {odds.home_moneyline:+d} | "
                f"{game.away_team.abbreviation} {odds.away_moneyline:+d}"
            )
        if odds.spread_line is not None:
            odds_lines.append(
                f"Spread: {game.home_team.abbreviation} {odds.spread_line:+g}"
            )
        if odds.total_line is not None:
            odds_lines.append(f"O/U: {odds.total_line:g}")
        if odds_lines:
            lines.extend(["", f"**Betting lines**: {' | '.join(odds_lines)}"])

        # Spread/total result
        if odds.spread_line is not None and game.home_score is not None:
            margin = game.home_score - game.away_score
            covered_spread = (
                margin > -odds.spread_line
                if odds.spread_line < 0
                else margin > odds.spread_line
            )
            spread_team = (
                game.home_team.abbreviation
                if covered_spread
                else game.away_team.abbreviation
            )
            lines.append(f"**Spread result**: {spread_team} covered")

        if odds.total_line is not None and game.home_score is not None:
            actual_total = game.home_score + game.away_score
            ou_result = (
                "OVER"
                if actual_total > odds.total_line
                else "UNDER"
                if actual_total < odds.total_line
                else "PUSH"
            )
            lines.append(
                f"**O/U result**: {ou_result} ({actual_total} total points, line was {odds.total_line:g})"
            )

    # Game notes
    try:
        notes = GameNotes.objects.get(game=game)
        if notes.body.strip():
            lines.extend(
                ["", "**Game notes (from a real viewer)**:", notes.body.strip()]
            )
    except GameNotes.DoesNotExist:
        pass

    # Community betting stats
    bet_count = game.bets.count()
    if bet_count:
        popular = (
            game.bets.values("selection")
            .annotate(count=Count("id"))
            .order_by("-count")
            .first()
        )
        lines.extend(
            [
                "",
                f"**Community betting**: {bet_count} bets placed",
            ]
        )
        if popular:
            lines.append(f"**Most popular selection**: {popular['selection']}")

    # Bot team affiliation context
    if bot_profile.nba_team_abbr:
        lines.extend(["", f"**Your team**: {bot_profile.nba_team_abbr}"])

    lines.extend(_article_format_instructions())
    return "\n".join(lines)


def _build_nfl_recap(game, bot_profile):
    """Build recap prompt for an NFL game."""
    from nfl.betting.models import Odds
    from nfl.games.models import GameNotes

    lines = [
        "You are writing a game recap article for a sports betting platform.",
        "",
        f"**Game**: {game.away_team.name} {game.away_score} @ {game.home_team.name} {game.home_score} (FINAL{'_OT' if game.status == 'FINAL_OT' else ''})",
        f"**Date**: {game.game_date.strftime('%A, %B %d, %Y')}",
    ]

    if game.week:
        lines.append(f"**Week**: {game.week}")

    if game.venue:
        lines.append(f"**Venue**: {game.venue}")

    # Quarter-by-quarter breakdown
    quarters = []
    for q_label, h_field, a_field in [
        ("Q1", "home_q1", "away_q1"),
        ("Q2", "home_q2", "away_q2"),
        ("Q3", "home_q3", "away_q3"),
        ("Q4", "home_q4", "away_q4"),
    ]:
        h_val = getattr(game, h_field, None)
        a_val = getattr(game, a_field, None)
        if h_val is not None and a_val is not None:
            quarters.append(f"{q_label}: {a_val}-{h_val}")
    if game.home_ot is not None and game.away_ot is not None:
        quarters.append(f"OT: {game.away_ot}-{game.home_ot}")
    if quarters:
        lines.extend(
            ["", f"**Scoring by quarter** (away-home): {' | '.join(quarters)}"]
        )

    # Odds
    odds = Odds.objects.filter(game=game).order_by("-fetched_at").first()
    if odds:
        odds_lines = []
        if odds.home_moneyline is not None:
            odds_lines.append(
                f"ML: {game.home_team.abbreviation} {odds.home_moneyline:+d} | "
                f"{game.away_team.abbreviation} {odds.away_moneyline:+d}"
            )
        if odds.spread_line is not None:
            odds_lines.append(
                f"Spread: {game.home_team.abbreviation} {odds.spread_line:+g}"
            )
        if odds.total_line is not None:
            odds_lines.append(f"O/U: {odds.total_line:g}")
        if odds_lines:
            lines.extend(["", f"**Betting lines**: {' | '.join(odds_lines)}"])

        # Spread/total result
        if odds.spread_line is not None and game.home_score is not None:
            margin = game.home_score - game.away_score
            covered_spread = (
                margin > -odds.spread_line
                if odds.spread_line < 0
                else margin > odds.spread_line
            )
            spread_team = (
                game.home_team.abbreviation
                if covered_spread
                else game.away_team.abbreviation
            )
            lines.append(f"**Spread result**: {spread_team} covered")

        if odds.total_line is not None and game.home_score is not None:
            actual_total = game.home_score + game.away_score
            ou_result = (
                "OVER"
                if actual_total > odds.total_line
                else "UNDER"
                if actual_total < odds.total_line
                else "PUSH"
            )
            lines.append(
                f"**O/U result**: {ou_result} ({actual_total} total points, line was {odds.total_line:g})"
            )

    # Game notes
    try:
        notes = GameNotes.objects.get(game=game)
        if notes.body.strip():
            lines.extend(
                ["", "**Game notes (from a real viewer)**:", notes.body.strip()]
            )
    except GameNotes.DoesNotExist:
        pass

    # Community betting stats
    bet_count = game.bets.count()
    if bet_count:
        popular = (
            game.bets.values("selection")
            .annotate(count=Count("id"))
            .order_by("-count")
            .first()
        )
        lines.extend(
            [
                "",
                f"**Community betting**: {bet_count} bets placed",
            ]
        )
        if popular:
            lines.append(f"**Most popular selection**: {popular['selection']}")

    # Bot team affiliation context
    if bot_profile.nfl_team_abbr:
        lines.extend(["", f"**Your team**: {bot_profile.nfl_team_abbr}"])

    lines.extend(_article_format_instructions())
    return "\n".join(lines)


def _article_format_instructions():
    """Shared instructions appended to every recap prompt."""
    return [
        "",
        "---",
        "",
        "Write a 3-5 paragraph game recap article. Include:",
        "1. A punchy, opinionated headline (on its own line, prefixed with TITLE:)",
        "2. A one-sentence subtitle (on its own line, prefixed with SUBTITLE:)",
        "3. The article body",
        "",
        "Write in your voice — opinionated, entertaining, with betting angles woven in naturally.",
        "Focus on what actually happened in the game, informed by the game notes if available.",
        "Reference the spread/total result where relevant.",
        "Keep it under 500 words.",
    ]


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_article_response(raw_text):
    """
    Extract title, subtitle, and body from structured response.
    Expects TITLE: and SUBTITLE: prefixes. Fallback: first line as title.
    """
    title = ""
    subtitle = ""
    body_lines = []
    in_body = False

    for line in raw_text.strip().split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            title = stripped[6:].strip()
        elif stripped.upper().startswith("SUBTITLE:"):
            subtitle = stripped[9:].strip()
            in_body = True  # body starts after subtitle
        elif in_body or (title and not subtitle and stripped):
            # If we have a title but no subtitle marker, treat everything
            # after the title as body
            body_lines.append(line)
        elif not title and stripped:
            # No TITLE: marker found yet — use first non-empty line
            title = stripped
            in_body = True

    body = "\n".join(body_lines).strip()

    # Fallback: if no title extracted, use first line of body
    if not title and body:
        parts = body.split("\n", 1)
        title = parts[0].strip()
        body = parts[1].strip() if len(parts) > 1 else ""

    return title, subtitle, body


# ---------------------------------------------------------------------------
# Post-hoc filter
# ---------------------------------------------------------------------------


def _filter_article(title, body):
    """
    Lightweight post-hoc filter. Returns (ok, reason).
    Adapted from epl/bots/comment_service.py _filter_comment().
    """
    if len(body) < MIN_BODY_LENGTH:
        return False, "body_too_short"
    if len(body) > MAX_BODY_LENGTH:
        return False, "body_too_long"
    if len(title) < MIN_TITLE_LENGTH:
        return False, "title_too_short"
    if len(title) > MAX_TITLE_LENGTH:
        return False, "title_too_long"

    # Profanity check on combined text
    combined = f"{title} {body}".lower()
    for word in PROFANITY_BLOCKLIST:
        if re.search(rf"\b{re.escape(word)}", combined):
            return False, f"profanity:{word}"

    # Relevance — must contain at least one sports keyword
    has_sports = any(kw in combined for kw in SPORTS_KEYWORDS)
    if not has_sports:
        return False, "irrelevant"

    return True, ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_game_url(league, game_obj):
    """Build the absolute URL for a game detail page."""
    if league == "epl":
        return reverse("epl_matches:match_detail", kwargs={"slug": game_obj.slug})
    elif league == "nba":
        return reverse("nba_games:game_detail", kwargs={"id_hash": game_obj.id_hash})
    elif league == "nfl":
        return reverse("nfl_games:game_detail", kwargs={"id_hash": game_obj.id_hash})
    return ""


def _format_game_summary(league, game_obj):
    """Format a concise game summary string for display."""
    if league == "epl":
        home = game_obj.home_team.short_name or game_obj.home_team.name
        away = game_obj.away_team.short_name or game_obj.away_team.name
    else:
        home = game_obj.home_team.abbreviation
        away = game_obj.away_team.abbreviation
    return f"{away} {game_obj.away_score} - {home} {game_obj.home_score}"
