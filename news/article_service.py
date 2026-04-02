"""
Article generation service for news recaps and weekly roundups.

Follows the same pattern as epl/bots/comment_service.py:
- System prompt = bot personality (persona_prompt)
- User prompt = game data + article writing instructions
- Claude API call with structured response parsing
- Post-hoc filter before publishing
"""

import logging
import re
from datetime import timedelta

import anthropic
from django.conf import settings
from django.db import IntegrityError
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from news.models import NewsArticle
from vinosports.bots.models import BotProfile

logger = logging.getLogger(__name__)

# Claude API settings — same model as comment generation, higher token limit
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 800
ROUNDUP_MAX_TOKENS = 1200  # Roundups are longer (4-6 paragraphs)
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


def generate_weekly_roundup(league):
    """
    Generate a weekly roundup article for a league.

    Aggregates last week's results, standings, and betting trends into a
    prompt for a neutral analyst bot.

    Returns the created NewsArticle, or None if generation failed or no games.
    """
    bot_user = _select_analyst_bot(league)
    if bot_user is None:
        logger.warning("No analyst bot available for roundup: league=%s", league)
        return None

    bot_profile = BotProfile.objects.get(user=bot_user)
    system_prompt = bot_profile.persona_prompt

    # Build roundup prompt with aggregated data
    user_prompt = _build_roundup_prompt(league)
    if user_prompt is None:
        logger.info("No games last week for roundup: league=%s", league)
        return None

    # Call Claude API — roundups get more tokens
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=MODEL,
            max_tokens=ROUNDUP_MAX_TOKENS,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text
    except Exception as exc:
        logger.error("Claude API error for roundup: league=%s, error=%s", league, exc)
        return None

    # Parse structured response
    title, subtitle, body = _parse_article_response(raw_text)

    # Post-hoc filter — roundups start as drafts for admin review
    ok, reason = _filter_article(title, body)
    status = NewsArticle.Status.DRAFT  # Always draft — admin publishes

    try:
        article = NewsArticle.objects.create(
            league=league,
            author=bot_user,
            article_type=NewsArticle.ArticleType.ROUNDUP,
            title=title[:200],
            subtitle=subtitle[:300],
            body=body,
            status=status,
            prompt_used=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            raw_response=raw_text,
        )
    except Exception as exc:
        logger.error("Error creating roundup article: league=%s, error=%s", league, exc)
        return None

    if not ok:
        logger.warning(
            "Roundup filtered (%s): league=%s — saved as draft for review",
            reason,
            league,
        )

    return article


def generate_betting_trend(league):
    """
    Generate a mid-week betting trend article for a league.

    Aggregates recent betting activity — popular markets, win rates,
    cover trends, and top performers — into a prompt for a neutral analyst bot.

    Returns the created NewsArticle, or None if generation failed or no data.
    """
    bot_user = _select_analyst_bot(league)
    if bot_user is None:
        logger.warning("No analyst bot available for trend: league=%s", league)
        return None

    bot_profile = BotProfile.objects.get(user=bot_user)
    system_prompt = bot_profile.persona_prompt

    user_prompt = _build_trend_prompt(league)
    if user_prompt is None:
        logger.info("No betting data for trend: league=%s", league)
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=MODEL,
            max_tokens=ROUNDUP_MAX_TOKENS,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text
    except Exception as exc:
        logger.error("Claude API error for trend: league=%s, error=%s", league, exc)
        return None

    title, subtitle, body = _parse_article_response(raw_text)

    ok, reason = _filter_article(title, body)
    status = NewsArticle.Status.DRAFT  # Always draft — admin publishes

    try:
        article = NewsArticle.objects.create(
            league=league,
            author=bot_user,
            article_type=NewsArticle.ArticleType.TREND,
            title=title[:200],
            subtitle=subtitle[:300],
            body=body,
            status=status,
            prompt_used=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            raw_response=raw_text,
        )
    except Exception as exc:
        logger.error("Error creating trend article: league=%s, error=%s", league, exc)
        return None

    if not ok:
        logger.warning(
            "Trend filtered (%s): league=%s — saved as draft for review",
            reason,
            league,
        )

    return article


