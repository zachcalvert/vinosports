"""
NBA data API client (BallDontLie) and sync helpers.

All public methods return normalized dicts that map directly to model fields.
Status strings from the API are normalized to GameStatus choices here.
"""

import logging
import zoneinfo
from datetime import date, datetime
from typing import Any

import httpx
from django.conf import settings

from games.models import Conference, Game, GameStatus, Standing, Team

_ET = zoneinfo.ZoneInfo("America/New_York")


logger = logging.getLogger(__name__)

BDL_BASE = "https://api.balldontlie.io/nba/v1"

_CONFERENCE_MAP = {
    "East": Conference.EAST,
    "West": Conference.WEST,
}


def _normalize_status(raw: str) -> str:
    """Convert BDL status string to GameStatus.

    BDL uses: ISO timestamp (scheduled), quarter strings (live),
    "Halftime", "Final".
    """
    if raw == "Final":
        return GameStatus.FINAL
    if raw == "Halftime":
        return GameStatus.HALFTIME
    if raw in ("1st Qtr", "2nd Qtr", "3rd Qtr", "4th Qtr"):
        return GameStatus.IN_PROGRESS
    # ISO timestamps and anything else = scheduled
    return GameStatus.SCHEDULED


def _normalize_conference(raw: str) -> str:
    return _CONFERENCE_MAP.get(raw, Conference.EAST)


