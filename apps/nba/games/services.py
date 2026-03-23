"""
NBA data API client (sportsdata.io v3) and sync helpers.

All public methods return normalized dicts that map directly to model fields.
Status strings from the API are normalized to GameStatus choices here.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx
from django.conf import settings

from games.models import Conference, Game, GameStatus, Standing, Team

logger = logging.getLogger(__name__)

SPORTSDATA_BASE = "https://api.sportsdata.io/v3/nba/scores/JSON"

# Map sportsdata.io status strings → our GameStatus enum
_STATUS_MAP = {
    "Scheduled": GameStatus.SCHEDULED,
    "InProgress": GameStatus.IN_PROGRESS,
    "Halftime": GameStatus.HALFTIME,
    "Final": GameStatus.FINAL,
    "F/OT": GameStatus.FINAL,
    "Postponed": GameStatus.POSTPONED,
    "Canceled": GameStatus.CANCELLED,
    "Delayed": GameStatus.SCHEDULED,
    "Suspended": GameStatus.SCHEDULED,
    "Forfeit": GameStatus.CANCELLED,
}

# Map sportsdata.io conference strings → our Conference enum
_CONFERENCE_MAP = {
    "Eastern": Conference.EAST,
    "Western": Conference.WEST,
}


def _normalize_status(raw: str) -> str:
    """Convert API status string to GameStatus. Defaults to SCHEDULED."""
    return _STATUS_MAP.get(raw, GameStatus.SCHEDULED)


def _normalize_conference(raw: str) -> str:
    return _CONFERENCE_MAP.get(raw, Conference.EAST)


def _sportsdata_date(d: date) -> str:
    """Format date as YYYY-MMM-DD (e.g. 2025-MAR-20) for sportsdata.io URL paths."""
    return d.strftime("%Y-%b-%d").upper()


class NBADataClient:
    """Thin httpx wrapper around the sportsdata.io NBA v3 Scores API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.SPORTSDATA_API_KEY
        self._client = httpx.Client(
            base_url=SPORTSDATA_BASE,
            headers={"Ocp-Apim-Subscription-Key": self.api_key},
            timeout=15.0,
        )

    def _get(self, path: str) -> Any:
        response = self._client.get(path)
        response.raise_for_status()
        return response.json()

    # --- Public data methods ---

    def get_teams(self) -> list[dict]:
        """Return all active NBA teams, normalized."""
        raw = self._get("/Teams")
        return [self._normalize_team(t) for t in raw]

    def get_games(self, season: int, game_date: date | None = None) -> list[dict]:
        """Return games for a season. If game_date provided, fetch that day only."""
        if game_date:
            raw = self._get(f"/GamesByDate/{_sportsdata_date(game_date)}")
            raw = raw if isinstance(raw, list) else []
        else:
            raw = self._get(f"/Games/{season}")
        return [self._normalize_game(g) for g in raw]

    def get_standings(self, season: int) -> list[dict]:
        """Return standings for a season."""
        raw = self._get(f"/Standings/{season}")
        return [self._normalize_standing(s) for s in raw]

    def get_live_scores(self) -> list[dict]:
        """Return currently in-progress games. Skips API call if no games are live."""
        in_progress = self._get("/AreAnyGamesInProgress")
        if not in_progress:
            return []
        raw = self._get(f"/GamesByDate/{_sportsdata_date(date.today())}")
        return [
            self._normalize_game(g)
            for g in (raw if isinstance(raw, list) else [])
            if g.get("Status") in ("InProgress", "Halftime", "Final", "F/OT")
        ]

    # --- Normalizers ---

    def _normalize_team(self, t: dict) -> dict:
        return {
            "external_id": t["TeamID"],
            "name": t["Name"],
            "short_name": f"{t['City']} {t['Name']}",
            "abbreviation": t["Key"],
            "logo_url": t.get("WikipediaLogoUrl") or "",
            "conference": _normalize_conference(t.get("Conference", "")),
            "division": t.get("Division", ""),
        }

    def _normalize_game(self, g: dict) -> dict:
        raw_dt = g.get("DateTime") or g.get("Day") or ""
        day = raw_dt[:10]
        tip_off = None
        if raw_dt:
            try:
                tip_off = datetime.fromisoformat(raw_dt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return {
            "external_id": g["GameID"],
            "home_team_external_id": g.get("HomeTeamID"),
            "away_team_external_id": g.get("AwayTeamID"),
            "home_score": g.get("HomeTeamScore"),
            "away_score": g.get("AwayTeamScore"),
            "status": _normalize_status(g.get("Status", "")),
            "game_date": day,
            "tip_off": tip_off,
            "season": g.get("Season"),
            "arena": "",
            "postseason": g.get("SeasonType", 1) != 1,
        }

    def _normalize_standing(self, s: dict) -> dict:
        wins = s.get("Wins", 0)
        losses = s.get("Losses", 0)
        total = wins + losses
        win_pct = round(wins / total, 3) if total else 0.0
        return {
            "team_external_id": s["TeamID"],
            "season": s.get("Season"),
            "conference": _normalize_conference(s.get("Conference", "")),
            "wins": wins,
            "losses": losses,
            "win_pct": win_pct,
            "games_behind": s.get("GamesBack") or 0.0,
            "streak": s.get("StreakDescription", ""),
            "home_record": f"{s.get('HomeWins', 0)}-{s.get('HomeLosses', 0)}",
            "away_record": f"{s.get('AwayWins', 0)}-{s.get('AwayLosses', 0)}",
            "conference_rank": s.get("ConferenceRank"),
        }

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# --- Sync helpers ---


def sync_teams(client: NBADataClient | None = None) -> int:
    """Upsert all teams. Returns count of teams synced."""
    with client or NBADataClient() as c:
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
    game_date: date | None = None,
    client: NBADataClient | None = None,
) -> int:
    """Upsert games for a season (or a single date). Returns count synced."""
    with client or NBADataClient() as c:
        games = c.get_games(season, game_date=game_date)

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
    logger.info("sync_games: synced %d games (season=%s)", count, season)
    return count