def generate_cross_league_article():
    """
    Generate a cross-league weekend preview article.

    Pulls recent results and betting trends from all three leagues into a
    single article. Uses a neutral analyst bot active in any league.

    Returns the created NewsArticle, or None if generation failed or no data.
    """
    bot_user = _select_analyst_bot(None)
    if bot_user is None:
        logger.warning("No bot available for cross-league article")
        return None

    bot_profile = BotProfile.objects.get(user=bot_user)
    system_prompt = bot_profile.persona_prompt

    user_prompt = _build_cross_league_prompt()
    if user_prompt is None:
        logger.info("No data for cross-league article")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=MODEL,
            max_tokens=ROUNDUP_MAX_TOKENS,
            temperature=TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text
    except Exception as exc:
        logger.error("Claude API error for cross-league article: %s", exc)
        return None

    title, subtitle, body = _parse_article_response(raw_text)

    ok, reason = _filter_article(title, body)
    status = NewsArticle.Status.DRAFT  # Always draft — admin publishes

    try:
        article = NewsArticle.objects.create(
            league="",  # cross-league — no single league scope
            author=bot_user,
            article_type=NewsArticle.ArticleType.CROSS_LEAGUE,
            title=title[:200],
            subtitle=subtitle[:300],
            body=body,
            status=status,
            prompt_used=f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}",
            raw_response=raw_text,
        )
    except Exception as exc:
        logger.error("Error creating cross-league article: %s", exc)
        return None

    if not ok:
        logger.warning(
            "Cross-league article filtered (%s) — saved as draft for review",
            reason,
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


def _select_analyst_bot(league):
    """
    Pick a neutral analyst bot for roundups/trends/cross-league articles.

    Prefers bots with no team affiliation for the given league (neutral voice).
    Falls back to any active bot if no unaffiliated bots exist.
    """
    active_flag = LEAGUE_ACTIVE_FLAGS.get(league)
    affiliation_field = LEAGUE_BOT_FIELDS.get(league, (None,))[0]

    filters = {"is_active": True}
    if active_flag:
        filters[active_flag] = True

    active_bots = (
        BotProfile.objects.filter(**filters)
        .exclude(persona_prompt="")
        .select_related("user")
    )

    if not active_bots.exists():
        return None

    # Prefer unaffiliated bots (neutral analyst voice)
    if affiliation_field:
        unaffiliated = active_bots.filter(**{affiliation_field: ""})
        if unaffiliated.exists():
            bot = unaffiliated.order_by("?").first()
            return bot.user

    # Fallback: any active bot
    bot = active_bots.order_by("?").first()
    return bot.user if bot else None


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
            _, spread_text = _spread_result(
                game.home_score,
                game.away_score,
                odds.spread_line,
                game.home_team.abbreviation,
                game.away_team.abbreviation,
            )
            lines.append(f"**Spread result**: {spread_text}")

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
            _, spread_text = _spread_result(
                game.home_score,
                game.away_score,
                odds.spread_line,
                game.home_team.abbreviation,
                game.away_team.abbreviation,
            )
            lines.append(f"**Spread result**: {spread_text}")

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
# Roundup prompt building
# ---------------------------------------------------------------------------


def _build_roundup_prompt(league):
    """Dispatch to league-specific roundup prompt builder."""
    builders = {
        "epl": _build_epl_roundup,
        "nba": _build_nba_roundup,
        "nfl": _build_nfl_roundup,
    }
    return builders[league]()


def _get_last_week_range():
    """Return (start_date, end_date) for the previous Monday-Sunday week."""
    today = timezone.now().date()
    # Monday of this week
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)
    return last_monday, last_sunday


