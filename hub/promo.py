import logging
import re

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a judge for a sports betting simulation site called VinoSports. \
Users enter a promo code when signing up. Your job is to rate the creativeness \
of the promo code and assign a bonus token amount.

Rules:
- Return ONLY a single integer between 25000 and 100000
- 25000 = generic/boring (e.g., "test", "promo", "abc123")
- 50000 = decent effort (e.g., "ParlaKing", "BetBoss2024")
- 75000 = creative and fun (e.g., "HedgeFundOfOne", "DegenerateScholar")
- 100000 = exceptional creativity, humor, or sports reference (e.g., "VinoVeritasVictory", "LeBronzeAge")
- Sports references, wordplay, and humor should score higher
- Generic words, simple numbers, or keyboard mashing should score lower
- Return ONLY the number, nothing else"""


def evaluate_promo_code(code: str) -> int:
    """Send a promo code to Claude and return a bonus token amount (25000-100000).

    Returns 0 if the API call fails or the response can't be parsed.
    """
    api_key = settings.ANTHROPIC_API_KEY
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not configured — skipping promo evaluation")
        return 0

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            temperature=0.7,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Rate this promo code: {code}"}],
        )
        text = response.content[0].text.strip()
        match = re.search(r"\d+", text)
        if not match:
            logger.warning("Could not parse promo score from response: %s", text)
            return 0
        score = int(match.group())
        return max(25000, min(100000, score))
    except Exception:
        logger.exception("Promo code evaluation failed for code: %s", code)
        return 0
