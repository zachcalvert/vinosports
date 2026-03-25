"""
EPL data API client (BallDontLie) and sync helpers.

All public methods return normalized dicts that map directly to model fields.
"""

import json
import logging
from datetime import date
from pathlib import Path

import httpx
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from epl.matches.models import Match, MatchStats, Standing, Team

logger = logging.getLogger(__name__)

STATIC_DATA_DIR = Path(__file__).resolve().parent / "static_data"

BDL_BASE = "https://api.balldontlie.io/epl/v2"

# BDL EPL status strings → our Match.Status choices
_EPL_STATUS_MAP = {
    "STATUS_SCHEDULED": Match.Status.SCHEDULED,
    "STATUS_TIMED": Match.Status.TIMED,
    "STATUS_FIRST_HALF": Match.Status.IN_PLAY,
    "STATUS_HALFTIME": Match.Status.PAUSED,
    "STATUS_SECOND_HALF": Match.Status.IN_PLAY,
    "STATUS_EXTRA_TIME": Match.Status.IN_PLAY,
    "STATUS_PENALTY": Match.Status.IN_PLAY,
    "STATUS_FULL_TIME": Match.Status.FINISHED,
    "STATUS_FINAL": Match.Status.FINISHED,
    "STATUS_POSTPONED": Match.Status.POSTPONED,
    "STATUS_CANCELLED": Match.Status.CANCELLED,
    "STATUS_SUSPENDED": Match.Status.POSTPONED,
}


def _normalize_epl_status(raw: str) -> str:
    return _EPL_STATUS_MAP.get(raw, Match.Status.SCHEDULED)


class FootballDataClient:
    """BallDontLie EPL v2 API client.

    Keeps the FootballDataClient name so callers (tasks, seed commands) don't
    need to change their imports.
    """

    def __init__(self):
        self.client = httpx.Client(
            base_url=BDL_BASE,
            headers={"Authorization": settings.BDL_API_KEY},
            timeout=settings.API_TIMEOUT,
        )

    def _get(self, path, params=None):
        logger.info("BDL EPL GET %s params=%s", path, params)
        resp = self.client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def _get_all(self, path, params=None):
        """Paginate through all results."""
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

    def get_teams(self, season=None):
        raw = self._get_all("/teams")
        return [self._normalize_team(t) for t in raw]

    def get_matches(self, season, matchday=None, status=None, game_date=None):
        params = {"season": season}
        if game_date:
            params["dates[]"] = (
                game_date.isoformat() if isinstance(game_date, date) else game_date
            )
        raw = self._get_all("/matches", params=params)
        return [self._normalize_match(m, season) for m in raw]

    def get_match(self, match_id):
        """Fetch a single match by ID."""
        data = self._get(f"/matches/{match_id}")
        m = data.get("data", data)
        return self._normalize_match(m, m.get("season", ""))

    def get_standings(self, season):
        data = self._get("/standings", params={"season": season})
        raw = data.get("data", []) if isinstance(data, dict) else data
        return [self._normalize_standing(s, season) for s in raw]

    def _normalize_team(self, t):
        return {
            "external_id": t["id"],
            "name": t["name"],
            "short_name": t.get("short_name", ""),
            "tla": t.get("abbreviation", ""),
            "crest_url": "",
            "venue": "",
        }

    def _normalize_match(self, m, season):
        raw_dt = m.get("date", "")
        kickoff = None
        if raw_dt:
            kickoff = parse_datetime(
                raw_dt.replace("Z", "+00:00") if raw_dt.endswith("Z") else raw_dt
            )

        return {
            "external_id": m["id"],
            "home_team_external_id": m["home_team_id"],
            "away_team_external_id": m["away_team_id"],
            "home_score": m.get("home_score"),
            "away_score": m.get("away_score"),
            "status": _normalize_epl_status(m.get("status", "")),
            "matchday": m.get("matchday", 0),
            "kickoff": kickoff,
            "season": str(season),
        }

    def _normalize_standing(self, s, season):
        team = s.get("team", {})
        return {
            "team_external_id": team.get("id") or s.get("team_id"),
            "season": str(season),
            "position": s.get("rank", 0),
            "played": s.get("games_played", 0),
            "won": s.get("wins", 0),
            "drawn": s.get("draws", 0),
            "lost": s.get("losses", 0),
            "goals_for": s.get("goals_for", 0),
            "goals_against": s.get("goals_against", 0),
            "goal_difference": s.get("goal_differential", 0),
            "points": s.get("points", 0),
        }

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------