def _build_epl_roundup():
    """Build roundup prompt for EPL — last week's matches, standings, betting."""
    from epl.betting.models import BetSlip
    from epl.matches.models import Match, Standing

    start_date, end_date = _get_last_week_range()

    matches = (
        Match.objects.filter(
            status=Match.Status.FINISHED,
            kickoff__date__gte=start_date,
            kickoff__date__lte=end_date,
        )
        .select_related("home_team", "away_team")
        .prefetch_related("odds")
        .order_by("kickoff")
    )

    if not matches.exists():
        return None

    lines = [
        "You are writing a weekly roundup article for the Premier League on a sports betting platform.",
        "",
        f"**Week of {start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}**",
        "",
        "**Results this week**:",
    ]

    for match in matches:
        result = f"{match.home_team.short_name or match.home_team.name} {match.home_score} - {match.away_team.short_name or match.away_team.name} {match.away_score}"
        odds = match.odds.order_by("-fetched_at").first()
        if odds:
            # Determine result vs odds
            if match.home_score > match.away_score:
                outcome = f"Home win @ {odds.home_win}"
            elif match.away_score > match.home_score:
                outcome = f"Away win @ {odds.away_win}"
            else:
                outcome = f"Draw @ {odds.draw}"
            result += f" ({outcome})"
        lines.append(f"- {result}")

    # Standings snapshot — top 6
    standings = (
        Standing.objects.filter(
            season=str(start_date.year),
        )
        .select_related("team")
        .order_by("position")[:6]
    )

    if standings.exists():
        lines.extend(["", "**Top of the table**:"])
        for s in standings:
            lines.append(
                f"- {s.position}. {s.team.short_name or s.team.name} — {s.points}pts (W{s.won} D{s.drawn} L{s.lost}, GD {s.goal_difference:+d})"
            )

    # Betting stats for the week
    week_bets = BetSlip.objects.filter(
        match__in=matches,
    )
    bet_count = week_bets.count()
    if bet_count:
        won_count = week_bets.filter(status="WON").count()
        lines.extend(
            [
                "",
                f"**Community betting this week**: {bet_count} bets placed, {won_count} winners",
            ]
        )
        # Most popular selections
        popular = (
            week_bets.values("selection")
            .annotate(count=Count("id"))
            .order_by("-count")[:3]
        )
        if popular:
            selections = ", ".join(f"{p['selection']} ({p['count']})" for p in popular)
            lines.append(f"**Popular selections**: {selections}")

    lines.extend(_roundup_format_instructions("Premier League"))
    return "\n".join(lines)


