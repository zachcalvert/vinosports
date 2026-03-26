"""
Odds API client (the-odds-api.com v4) and sync helpers.
"""

import logging
from typing import Any

import httpx
from django.conf import settings

from nba.games.models import Game, Odds, Team

logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
NBA_SPORT_KEY = "basketball_nba"

# Map The Odds API team name → our Team.short_name (sportsdata "City Name" format).
_TEAM_ALIAS: dict[str, str] = {
    "Atlanta Hawks": "Atlanta Hawks",
    "Boston Celtics": "Boston Celtics",
    "Brooklyn Nets": "Brooklyn Nets",
    "Charlotte Hornets": "Charlotte Hornets",
    "Chicago Bulls": "Chicago Bulls",
    "Cleveland Cavaliers": "Cleveland Cavaliers",
    "Dallas Mavericks": "Dallas Mavericks",
    "Denver Nuggets": "Denver Nuggets",
    "Detroit Pistons": "Detroit Pistons",
    "Golden State Warriors": "Golden State Warriors",
    "Houston Rockets": "Houston Rockets",
    "Indiana Pacers": "Indiana Pacers",
    "Los Angeles Clippers": "Los Angeles Clippers",
    "LA Clippers": "Los Angeles Clippers",
    "Los Angeles Lakers": "Los Angeles Lakers",
    "LA Lakers": "Los Angeles Lakers",
    "Memphis Grizzlies": "Memphis Grizzlies",
    "Miami Heat": "Miami Heat",
    "Milwaukee Bucks": "Milwaukee Bucks",
    "Minnesota Timberwolves": "Minnesota Timberwolves",
    "New Orleans Pelicans": "New Orleans Pelicans",
    "New York Knicks": "New York Knicks",
    "Oklahoma City Thunder": "Oklahoma City Thunder",
    "Orlando Magic": "Orlando Magic",
    "Philadelphia 76ers": "Philadelphia 76ers",
    "Phoenix Suns": "Phoenix Suns",
    "Portland Trail Blazers": "Portland Trail Blazers",
    "Sacramento Kings": "Sacramento Kings",
    "San Antonio Spurs": "San Antonio Spurs",
    "Toronto Raptors": "Toronto Raptors",
    "Utah Jazz": "Utah Jazz",
    "Washington Wizards": "Washington Wizards",
}


def _resolve_team_name(name: str) -> str:
    return _TEAM_ALIAS.get(name, name)


class OddsClient:
    """Thin httpx wrapper around The Odds API v4."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.ODDS_API_KEY
        self._client = httpx.Client(base_url=ODDS_API_BASE, timeout=15.0)

    def _get(self, path: str, params: dict | None = None) -> Any:
        params = dict(params or {})
        params["apiKey"] = self.api_key
        response = self._client.get(path, params=params)
        response.raise_for_status()
        remaining = response.headers.get("x-requests-remaining")
        if remaining is not None:
            logger.info("odds-api: %s requests remaining this month", remaining)
        return response.json()

    def get_odds(self) -> list[dict]:
        return self._get(
            f"/sports/{NBA_SPORT_KEY}/odds",
            params={
                "regions": "us",
                "markets": "h2h,spreads,totals",
                "oddsFormat": "american",
            },
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _parse_bookmaker_odds(game_data: dict) -> list[dict]:
    """
    Parse all bookmakers from a single Odds API game object.
    Returns one normalized dict per bookmaker.
    """
    results = []
    for bm in game_data.get("bookmakers", []):
        record: dict[str, Any] = {
            "bookmaker": bm["key"],
            "home_moneyline": None,
            "away_moneyline": None,
            "spread_line": None,
            "spread_home": None,
            "spread_away": None,
            "total_line": None,
            "over_odds": None,
            "under_odds": None,
        }
        home_key = game_data.get("home_team", "")
        away_key = game_data.get("away_team", "")
        for market in bm.get("markets", []):
            outcomes = {o["name"]: o for o in market.get("outcomes", [])}
            if market["key"] == "h2h":
                record["home_moneyline"] = outcomes.get(home_key, {}).get("price")
                record["away_moneyline"] = outcomes.get(away_key, {}).get("price")
            elif market["key"] == "spreads":
                home_o = outcomes.get(home_key, {})
                away_o = outcomes.get(away_key, {})
                record["spread_line"] = home_o.get("point")
                record["spread_home"] = home_o.get("price")
                record["spread_away"] = away_o.get("price")
            elif market["key"] == "totals":
                record["total_line"] = outcomes.get("Over", {}).get("point")
                record["over_odds"] = outcomes.get("Over", {}).get("price")
                record["under_odds"] = outcomes.get("Under", {}).get("price")
        results.append(record)
    return results


def sync_odds(client: OddsClient | None = None) -> int:
    """Fetch current NBA odds and upsert Odds records. Returns count synced."""
    from django.utils import timezone

    with client or OddsClient() as c:
        raw_games = c.get_odds()

    fetched_at = timezone.now()
    team_map = {t.short_name: t for t in Team.objects.all()}
    count = 0

    for game_data in raw_games:
        home_name = _resolve_team_name(game_data.get("home_team", ""))
        away_name = _resolve_team_name(game_data.get("away_team", ""))
        home_team = team_map.get(home_name)
        away_team = team_map.get(away_name)
        if not home_team or not away_team:
            logger.warning(
                "sync_odds: cannot match teams home=%r away=%r", home_name, away_name
            )
            continue

        game = (
            Game.objects.filter(
                home_team=home_team,
                away_team=away_team,
                status__in=("SCHEDULED", "IN_PROGRESS", "HALFTIME"),
            )
            .order_by("game_date")
            .first()
        )
        if not game:
            logger.debug("sync_odds: no open game for %s vs %s", home_name, away_name)
            continue

        for bm_odds in _parse_bookmaker_odds(game_data):
            bookmaker = bm_odds.pop("bookmaker")
            bm_odds["fetched_at"] = fetched_at
            Odds.objects.update_or_create(
                game=game,
                bookmaker=bookmaker,
                defaults=bm_odds,
            )
            count += 1

    logger.info("sync_odds: synced %d odds records", count)
    return count
