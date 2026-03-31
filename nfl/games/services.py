"""
NFL data API client (BallDontLie) and sync helpers.

All public methods return normalized dicts that map directly to model fields.
Status strings from the API are normalized to GameStatus choices here.
"""

import logging
import time
import zoneinfo
from collections import defaultdict
from datetime import date, datetime
from typing import Any

import httpx
from django.conf import settings

from nfl.games.models import (
    DIVISION_MAP,
    Division,
    Game,
    GameStatus,
    Player,
    Standing,
    Team,
)

_ET = zoneinfo.ZoneInfo("America/New_York")

logger = logging.getLogger(__name__)

BDL_BASE = "https://api.balldontlie.io/nfl/v1"

# BDL status strings observed from the API.
# In-progress statuses are assumed based on NBA patterns — to be verified
# when live games are available.
_STATUS_MAP = {
    "Final": GameStatus.FINAL,
    "Final/OT": GameStatus.FINAL_OT,
    "Halftime": GameStatus.HALFTIME,
    "1st Quarter": GameStatus.IN_PROGRESS,
    "2nd Quarter": GameStatus.IN_PROGRESS,
    "3rd Quarter": GameStatus.IN_PROGRESS,
    "4th Quarter": GameStatus.IN_PROGRESS,
    "Overtime": GameStatus.IN_PROGRESS,
}


def today_et() -> date:
    """Return today's date in Eastern Time (matches how game_date is stored)."""
    return datetime.now(_ET).date()


def _normalize_status(raw: str) -> str:
    """Convert BDL status string to GameStatus."""
    if raw in _STATUS_MAP:
        return _STATUS_MAP[raw]
    return GameStatus.SCHEDULED


def _normalize_division(conference: str, division: str) -> str:
    """Map BDL conference + division to our Division enum."""
    return DIVISION_MAP.get((conference, division), Division.AFC_EAST)