def _build_nba_roundup():
    """Build roundup prompt for NBA — last week's games, standings, betting."""
    from nba.betting.models import BetSlip
    from nba.games.models import Game, GameStatus, Standing

    start_date, end_date = _get_last_week_range()

    games = (
        Game.objects.filter(
            status=GameStatus.FINAL,
            game_date__gte=start_date,
            game_date__lte=end_date,
        )
        .select_related("home_team", "away_team")
        .prefetch_related("odds")
        .order_by("game_date")
    )

    if not games.exists():
        return None

    lines = [
        "You are writing a weekly roundup article for the NBA on a sports betting platform.",
        "",
        f"**Week of {start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}**",
        "",
        "**Results this week**:",
    ]

    covers = 0
    overs = 0
    games_with_spread = 0
    games_with_total = 0

    for game in games:
        result = f"{game.away_team.abbreviation} {game.away_score} @ {game.home_team.abbreviation} {game.home_score}"
        odds = game.odds.order_by("-fetched_at").first()
        details = []
        if odds:
            if odds.spread_line is not None:
                home_covered, spread_text = _spread_result(
                    game.home_score,
                    game.away_score,
                    odds.spread_line,
                    game.home_team.abbreviation,
                    game.away_team.abbreviation,
                )
                details.append(spread_text)
                games_with_spread += 1
                if home_covered is True:
                    covers += 1

            if odds.total_line is not None:
                actual_total = game.home_score + game.away_score
                if actual_total > odds.total_line:
                    details.append(f"OVER {odds.total_line:g}")
                    overs += 1
                elif actual_total < odds.total_line:
                    details.append(f"UNDER {odds.total_line:g}")
                else:
                    details.append(f"PUSH {odds.total_line:g}")
                games_with_total += 1

        if details:
            result += f" ({', '.join(details)})"
        lines.append(f"- {result}")

    # Spread/O-U trends
    if games_with_spread:
        lines.extend(
            [
                "",
                "**Betting trends**:",
                f"- Home teams covering: {covers}/{games_with_spread}",
            ]
        )
    if games_with_total:
        lines.append(f"- Games going over: {overs}/{games_with_total}")

    # Standings snapshot — top 5 per conference
    for conf_label, conf_value in [("Eastern", "EAST"), ("Western", "WEST")]:
        standings = (
            Standing.objects.filter(
                season=start_date.year,
                conference=conf_value,
            )
            .select_related("team")
            .order_by("conference_rank")[:5]
        )
        if standings.exists():
            lines.extend(["", f"**{conf_label} Conference top 5**:"])
            for s in standings:
                streak_str = f" ({s.streak})" if s.streak else ""
                lines.append(
                    f"- {s.conference_rank}. {s.team.abbreviation} — {s.wins}-{s.losses} ({s.win_pct:.3f}){streak_str}"
                )

    # Betting stats for the week
    week_bets = BetSlip.objects.filter(game__in=games)
    bet_count = week_bets.count()
    if bet_count:
        won_count = week_bets.filter(status="WON").count()
        lines.extend(
            [
                "",
                f"**Community betting this week**: {bet_count} bets placed, {won_count} winners",
            ]
        )

    lines.extend(_roundup_format_instructions("NBA"))
    return "\n".join(lines)


def _build_nfl_roundup():
    """Build roundup prompt for NFL — last week's games, standings, betting."""
    from nfl.betting.models import BetSlip, Odds
    from nfl.games.models import Game, GameStatus, Standing

    start_date, end_date = _get_last_week_range()

    games = (
        Game.objects.filter(
            status__in=[GameStatus.FINAL, GameStatus.FINAL_OT],
            game_date__gte=start_date,
            game_date__lte=end_date,
        )
        .select_related("home_team", "away_team")
        .order_by("game_date")
    )

    if not games.exists():
        return None

    # Determine the NFL week from the first game
    first_game = games.first()
    week_label = f"Week {first_game.week}" if first_game.week else "Last week"

    lines = [
        "You are writing a weekly roundup article for the NFL on a sports betting platform.",
        "",
        f"**{week_label} — {start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}**",
        "",
        "**Results this week**:",
    ]

    covers = 0
    overs = 0
    games_with_spread = 0
    games_with_total = 0

    for game in games:
        ot_tag = " (OT)" if game.status == GameStatus.FINAL_OT else ""
        result = f"{game.away_team.abbreviation} {game.away_score} @ {game.home_team.abbreviation} {game.home_score}{ot_tag}"

        odds = Odds.objects.filter(game=game).order_by("-fetched_at").first()
        details = []
        if odds:
            if odds.spread_line is not None:
                home_covered, spread_text = _spread_result(
                    game.home_score,
                    game.away_score,
                    odds.spread_line,
                    game.home_team.abbreviation,
                    game.away_team.abbreviation,
                )
                details.append(spread_text)
                games_with_spread += 1
                if home_covered is True:
                    covers += 1

            if odds.total_line is not None:
                actual_total = game.home_score + game.away_score
                if actual_total > odds.total_line:
                    details.append(f"OVER {odds.total_line:g}")
                    overs += 1
                elif actual_total < odds.total_line:
                    details.append(f"UNDER {odds.total_line:g}")
                else:
                    details.append(f"PUSH {odds.total_line:g}")
                games_with_total += 1

        if details:
            result += f" ({', '.join(details)})"
        lines.append(f"- {result}")

    # Spread/O-U trends
    if games_with_spread:
        lines.extend(
            [
                "",
                "**Betting trends**:",
                f"- Home teams covering: {covers}/{games_with_spread}",
            ]
        )
    if games_with_total:
        lines.append(f"- Games going over: {overs}/{games_with_total}")

    # Division leaders
    standings = (
        Standing.objects.filter(season=start_date.year, division_rank=1)
        .select_related("team")
        .order_by("division")
    )
    if standings.exists():
        lines.extend(["", "**Division leaders**:"])
        for s in standings:
            record = f"{s.wins}-{s.losses}"
            if s.ties:
                record += f"-{s.ties}"
            streak_str = f" ({s.streak})" if s.streak else ""
            lines.append(
                f"- {s.team.abbreviation} ({s.division}) — {record}{streak_str}"
            )

    # Betting stats for the week
    week_bets = BetSlip.objects.filter(game__in=games)
    bet_count = week_bets.count()
    if bet_count:
        won_count = week_bets.filter(status="WON").count()
        lines.extend(
            [
                "",
                f"**Community betting this week**: {bet_count} bets placed, {won_count} winners",
            ]
        )

    lines.extend(_roundup_format_instructions("NFL"))
    return "\n".join(lines)


