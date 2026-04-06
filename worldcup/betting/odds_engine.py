"""House odds generation for World Cup 1X2 markets."""

import logging
from decimal import Decimal

from django.utils import timezone

from worldcup.matches.models import Match, Odds, Standing

logger = logging.getLogger(__name__)

# Base probabilities for balanced teams
BASE_HOME_PROB = Decimal("0.40")
BASE_DRAW_PROB = Decimal("0.25")
BASE_AWAY_PROB = Decimal("0.35")

# House margin
MARGIN = Decimal("1.08")

# Clamp odds to reasonable range
MIN_ODDS = Decimal("1.10")
MAX_ODDS = Decimal("20.00")


def _team_strength(team):
    """Derive team strength from group standings. Higher = better."""
    standings = Standing.objects.filter(team=team).first()
    if not standings:
        return Decimal("50")
    return Decimal(str(standings.points * 10 + standings.goal_difference + 50))


def _generate_match_odds(match):
    """Generate 1X2 odds for a single match."""
    home_str = _team_strength(match.home_team)
    away_str = _team_strength(match.away_team)
    total = home_str + away_str

    if total == 0:
        home_prob = BASE_HOME_PROB
        draw_prob = BASE_DRAW_PROB
        away_prob = BASE_AWAY_PROB
    else:
        raw_home = home_str / total
        raw_away = away_str / total
        # Blend with base probabilities
        home_prob = (Decimal(str(raw_home)) + BASE_HOME_PROB) / 2
        away_prob = (Decimal(str(raw_away)) + BASE_AWAY_PROB) / 2
        draw_prob = Decimal("1") - home_prob - away_prob
        if draw_prob < Decimal("0.10"):
            draw_prob = Decimal("0.10")
            remainder = Decimal("1") - draw_prob
            home_prob = home_prob / (home_prob + away_prob) * remainder
            away_prob = remainder - home_prob

    # Apply margin and convert to decimal odds
    home_odds = max(MIN_ODDS, min(MAX_ODDS, MARGIN / home_prob))
    draw_odds = max(MIN_ODDS, min(MAX_ODDS, MARGIN / draw_prob))
    away_odds = max(MIN_ODDS, min(MAX_ODDS, MARGIN / away_prob))

    return (
        home_odds.quantize(Decimal("0.01")),
        draw_odds.quantize(Decimal("0.01")),
        away_odds.quantize(Decimal("0.01")),
    )


def generate_all_upcoming_odds():
    """Generate house odds for all upcoming World Cup matches."""
    upcoming = Match.objects.filter(
        status__in=[Match.Status.SCHEDULED, Match.Status.TIMED]
    ).select_related("home_team", "away_team")

    count = 0
    now = timezone.now()
    for match in upcoming:
        home_win, draw, away_win = _generate_match_odds(match)
        Odds.objects.update_or_create(
            match=match,
            bookmaker="Vino House",
            defaults={
                "home_win": home_win,
                "draw": draw,
                "away_win": away_win,
                "fetched_at": now,
            },
        )
        count += 1

    return count
