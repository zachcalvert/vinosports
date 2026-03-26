"""Utilities for generating featured parlay content."""

import json
import logging

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a sports copywriter for VinoSports, a sports betting simulation site. \
Given a parlay (a multi-leg bet), write a catchy title and a one-sentence description.

Rules:
- Return valid JSON: {"title": "...", "description": "..."}
- Title: max 60 characters, punchy, fun. Use sports lingo, wordplay, or alliteration.
- Description: one sentence, max 120 characters. Hype the picks.
- Match the vibe to the theme: "favorites" = confident/chalk, "underdogs" = bold/daring, "value" = smart/savvy.
- Do NOT include odds numbers in the title or description.
- Return ONLY the JSON object, nothing else."""

# Fallback titles when Claude is unavailable
_FALLBACK_TITLES = {
    "favorites": {
        "epl": ("Weekend Chalk", "The safe picks for this matchday."),
        "nba": ("Tonight's Chalk", "Riding the favorites across tonight's slate."),
    },
    "underdogs": {
        "epl": ("Underdog Special", "Bold picks for the brave this weekend."),
        "nba": ("Upset Alert", "Going against the grain tonight."),
    },
    "value": {
        "epl": ("Value Picks", "Smart money for the weekend fixtures."),
        "nba": ("Sharp Plays", "Finding the edges in tonight's lines."),
    },
}


def generate_parlay_copy(
    legs_summary: list[dict],
    league: str,
    theme: str,
) -> dict:
    """Call Claude to generate a title and description for a featured parlay.

    Args:
        legs_summary: [{"event": "Arsenal vs Chelsea", "selection": "Home Win", "odds": "2.10"}, ...]
        league: "epl" or "nba"
        theme: "favorites", "underdogs", or "value"

    Returns:
        {"title": str, "description": str}
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not configured — using fallback copy")
        return _fallback(league, theme)

    legs_text = "\n".join(
        f"- {leg['event']}: {leg['selection']} @ {leg['odds']}" for leg in legs_summary
    )
    prompt = f"League: {league.upper()}\nTheme: {theme}\n\nLegs:\n{legs_text}"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            temperature=0.9,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        result = json.loads(text)
        return {
            "title": str(result.get("title", ""))[:120],
            "description": str(result.get("description", ""))[:300],
        }
    except Exception:
        logger.exception("Featured parlay copy generation failed")
        return _fallback(league, theme)


def _fallback(league: str, theme: str) -> dict:
    """Return a safe fallback title/description."""
    theme_map = _FALLBACK_TITLES.get(theme, _FALLBACK_TITLES["value"])
    title, desc = theme_map.get(league, theme_map.get("epl", ("Featured Parlay", "")))
    return {"title": title, "description": desc}