def _roundup_format_instructions(league_name):
    """Shared instructions appended to every roundup prompt."""
    return [
        "",
        "---",
        "",
        f"Write a weekly roundup article for {league_name} (4-6 paragraphs). Include:",
        "1. A punchy, opinionated headline (on its own line, prefixed with TITLE:)",
        "2. A one-sentence subtitle (on its own line, prefixed with SUBTITLE:)",
        "3. The article body",
        "",
        "Cover the biggest storylines, betting trends, and what to watch next week.",
        "Opinionated and entertaining. Under 600 words.",
    ]


# ---------------------------------------------------------------------------
# Trend prompt building
# ---------------------------------------------------------------------------

# How far back to look for betting trend data
TREND_LOOKBACK_DAYS = 14


def _build_trend_prompt(league):
    """Dispatch to league-specific trend prompt builder."""
    builders = {
        "epl": _build_epl_trend,
        "nba": _build_nba_trend,
        "nfl": _build_nfl_trend,
    }
    return builders[league]()


def _build_betting_stats_section(bet_qs, has_market=True):
    """
    Build shared betting stats lines from a BetSlip queryset.

    Args:
        bet_qs: QuerySet of BetSlip objects (already filtered to time range).
        has_market: True for NBA/NFL (market field), False for EPL (1X2 only).

    Returns list of prompt lines, or empty list if no bets.
    """
    total = bet_qs.count()
    if not total:
        return []

    won = bet_qs.filter(status="WON").count()
    lost = bet_qs.filter(status="LOST").count()
    settled = won + lost

    lines = [
        f"**Total bets placed**: {total}",
        f"**Settled**: {settled} ({won} won, {lost} lost)",
    ]
    if settled:
        lines.append(f"**Overall win rate**: {won / settled * 100:.1f}%")

    # Market breakdown (NBA/NFL only)
    if has_market:
        markets = (
            bet_qs.filter(status__in=["WON", "LOST"])
            .values("market")
            .annotate(
                total=Count("id"),
                wins=Count("id", filter=Q(status="WON")),
            )
            .order_by("-total")
        )
        if markets:
            lines.append("")
            lines.append("**Win rate by market**:")
            for m in markets:
                rate = m["wins"] / m["total"] * 100 if m["total"] else 0
                lines.append(f"- {m['market']}: {m['wins']}/{m['total']} ({rate:.1f}%)")

    # Selection popularity
    popular = (
        bet_qs.values("selection").annotate(count=Count("id")).order_by("-count")[:5]
    )
    if popular:
        lines.append("")
        lines.append("**Most popular selections**:")
        for p in popular:
            lines.append(f"- {p['selection']}: {p['count']} bets")

    return lines