def sync_standings(season: int, client: NBADataClient | None = None) -> int:
    """Upsert standings for a season. Returns count synced."""
    with client or NBADataClient() as c:
        standings = c.get_standings(season)

    count = 0
    for s in standings:
        team_ext_id = s.pop("team_external_id")
        try:
            team = Team.objects.get(external_id=team_ext_id)
        except Team.DoesNotExist:
            logger.warning("sync_standings: unknown team external_id=%s", team_ext_id)
            continue
        s["team"] = team
        season_val = s.pop("season")
        Standing.objects.update_or_create(team=team, season=season_val, defaults=s)
        count += 1
    logger.info("sync_standings: synced %d standings (season=%s)", count, season)
    return count


def sync_live_scores(client: NBADataClient | None = None) -> int:
    """Update scores + status for in-progress games. Returns count updated."""
    with client or NBADataClient() as c:
        games = c.get_live_scores()

    count = 0
    updated_game_pks = []
    for g in games:
        external_id = g.pop("external_id")
        g.pop("home_team_external_id", None)
        g.pop("away_team_external_id", None)
        updated = Game.objects.filter(external_id=external_id).update(
            home_score=g["home_score"],
            away_score=g["away_score"],
            status=g["status"],
        )
        if updated:
            try:
                game_obj = Game.objects.get(external_id=external_id)
                updated_game_pks.append(game_obj.pk)
            except Game.DoesNotExist:
                pass
        count += updated

    if updated_game_pks:
        _broadcast_score_updates(updated_game_pks)

    logger.info("sync_live_scores: updated %d games", count)
    return count


def _broadcast_score_updates(game_pks: list[int]) -> None:
    """Broadcast score updates to WebSocket groups and create ActivityEvents."""
    from activity.models import ActivityEvent
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    send = async_to_sync(channel_layer.group_send)

    for pk in game_pks:
        try:
            game = Game.objects.select_related("home_team", "away_team").get(pk=pk)
        except Game.DoesNotExist:
            continue

        # Dashboard update
        send("live_scores", {"type": "score_update", "game_pk": pk})

        # Game detail update
        send(f"game_{game.id_hash}", {"type": "game_score_update", "game_pk": pk})

        # Activity event
        ActivityEvent.objects.create(
            event_type=ActivityEvent.EventType.SCORE_CHANGE,
            message=(
                f"{game.away_team.abbreviation} {game.away_score}"
                f" - {game.home_team.abbreviation} {game.home_score}"
            ),
        )