class NFLDataClient:
    """Thin httpx wrapper around the BallDontLie NFL v1 API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.BDL_API_KEY
        self._client = httpx.Client(
            base_url=BDL_BASE,
            headers={"Authorization": self.api_key},
            timeout=15.0,
        )

    def _get(self, path: str, params: dict | None = None) -> Any:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def _get_all(
        self, path: str, params: dict | None = None, page_delay: float = 0
    ) -> list[dict]:
        """Paginate through all results for a list endpoint.

        Retries with exponential backoff on 429 Too Many Requests.

        Args:
            page_delay: Seconds to sleep between paginated requests.
                        Use 1-2s for bulk backfills to avoid 429s.
        """
        params = dict(params or {})
        params["per_page"] = 100
        results = []
        while True:
            data = self._get_with_retry(path, params=params)
            results.extend(data.get("data", []))
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
            params["cursor"] = cursor
            if page_delay:
                time.sleep(page_delay)
        return results

    def _get_with_retry(
        self, path: str, params: dict | None = None, max_retries: int = 5
    ) -> Any:
        """GET with retry on 429 (rate limit) responses."""
        for attempt in range(max_retries + 1):
            try:
                return self._get(path, params=params)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 or attempt == max_retries:
                    raise
                wait = 2**attempt
                logger.info(
                    "Rate limited on %s, retrying in %ds (attempt %d/%d)",
                    path,
                    wait,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(wait)

    # --- Public data methods ---

    def get_teams(self) -> list[dict]:
        """Return all 32 NFL teams, normalized."""
        raw = self._get_all("/teams")
        return [self._normalize_team(t) for t in raw]

    def get_games(
        self,
        season: int,
        week: int | None = None,
        game_date: date | None = None,
        page_delay: float = 0,
    ) -> list[dict]:
        """Return games for a season, optionally filtered by week or date.

        Args:
            page_delay: Seconds to sleep between paginated requests.
                        Use 1-2s for bulk backfills to avoid 429s.
        """
        params: dict[str, Any] = {"seasons[]": season}
        if week is not None:
            params["weeks[]"] = week
        if game_date:
            params["dates[]"] = game_date.isoformat()
        raw = self._get_all("/games", params=params, page_delay=page_delay)
        return [self._normalize_game(g) for g in raw]

    def get_players(
        self,
        page_delay: float = 0,
        on_page=None,
    ) -> list[dict]:
        """Return all players, normalized.

        Args:
            page_delay: Seconds to sleep between paginated requests.
                        Recommended ~12s on free tier (5 req/min).
            on_page: Optional callback(total_fetched) called after each page.
        """
        params: dict[str, Any] = {"per_page": 100}
        raw: list[dict] = []
        while True:
            data = self._get_with_retry("/players", params=params)
            raw.extend(data.get("data", []))
            if on_page:
                on_page(len(raw))
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
            params["cursor"] = cursor
            if page_delay:
                time.sleep(page_delay)
        return [self._normalize_player(p) for p in raw]

    # --- Normalizers ---

    def _normalize_team(self, t: dict) -> dict:
        conference = t.get("conference", "")
        division_raw = t.get("division", "")
        return {
            "external_id": t["id"],
            "name": t.get("full_name", ""),
            "short_name": t.get("name", ""),
            "abbreviation": t.get("abbreviation", ""),
            "location": t.get("location", ""),
            "conference": conference,
            "division": _normalize_division(conference, division_raw),
        }

    def _normalize_game(self, g: dict) -> dict:
        raw_dt = g.get("date", "")
        kickoff = None
        game_date = raw_dt[:10] if raw_dt else ""
        if raw_dt and "T" in raw_dt:
            try:
                kickoff = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                game_date = kickoff.astimezone(_ET).date().isoformat()
            except ValueError:
                pass
        return {
            "external_id": g["id"],
            "home_team_external_id": g["home_team"]["id"],
            "away_team_external_id": g["visitor_team"]["id"],
            "home_score": g.get("home_team_score"),
            "away_score": g.get("visitor_team_score"),
            "status": _normalize_status(g.get("status", "")),
            "game_date": game_date,
            "kickoff": kickoff,
            "season": g.get("season"),
            "week": g.get("week"),
            "postseason": g.get("postseason", False),
            "venue": g.get("venue") or "",
            # Quarter scores
            "home_q1": g.get("home_team_q1"),
            "home_q2": g.get("home_team_q2"),
            "home_q3": g.get("home_team_q3"),
            "home_q4": g.get("home_team_q4"),
            "home_ot": g.get("home_team_ot"),
            "away_q1": g.get("visitor_team_q1"),
            "away_q2": g.get("visitor_team_q2"),
            "away_q3": g.get("visitor_team_q3"),
            "away_q4": g.get("visitor_team_q4"),
            "away_ot": g.get("visitor_team_ot"),
        }

    def _normalize_player(self, p: dict) -> dict:
        team = p.get("team")
        weight_raw = p.get("weight")
        try:
            weight = int(weight_raw) if weight_raw else None
        except (ValueError, TypeError):
            weight = None
        experience_raw = p.get("experience")
        try:
            experience = int(experience_raw) if experience_raw else None
        except (ValueError, TypeError):
            experience = None
        age_raw = p.get("age")
        try:
            age = int(age_raw) if age_raw else None
        except (ValueError, TypeError):
            age = None
        return {
            "external_id": p["id"],
            "first_name": p.get("first_name", ""),
            "last_name": p.get("last_name", ""),
            "position": p.get("position") or "",
            "position_abbreviation": p.get("position_abbreviation") or "",
            "height": p.get("height") or "",
            "weight": weight,
            "jersey_number": p.get("jersey_number") or "",
            "college": p.get("college") or "",
            "experience": experience,
            "age": age,
            "team_external_id": team["id"] if team else None,
        }

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# --- Sync helpers ---


def sync_teams(client: NFLDataClient | None = None) -> int:
    """Upsert all NFL teams. Returns count synced."""
    with client or NFLDataClient() as c:
        teams = c.get_teams()
    count = 0
    for t in teams:
        Team.objects.update_or_create(
            external_id=t.pop("external_id"),
            defaults=t,
        )
        count += 1
    logger.info("sync_teams: synced %d teams", count)
    return count


def sync_games(
    season: int,
    week: int | None = None,
    client: NFLDataClient | None = None,
    page_delay: float = 0,
) -> int:
    """Upsert games for a season (or single week). Returns count synced."""
    with client or NFLDataClient() as c:
        games = c.get_games(season, week=week, page_delay=page_delay)

    count = 0
    for g in games:
        home_id = g.pop("home_team_external_id")
        away_id = g.pop("away_team_external_id")
        external_id = g.pop("external_id")
        try:
            home_team = Team.objects.get(external_id=home_id)
            away_team = Team.objects.get(external_id=away_id)
        except Team.DoesNotExist:
            logger.warning(
                "sync_games: unknown team external_id home=%s away=%s", home_id, away_id
            )
            continue
        g["home_team"] = home_team
        g["away_team"] = away_team
        Game.objects.update_or_create(external_id=external_id, defaults=g)
        count += 1
    logger.info("sync_games: synced %d games (season=%s, week=%s)", count, season, week)
    return count


def sync_players(
    client: NFLDataClient | None = None,
    page_delay: float = 0,
    on_page=None,
) -> int:
    """Upsert all players from BDL. Returns count synced."""
    with client or NFLDataClient() as c:
        players = c.get_players(page_delay=page_delay, on_page=on_page)

    team_ext_ids = {p["team_external_id"] for p in players if p["team_external_id"]}
    teams_by_ext = {
        t.external_id: t for t in Team.objects.filter(external_id__in=team_ext_ids)
    }

    count = 0
    for p in players:
        fields = dict(p)
        team_ext_id = fields.pop("team_external_id")
        fields["team"] = teams_by_ext.get(team_ext_id)
        fields["is_active"] = fields["team"] is not None
        Player.objects.update_or_create(
            external_id=fields.pop("external_id"),
            defaults=fields,
        )
        count += 1

    logger.info("sync_players: synced %d players", count)
    return count


def compute_standings(season: int) -> int:
    """Compute standings from FINAL/FINAL_OT game results for the season.

    This is used in place of the BDL standings API (requires All-Star tier).
    Simplified tiebreakers: win_pct only. Full NFL tiebreakers deferred
    to when we upgrade to All-Star and can sync official standings.
    """
    stats = defaultdict(
        lambda: {
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "div_wins": 0,
            "div_losses": 0,
            "conf_wins": 0,
            "conf_losses": 0,
            "pf": 0,
            "pa": 0,
            "streak_type": None,
            "streak_count": 0,
        }
    )

    games = (
        Game.objects.filter(
            season=season, status__in=(GameStatus.FINAL, GameStatus.FINAL_OT)
        )
        .exclude(home_score__isnull=True)
        .select_related("home_team", "away_team")
        .order_by("game_date", "kickoff")
    )

    for g in games:
        ht, at = g.home_team, g.away_team
        ht_id, at_id = ht.pk, at.pk
        home_score, away_score = g.home_score, g.away_score

        stats[ht_id]["pf"] += home_score
        stats[ht_id]["pa"] += away_score
        stats[at_id]["pf"] += away_score
        stats[at_id]["pa"] += home_score

        same_div = ht.division == at.division
        same_conf = ht.conference == at.conference

        if home_score > away_score:
            _record_result(stats[ht_id], "W", same_div, same_conf)
            _record_result(stats[at_id], "L", same_div, same_conf)
        elif away_score > home_score:
            _record_result(stats[at_id], "W", same_div, same_conf)
            _record_result(stats[ht_id], "L", same_div, same_conf)
        else:
            _record_result(stats[ht_id], "T", same_div, same_conf)
            _record_result(stats[at_id], "T", same_div, same_conf)

    # Build team lookup for conference/division
    teams_by_pk = {t.pk: t for t in Team.objects.all()}

    count = 0
    for team_pk, s in stats.items():
        team = teams_by_pk.get(team_pk)
        if not team:
            continue
        total = s["wins"] + s["losses"] + s["ties"]
        win_pct = round((s["wins"] + 0.5 * s["ties"]) / total, 3) if total else 0.0
        streak = (
            f"{'W' if s['streak_type'] == 'W' else 'L' if s['streak_type'] == 'L' else 'T'}{s['streak_count']}"
            if s["streak_type"]
            else ""
        )
        Standing.objects.update_or_create(
            team=team,
            season=season,
            defaults={
                "conference": team.conference,
                "division": team.division,
                "wins": s["wins"],
                "losses": s["losses"],
                "ties": s["ties"],
                "win_pct": win_pct,
                "division_wins": s["div_wins"],
                "division_losses": s["div_losses"],
                "conference_wins": s["conf_wins"],
                "conference_losses": s["conf_losses"],
                "points_for": s["pf"],
                "points_against": s["pa"],
                "streak": streak,
            },
        )
        count += 1

    # Compute division ranks (sorted by win_pct within each division)
    for div in Division.values:
        qs = Standing.objects.filter(season=season, division=div).order_by(
            "-win_pct", "-wins"
        )
        for rank, standing in enumerate(qs, start=1):
            if standing.division_rank != rank:
                standing.division_rank = rank
                standing.save(update_fields=["division_rank"])

    logger.info("compute_standings: computed %d standings (season=%s)", count, season)
    return count


def _record_result(
    team_stats: dict, result: str, same_division: bool, same_conference: bool
) -> None:
    """Update a team's stats dict with a game result."""
    if result == "W":
        team_stats["wins"] += 1
        if same_division:
            team_stats["div_wins"] += 1
        if same_conference:
            team_stats["conf_wins"] += 1
    elif result == "L":
        team_stats["losses"] += 1
        if same_division:
            team_stats["div_losses"] += 1
        if same_conference:
            team_stats["conf_losses"] += 1
    else:
        team_stats["ties"] += 1

    # Update streak
    if team_stats["streak_type"] == result:
        team_stats["streak_count"] += 1
    else:
        team_stats["streak_type"] = result
        team_stats["streak_count"] = 1