def _build_top_bettors_section():
    """Build lines showing top performers from UserStats."""
    from vinosports.betting.models import UserStats

    lines = []

    # Top by net profit (min 10 bets, exclude bots)
    top_profit = (
        UserStats.objects.filter(total_bets__gte=10, user__is_bot=False)
        .select_related("user")
        .order_by("-net_profit")[:5]
    )
    if top_profit:
        lines.extend(["", "**Top performers (by profit)**:"])
        for s in top_profit:
            lines.append(
                f"- {s.user.display_name}: {s.net_profit:+.0f} coins "
                f"({s.total_wins}W-{s.total_losses}L, {s.win_rate}% win rate)"
            )

    # Hot streaks
    hot_streaks = (
        UserStats.objects.filter(current_streak__gte=3, user__is_bot=False)
        .select_related("user")
        .order_by("-current_streak")[:3]
    )
    if hot_streaks:
        lines.extend(["", "**Hot streaks**:"])
        for s in hot_streaks:
            lines.append(f"- {s.user.display_name}: {s.current_streak}W streak")

    # Cold streaks
    cold_streaks = (
        UserStats.objects.filter(current_streak__lte=-3, user__is_bot=False)
        .select_related("user")
        .order_by("current_streak")[:3]
    )
    if cold_streaks:
        lines.extend(["", "**Cold streaks**:"])
        for s in cold_streaks:
            lines.append(f"- {s.user.display_name}: {abs(s.current_streak)}L streak")

    return lines


def _build_epl_trend():
    """Build trend prompt for EPL — betting activity over the last 2 weeks."""
    from epl.betting.models import BetSlip

    cutoff = timezone.now() - timedelta(days=TREND_LOOKBACK_DAYS)
    recent_bets = BetSlip.objects.filter(created_at__gte=cutoff)

    if not recent_bets.exists():
        return None

    lines = [
        "You are writing a mid-week betting trend article for the Premier League on a sports betting platform.",
        "",
        f"**Betting data from the last {TREND_LOOKBACK_DAYS} days**:",
        "",
    ]

    lines.extend(_build_betting_stats_section(recent_bets, has_market=False))

    # EPL-specific: selection breakdown (Home/Draw/Away win rates)
    selections = (
        recent_bets.filter(status__in=["WON", "LOST"])
        .values("selection")
        .annotate(
            total=Count("id"),
            wins=Count("id", filter=Q(status="WON")),
        )
        .order_by("-total")
    )
    if selections:
        lines.extend(["", "**Win rate by selection**:"])
        for s in selections:
            rate = s["wins"] / s["total"] * 100 if s["total"] else 0
            lines.append(f"- {s['selection']}: {s['wins']}/{s['total']} ({rate:.1f}%)")

    lines.extend(_build_top_bettors_section())
    lines.extend(_trend_format_instructions("Premier League"))
    return "\n".join(lines)


def _build_nba_trend():
    """Build trend prompt for NBA — betting activity over the last 2 weeks."""
    from nba.betting.models import BetSlip

    cutoff = timezone.now() - timedelta(days=TREND_LOOKBACK_DAYS)
    recent_bets = BetSlip.objects.filter(created_at__gte=cutoff)

    if not recent_bets.exists():
        return None

    lines = [
        "You are writing a mid-week betting trend article for the NBA on a sports betting platform.",
        "",
        f"**Betting data from the last {TREND_LOOKBACK_DAYS} days**:",
        "",
    ]

    lines.extend(_build_betting_stats_section(recent_bets, has_market=True))
    lines.extend(_build_top_bettors_section())
    lines.extend(_trend_format_instructions("NBA"))
    return "\n".join(lines)


def _build_nfl_trend():
    """Build trend prompt for NFL — betting activity over the last 2 weeks."""
    from nfl.betting.models import BetSlip

    cutoff = timezone.now() - timedelta(days=TREND_LOOKBACK_DAYS)
    recent_bets = BetSlip.objects.filter(created_at__gte=cutoff)

    if not recent_bets.exists():
        return None

    lines = [
        "You are writing a mid-week betting trend article for the NFL on a sports betting platform.",
        "",
        f"**Betting data from the last {TREND_LOOKBACK_DAYS} days**:",
        "",
    ]

    lines.extend(_build_betting_stats_section(recent_bets, has_market=True))
    lines.extend(_build_top_bettors_section())
    lines.extend(_trend_format_instructions("NFL"))
    return "\n".join(lines)