class NBADataClient:
    """Thin httpx wrapper around the BallDontLie NBA v1 API."""

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

    def _get_all(self, path: str, params: dict | None = None) -> list[dict]:
        """Paginate through all results for a list endpoint."""
        params = dict(params or {})
        params["per_page"] = 100
        results = []
        while True:
            data = self._get(path, params=params)
            results.extend(data.get("data", []))
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
            params["cursor"] = cursor
        return results

    # --- Public data methods ---

    def get_teams(self) -> list[dict]:
        """Return all active NBA teams, normalized."""
        raw = self._get_all("/teams")
        return [self._normalize_team(t) for t in raw]

    def get_games(self, season: int, game_date: date | None = None) -> list[dict]:
        """Return games for a season, or for a specific date.

        When game_date is provided, only the date filter is sent (the BDL
        dates[] filter is sufficient on its own and avoids needing a valid
        season value).
        """
        params: dict[str, Any] = {}
        if game_date:
            params["dates[]"] = game_date.isoformat()
        else:
            params["seasons[]"] = season
        raw = self._get_all("/games", params=params)
        return [self._normalize_game(g) for g in raw]

    def get_standings(self, season: int) -> list[dict]:
        """Return standings for a season (requires All-Star tier)."""
        data = self._get("/standings", params={"season": season})
        raw = data.get("data", []) if isinstance(data, dict) else data
        return [self._normalize_standing(s) for s in raw]

    def get_live_scores(self) -> list[dict]:
        """Return in-progress and recently-finished games for today.

        Checks if we have locally-live games to avoid unnecessary API calls.
        """
        local_live = Game.objects.filter(
            game_date=date.today(),
            status__in=(GameStatus.IN_PROGRESS, GameStatus.HALFTIME),
        ).exists()
        if not local_live:
            # No games we think are live — skip unless there are scheduled
            # games today (they might have started since our last check).
            has_scheduled = Game.objects.filter(
                game_date=date.today(),
                status=GameStatus.SCHEDULED,
            ).exists()
            if not has_scheduled:
                return []

        raw = self._get_all("/games", params={"dates[]": date.today().isoformat()})
        return [
            self._normalize_game(g)
            for g in raw
            if _normalize_status(g.get("status", ""))
            in (GameStatus.IN_PROGRESS, GameStatus.HALFTIME, GameStatus.FINAL)
        ]

    # --- Normalizers ---

    def _normalize_team(self, t: dict) -> dict:
        return {
            "external_id": t["id"],
            "name": t["name"],
            "short_name": t.get("full_name", f"{t.get('city', '')} {t['name']}"),
            "abbreviation": t["abbreviation"],
            "logo_url": f"https://cdn.nba.com/logos/nba/{t['id']}/global/L/logo.svg",
            "conference": _normalize_conference(t.get("conference", "")),
            "division": t.get("division", ""),
        }

    def _normalize_game(self, g: dict) -> dict:
        raw_dt = g.get("datetime") or g.get("date") or ""
        day = raw_dt[:10]
        tip_off = None
        if raw_dt and "T" in raw_dt:
            try:
                # BDL returns ISO 8601: "2025-12-25T17:00:00.000Z"
                tip_off = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                # Derive game_date from tip-off in Eastern Time, not UTC,
                # so late-night ET games don't shift to the next calendar day.
                day = tip_off.astimezone(_ET).date().isoformat()
            except ValueError:
                pass
        return {
            "external_id": g["id"],
            "home_team_external_id": g["home_team"]["id"],
            "away_team_external_id": g["visitor_team"]["id"],
            "home_score": g.get("home_team_score"),
            "away_score": g.get("visitor_team_score"),
            "status": _normalize_status(g.get("status", "")),
            "game_date": day,
            "tip_off": tip_off,
            "season": g.get("season"),
            "arena": "",
            "postseason": g.get("postseason", False),
        }

    def _normalize_standing(self, s: dict) -> dict:
        team = s.get("team", {})
        wins = s.get("wins", 0)
        losses = s.get("losses", 0)
        total = wins + losses
        win_pct = round(wins / total, 3) if total else 0.0
        return {
            "team_external_id": team.get("id") or s.get("team_id"),
            "season": s.get("season"),
            "conference": _normalize_conference(team.get("conference", "")),
            "wins": wins,
            "losses": losses,
            "win_pct": win_pct,
            "games_behind": 0.0,
            "streak": "",
            "home_record": s.get("home_record", ""),
            "away_record": s.get("road_record", ""),
            "conference_rank": s.get("conference_rank"),
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
    """Upsert standings for a season.

    Tries the BDL standings API first; falls back to computing standings
    from game results if the endpoint is unavailable.
    """
    try:
        with client or NBADataClient() as c:
            standings = c.get_standings(season)
        count = 0
        for s in standings:
            team_ext_id = s.pop("team_external_id")
            try:
                team = Team.objects.get(external_id=team_ext_id)
            except Team.DoesNotExist:
                logger.warning(
                    "sync_standings: unknown team external_id=%s", team_ext_id
                )
                continue
            s["team"] = team
            season_val = s.pop("season")
            Standing.objects.update_or_create(team=team, season=season_val, defaults=s)
            count += 1
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.info(
            "sync_standings: API unavailable (%s: %s), computing from game results",
            type(exc).__name__,
            exc,
        )
        count = _compute_standings_from_games(season)

    # Recompute conference_rank from win_pct.
    for conf in (Conference.EAST, Conference.WEST):
        qs = Standing.objects.filter(season=season, conference=conf).order_by(
            "-win_pct", "games_behind"
        )
        for rank, standing in enumerate(qs, start=1):
            if standing.conference_rank != rank:
                standing.conference_rank = rank
                standing.save(update_fields=["conference_rank"])

    logger.info("sync_standings: synced %d standings (season=%s)", count, season)
    return count


def _compute_standings_from_games(season: int) -> int:
    """Compute standings from FINAL game results for the season."""
    from collections import defaultdict

    stats = defaultdict(
        lambda: {
            "wins": 0,
            "losses": 0,
            "home_wins": 0,
            "home_losses": 0,
            "away_wins": 0,
            "away_losses": 0,
        }
    )

    games = (
        Game.objects.filter(season=season, status=GameStatus.FINAL)
        .exclude(home_score__isnull=True)
        .select_related("home_team", "away_team")
    )

    for g in games:
        home_won = g.home_score > g.away_score
        ht, at = g.home_team_id, g.away_team_id
        if home_won:
            stats[ht]["wins"] += 1
            stats[ht]["home_wins"] += 1
            stats[at]["losses"] += 1
            stats[at]["away_losses"] += 1
        else:
            stats[at]["wins"] += 1
            stats[at]["away_wins"] += 1
            stats[ht]["losses"] += 1
            stats[ht]["home_losses"] += 1

    count = 0
    for team in Team.objects.all():
        s = stats.get(team.pk)
        if not s:
            continue
        total = s["wins"] + s["losses"]
        win_pct = round(s["wins"] / total, 3) if total else 0.0
        Standing.objects.update_or_create(
            team=team,
            season=season,
            defaults={
                "conference": team.conference,
                "wins": s["wins"],
                "losses": s["losses"],
                "win_pct": win_pct,
                "games_behind": 0.0,
                "streak": "",
                "home_record": f"{s['home_wins']}-{s['home_losses']}",
                "away_record": f"{s['away_wins']}-{s['away_losses']}",
            },
        )
        count += 1
    return count


def sync_live_scores(client: NBADataClient | None = None) -> int:
    """Update scores + status for in-progress games. Returns count updated."""
    with client or NBADataClient() as c:
        games = c.get_live_scores()

    count = 0
    changed_game_pks = []
    for g in games:
        external_id = g.pop("external_id")
        g.pop("home_team_external_id", None)
        g.pop("away_team_external_id", None)

        try:
            game_obj = Game.objects.get(external_id=external_id)
        except Game.DoesNotExist:
            continue

        # Only flag as changed if the score or status actually differs
        score_changed = (
            game_obj.home_score != g["home_score"]
            or game_obj.away_score != g["away_score"]
            or game_obj.status != g["status"]
        )

        Game.objects.filter(pk=game_obj.pk).update(
            home_score=g["home_score"],
            away_score=g["away_score"],
            status=g["status"],
        )
        count += 1

        if score_changed:
            changed_game_pks.append(game_obj.pk)

    if changed_game_pks:
        _broadcast_score_updates(changed_game_pks)

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
            url=game.get_absolute_url(),
        )