def sync_teams(season, offline=False):
    if offline:
        with open(STATIC_DATA_DIR / "teams.json") as f:
            teams_data = json.load(f)
    else:
        with FootballDataClient() as client:
            teams_data = client.get_teams(season)

    created = updated = 0
    for t in teams_data:
        _, was_created = Team.objects.update_or_create(
            external_id=t["external_id"],
            defaults={
                "name": t["name"],
                "short_name": t["short_name"],
                "tla": t["tla"],
                "crest_url": t["crest_url"],
                "venue": t["venue"],
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("sync_teams: created=%d updated=%d", created, updated)
    return created, updated


def sync_matches(season, matchday=None, status=None, offline=False, game_date=None):
    if offline:
        with open(STATIC_DATA_DIR / "matches.json") as f:
            matches_data = json.load(f)
    else:
        with FootballDataClient() as client:
            matches_data = client.get_matches(
                season, matchday=matchday, status=status, game_date=game_date
            )

    # BDL doesn't return matchday. If missing, derive from date grouping:
    # sort all matches by kickoff, group into rounds of 10 (20 teams = 10 per round).
    if matches_data and not matches_data[0].get("matchday"):
        _assign_matchdays(matches_data)

    team_map = {t.external_id: t for t in Team.objects.all()}

    created = updated = 0
    for m in matches_data:
        home = team_map.get(m["home_team_external_id"])
        away = team_map.get(m["away_team_external_id"])
        if not home or not away:
            logger.warning(
                "Skipping match %s: missing team(s) home=%s away=%s",
                m["external_id"],
                m["home_team_external_id"],
                m["away_team_external_id"],
            )
            continue

        _, was_created = Match.objects.update_or_create(
            external_id=m["external_id"],
            defaults={
                "home_team": home,
                "away_team": away,
                "home_score": m["home_score"],
                "away_score": m["away_score"],
                "status": m["status"],
                "matchday": m["matchday"],
                "kickoff": m["kickoff"],
                "season": m["season"],
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("sync_matches: created=%d updated=%d", created, updated)
    return created, updated


def sync_standings(season, offline=False):
    if offline:
        with open(STATIC_DATA_DIR / "standings.json") as f:
            standings_data = json.load(f)
    else:
        with FootballDataClient() as client:
            standings_data = client.get_standings(season)

    team_map = {t.external_id: t for t in Team.objects.all()}

    created = updated = 0
    for s in standings_data:
        team = team_map.get(s["team_external_id"])
        if not team:
            logger.warning("Skipping standing: missing team %s", s["team_external_id"])
            continue

        _, was_created = Standing.objects.update_or_create(
            team=team,
            season=s["season"],
            defaults={
                "position": s["position"],
                "played": s["played"],
                "won": s["won"],
                "drawn": s["drawn"],
                "lost": s["lost"],
                "goals_for": s["goals_for"],
                "goals_against": s["goals_against"],
                "goal_difference": s["goal_difference"],
                "points": s["points"],
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("sync_standings: created=%d updated=%d", created, updated)
    return created, updated


def _assign_matchdays(matches_data: list[dict]) -> None:
    """Derive matchday numbers from kickoff dates.

    EPL has 20 teams = 10 matches per matchday.  Sort all matches by kickoff,
    then assign matchday 1, 2, 3, ... for each batch of 10.
    """
    sorted_matches = sorted(matches_data, key=lambda m: m.get("kickoff") or "")
    for i, m in enumerate(sorted_matches):
        m["matchday"] = (i // 10) + 1


def get_team_form(team, limit=5):
    """Return the last `limit` finished EPL matches for a team from the local DB."""
    recent = (
        Match.objects.filter(
            Q(home_team=team) | Q(away_team=team),
            status=Match.Status.FINISHED,
        )
        .select_related("home_team", "away_team")
        .order_by("-kickoff")[:limit]
    )
    results = []
    for m in reversed(list(recent)):
        is_home = m.home_team_id == team.pk
        hs, as_ = m.home_score, m.away_score
        if hs is not None and as_ is not None:
            if is_home:
                result = "W" if hs > as_ else ("D" if hs == as_ else "L")
            else:
                result = "W" if as_ > hs else ("D" if as_ == hs else "L")
        else:
            result = None
        results.append(
            {
                "date": m.kickoff.date().isoformat() if m.kickoff else "",
                "home_team": m.home_team.short_name or m.home_team.name,
                "away_team": m.away_team.short_name or m.away_team.name,
                "home_score": hs,
                "away_score": as_,
                "result": result,
            }
        )
    return results


def get_head_to_head(match, limit=5):
    """Compute H2H from local DB (no API call needed)."""
    h2h_qs = (
        Match.objects.filter(
            Q(home_team=match.home_team, away_team=match.away_team)
            | Q(home_team=match.away_team, away_team=match.home_team),
            status=Match.Status.FINISHED,
        )
        .exclude(pk=match.pk)
        .select_related("home_team", "away_team")
        .order_by("-kickoff")[:limit]
    )

    h2h_matches = []
    home_wins = away_wins = draws = 0
    for m in h2h_qs:
        hs, as_ = m.home_score, m.away_score
        h2h_matches.append(
            {
                "date": m.kickoff.date().isoformat() if m.kickoff else "",
                "home_team": m.home_team.short_name or m.home_team.name,
                "away_team": m.away_team.short_name or m.away_team.name,
                "home_score": hs,
                "away_score": as_,
            }
        )
        if hs is None or as_ is None:
            continue
        if hs == as_:
            draws += 1
        elif hs > as_:
            if m.home_team_id == match.home_team_id:
                home_wins += 1
            else:
                away_wins += 1
        else:
            if m.home_team_id == match.home_team_id:
                away_wins += 1
            else:
                home_wins += 1

    summary = {"home_wins": home_wins, "away_wins": away_wins, "draws": draws}
    return h2h_matches, summary


def fetch_match_hype_data(match):
    """Fetch and cache H2H + form data for a match (all local, no API)."""
    stats, _ = MatchStats.objects.get_or_create(match=match)
    if not stats.is_stale():
        return stats

    try:
        h2h_matches, h2h_summary = get_head_to_head(match)

        stats.h2h_json = h2h_matches
        stats.h2h_summary_json = h2h_summary
        stats.home_form_json = get_team_form(match.home_team)
        stats.away_form_json = get_team_form(match.away_team)
        stats.fetched_at = timezone.now()
        stats.last_attempt_at = timezone.now()
        stats.save()
        logger.info("fetch_match_hype_data: updated stats for match %d", match.pk)
    except Exception:
        logger.exception("fetch_match_hype_data: failed for match %d", match.pk)
        stats.last_attempt_at = timezone.now()
        stats.save(update_fields=["last_attempt_at"])

    return stats