def _trend_format_instructions(league_name):
    """Shared instructions appended to every trend prompt."""
    return [
        "",
        "---",
        "",
        f"Write a mid-week betting trend article for {league_name} (3-5 paragraphs). Include:",
        "1. A punchy, opinionated headline (on its own line, prefixed with TITLE:)",
        "2. A one-sentence subtitle (on its own line, prefixed with SUBTITLE:)",
        "3. The article body",
        "",
        "Analyze what the betting data reveals — which markets are hot, who's on a streak,",
        "and what the community should watch for. Be opinionated about where the value is.",
        "Under 500 words.",
    ]


# ---------------------------------------------------------------------------
# Cross-league prompt building
# ---------------------------------------------------------------------------


def _build_cross_league_prompt():
    """
    Build a prompt combining data from all three leagues.

    Pulls last week's results and betting activity across EPL, NBA, and NFL
    for a cross-sport weekend preview.
    """
    start_date, end_date = _get_last_week_range()
    sections = []
    has_data = False

    # --- EPL section ---
    epl_section = _build_cross_league_epl_section(start_date, end_date)
    if epl_section:
        sections.append(epl_section)
        has_data = True

    # --- NBA section ---
    nba_section = _build_cross_league_nba_section(start_date, end_date)
    if nba_section:
        sections.append(nba_section)
        has_data = True

    # --- NFL section ---
    nfl_section = _build_cross_league_nfl_section(start_date, end_date)
    if nfl_section:
        sections.append(nfl_section)
        has_data = True

    if not has_data:
        return None

    lines = [
        "You are writing a cross-league weekend preview article for a sports betting platform "
        "that covers the Premier League, NBA, and NFL.",
        "",
        f"**Week of {start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}**",
    ]

    for section in sections:
        lines.extend(["", "---", ""])
        lines.extend(section)

    # Cross-league betting summary
    cross_league_stats = _build_cross_league_betting_summary()
    if cross_league_stats:
        lines.extend(["", "---", ""])
        lines.extend(cross_league_stats)

    lines.extend(_cross_league_format_instructions())
    return "\n".join(lines)


def _build_cross_league_epl_section(start_date, end_date):
    """EPL summary for the cross-league article."""
    try:
        from epl.betting.models import BetSlip
        from epl.matches.models import Match
    except ImportError:
        return None

    matches = (
        Match.objects.filter(
            status=Match.Status.FINISHED,
            kickoff__date__gte=start_date,
            kickoff__date__lte=end_date,
        )
        .select_related("home_team", "away_team")
        .order_by("kickoff")
    )

    if not matches.exists():
        return None

    lines = ["**Premier League**:", ""]

    for match in matches[:8]:  # cap at 8 to keep prompt size reasonable
        home = match.home_team.short_name or match.home_team.name
        away = match.away_team.short_name or match.away_team.name
        lines.append(f"- {home} {match.home_score} - {away} {match.away_score}")

    # Betting summary
    bet_count = BetSlip.objects.filter(match__in=matches).count()
    if bet_count:
        won = BetSlip.objects.filter(match__in=matches, status="WON").count()
        lines.append(f"- Community: {bet_count} bets, {won} winners")

    return lines


def _build_cross_league_nba_section(start_date, end_date):
    """NBA summary for the cross-league article."""
    try:
        from nba.betting.models import BetSlip
        from nba.games.models import Game, GameStatus
    except ImportError:
        return None

    games = (
        Game.objects.filter(
            status=GameStatus.FINAL,
            game_date__gte=start_date,
            game_date__lte=end_date,
        )
        .select_related("home_team", "away_team")
        .order_by("game_date")
    )

    if not games.exists():
        return None

    lines = [f"**NBA** ({games.count()} games):", ""]

    for game in games[:10]:  # cap at 10
        lines.append(
            f"- {game.away_team.abbreviation} {game.away_score} @ "
            f"{game.home_team.abbreviation} {game.home_score}"
        )

    # Betting summary
    bet_count = BetSlip.objects.filter(game__in=games).count()
    if bet_count:
        won = BetSlip.objects.filter(game__in=games, status="WON").count()
        lines.append(f"- Community: {bet_count} bets, {won} winners")

    return lines


def _build_cross_league_nfl_section(start_date, end_date):
    """NFL summary for the cross-league article."""
    try:
        from nfl.betting.models import BetSlip
        from nfl.games.models import Game, GameStatus
    except ImportError:
        return None

    games = (
        Game.objects.filter(
            status__in=[GameStatus.FINAL, GameStatus.FINAL_OT],
            game_date__gte=start_date,
            game_date__lte=end_date,
        )
        .select_related("home_team", "away_team")
        .order_by("game_date")
    )

    if not games.exists():
        return None

    first_game = games.first()
    week_label = f"Week {first_game.week}" if first_game.week else ""
    header = (
        f"**NFL{' — ' + week_label if week_label else ''}** ({games.count()} games):"
    )
    lines = [header, ""]

    for game in games[:16]:  # full NFL slate
        ot_tag = " (OT)" if game.status == GameStatus.FINAL_OT else ""
        lines.append(
            f"- {game.away_team.abbreviation} {game.away_score} @ "
            f"{game.home_team.abbreviation} {game.home_score}{ot_tag}"
        )

    # Betting summary
    bet_count = BetSlip.objects.filter(game__in=games).count()
    if bet_count:
        won = BetSlip.objects.filter(game__in=games, status="WON").count()
        lines.append(f"- Community: {bet_count} bets, {won} winners")

    return lines


def _build_cross_league_betting_summary():
    """Aggregate betting stats across all leagues for the cross-league article."""
    from vinosports.betting.models import UserStats

    lines = ["**Cross-league leaderboard highlights**:"]

    # Top performers across all leagues
    top_profit = (
        UserStats.objects.filter(total_bets__gte=10, user__is_bot=False)
        .select_related("user")
        .order_by("-net_profit")[:3]
    )

    if not top_profit:
        return None

    lines.append("")
    for s in top_profit:
        lines.append(
            f"- {s.user.display_name}: {s.net_profit:+.0f} coins "
            f"({s.total_wins}W-{s.total_losses}L)"
        )

    # Hot streaks
    hot = (
        UserStats.objects.filter(current_streak__gte=3, user__is_bot=False)
        .select_related("user")
        .order_by("-current_streak")[:3]
    )
    if hot:
        lines.extend(["", "**Hot hands**:"])
        for s in hot:
            lines.append(f"- {s.user.display_name}: {s.current_streak}W streak")

    return lines


def _cross_league_format_instructions():
    """Instructions for cross-league weekend preview articles."""
    return [
        "",
        "---",
        "",
        "Write a cross-league weekend preview article (4-6 paragraphs). Include:",
        "1. A punchy, opinionated headline (on its own line, prefixed with TITLE:)",
        "2. A one-sentence subtitle (on its own line, prefixed with SUBTITLE:)",
        "3. The article body",
        "",
        "Connect the dots across leagues — compare betting trends, highlight the biggest ",
        "storylines from each league, and preview what to watch this weekend.",
        "Be opinionated and entertaining. Under 600 words.",
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


def _spread_result(home_score, away_score, spread_line, home_abbr, away_abbr):
    """
    Determine which side covered the spread, or if it was a push.

    spread_line is from the home team's perspective:
    - Negative means home is favored (laying points)
    - Positive means home is underdog (getting points)

    Returns (home_covered, text) where home_covered is True/False/None (push).
    """
    margin = home_score - away_score
    ats_margin = margin + spread_line
    if ats_margin > 0:
        return True, f"{home_abbr} covered"
    elif ats_margin < 0:
        return False, f"{away_abbr} covered"
    return None, "PUSH"


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
