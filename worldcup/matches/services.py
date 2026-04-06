"""World Cup data client and sync services using football-data.org v4 API."""

import json
import logging
import time
from pathlib import Path

import httpx
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

STATIC_DATA_DIR = Path(__file__).parent / "static_data"

# football-data.org free tier: 10 req/min
MIN_REQUEST_INTERVAL = 6.0


class WorldCupDataClient:
    """Client for football-data.org v4 API (World Cup competition)."""

    BASE_URL = "https://api.football-data.org/v4"
    COMPETITION = "WC"

    def __init__(self, api_key=None, offline=False):
        self.api_key = api_key or getattr(settings, "FOOTBALL_DATA_API_KEY", "")
        self.offline = offline
        self._last_request_at = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.time()

    def _get(self, path):
        if self.offline:
            raise RuntimeError("Cannot make API calls in offline mode")
        self._throttle()
        url = f"{self.BASE_URL}{path}"
        headers = {"X-Auth-Token": self.api_key}
        response = httpx.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_teams(self):
        if self.offline:
            return json.loads((STATIC_DATA_DIR / "teams.json").read_text())
        data = self._get(f"/competitions/{self.COMPETITION}/teams")
        return data.get("teams", [])

    def get_matches(self):
        if self.offline:
            return json.loads((STATIC_DATA_DIR / "matches.json").read_text())
        data = self._get(f"/competitions/{self.COMPETITION}/matches")
        return data.get("matches", [])

    def get_standings(self):
        if self.offline:
            return json.loads((STATIC_DATA_DIR / "standings.json").read_text())
        data = self._get(f"/competitions/{self.COMPETITION}/standings")
        return data.get("standings", [])


# --- Status normalization ---

STATUS_MAP = {
    "SCHEDULED": "SCHEDULED",
    "TIMED": "TIMED",
    "IN_PLAY": "IN_PLAY",
    "PAUSED": "PAUSED",
    "EXTRA_TIME": "EXTRA_TIME",
    "PENALTY_SHOOTOUT": "PENALTY_SHOOTOUT",
    "FINISHED": "FINISHED",
    "POSTPONED": "POSTPONED",
    "CANCELLED": "CANCELLED",
    "SUSPENDED": "PAUSED",
    "AWARDED": "FINISHED",
}

STAGE_MAP = {
    "GROUP_STAGE": "GROUP",
    "ROUND_OF_32": "ROUND_OF_32",
    "LAST_32": "ROUND_OF_32",
    "ROUND_OF_16": "ROUND_OF_16",
    "LAST_16": "ROUND_OF_16",
    "QUARTER_FINALS": "QUARTER",
    "SEMI_FINALS": "SEMI",
    "THIRD_PLACE": "THIRD_PLACE",
    "FINAL": "FINAL",
}


def _normalize_status(raw):
    return STATUS_MAP.get(raw, "SCHEDULED")


def _normalize_stage(raw):
    return STAGE_MAP.get(raw, "GROUP")


# --- Sync functions ---


def sync_stages():
    """Create the 7 tournament stages."""
    from worldcup.matches.models import Stage

    stages = [
        ("Group Stage", "GROUP", 1),
        ("Round of 32", "ROUND_OF_32", 2),
        ("Round of 16", "ROUND_OF_16", 3),
        ("Quarter-finals", "QUARTER", 4),
        ("Semi-finals", "SEMI", 5),
        ("Third-place Play-off", "THIRD_PLACE", 6),
        ("Final", "FINAL", 7),
    ]
    for name, stage_type, order in stages:
        Stage.objects.update_or_create(
            stage_type=stage_type,
            defaults={"name": name, "order": order},
        )
    return len(stages)


def sync_teams(offline=False):
    """Sync teams from football-data.org or static JSON."""
    from worldcup.matches.models import Confederation, Team

    client = WorldCupDataClient(offline=offline)
    teams_data = client.get_teams()
    created = updated = 0

    confederation_map = {
        "AFC": Confederation.AFC,
        "CAF": Confederation.CAF,
        "CONCACAF": Confederation.CONCACAF,
        "CONMEBOL": Confederation.CONMEBOL,
        "OFC": Confederation.OFC,
        "UEFA": Confederation.UEFA,
    }

    for t in teams_data:
        area = t.get("area", {})
        conf_raw = area.get("parentArea", "") or ""
        confederation = ""
        for key, val in confederation_map.items():
            if key.lower() in conf_raw.lower():
                confederation = val
                break

        _, was_created = Team.objects.update_or_create(
            external_id=t["id"],
            defaults={
                "name": t.get("name") or "",
                "short_name": t.get("shortName") or "",
                "tla": t.get("tla") or "",
                "crest_url": t.get("crest") or "",
                "country_code": area.get("code") or "",
                "confederation": confederation,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return created, updated


def sync_groups():
    """Create groups A-L and assign teams based on match data."""
    from worldcup.matches.models import Group

    for letter in "ABCDEFGHIJKL":
        Group.objects.get_or_create(letter=letter)
    return 12


def sync_matches(offline=False):
    """Sync matches from football-data.org or static JSON."""
    from worldcup.matches.models import Group, Match, Stage, Team

    client = WorldCupDataClient(offline=offline)
    matches_data = client.get_matches()
    created = updated = 0

    for m in matches_data:
        home_team = Team.objects.filter(external_id=m["homeTeam"]["id"]).first()
        away_team = Team.objects.filter(external_id=m["awayTeam"]["id"]).first()
        if not home_team or not away_team:
            logger.warning("Skipping match %s — missing team(s)", m.get("id"))
            continue

        stage_type = _normalize_stage(m.get("stage", "GROUP_STAGE"))
        stage = Stage.objects.filter(stage_type=stage_type).first()
        if not stage:
            logger.warning(
                "Skipping match %s — unknown stage %s", m.get("id"), stage_type
            )
            continue

        # Resolve group
        group = None
        group_str = m.get("group", "")
        if group_str and stage_type == "GROUP":
            letter = group_str.replace("GROUP_", "").replace("Group ", "")[-1].upper()
            group = Group.objects.filter(letter=letter).first()
            if group:
                group.teams.add(home_team, away_team)

        score = m.get("score", {})
        full_time = score.get("fullTime", {})
        extra_time = score.get("extraTime", {})
        penalties = score.get("penalties", {})

        _, was_created = Match.objects.update_or_create(
            external_id=m["id"],
            defaults={
                "home_team": home_team,
                "away_team": away_team,
                "stage": stage,
                "group": group,
                "matchday": m.get("matchday"),
                "home_score": full_time.get("home"),
                "away_score": full_time.get("away"),
                "home_score_et": extra_time.get("home"),
                "away_score_et": extra_time.get("away"),
                "home_score_penalties": penalties.get("home"),
                "away_score_penalties": penalties.get("away"),
                "status": _normalize_status(m.get("status", "SCHEDULED")),
                "kickoff": m.get("utcDate", timezone.now().isoformat()),
                "venue": m.get("venue") or "",
                "city": "",
                "season": "2026",
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return created, updated


def sync_standings(offline=False):
    """Sync group standings from football-data.org or static JSON."""
    from worldcup.matches.models import Group, Standing, Team

    client = WorldCupDataClient(offline=offline)
    standings_data = client.get_standings()
    created = updated = 0

    for group_data in standings_data:
        group_str = group_data.get("group", "")
        letter = group_str.replace("GROUP_", "").replace("Group ", "")[-1].upper()
        group = Group.objects.filter(letter=letter).first()
        if not group:
            continue

        for entry in group_data.get("table", []):
            team = Team.objects.filter(external_id=entry["team"]["id"]).first()
            if not team:
                continue

            _, was_created = Standing.objects.update_or_create(
                group=group,
                team=team,
                defaults={
                    "position": entry.get("position", 0),
                    "played": entry.get("playedGames", 0),
                    "won": entry.get("won", 0),
                    "drawn": entry.get("draw", 0),
                    "lost": entry.get("lost", 0),
                    "goals_for": entry.get("goalsFor", 0),
                    "goals_against": entry.get("goalsAgainst", 0),
                    "goal_difference": entry.get("goalDifference", 0),
                    "points": entry.get("points", 0),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

    return created, updated


def poll_live_scores():
    """Poll for live score updates and broadcast changes via WebSocket."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from worldcup.matches.models import Match

    live_statuses = [
        Match.Status.IN_PLAY,
        Match.Status.PAUSED,
        Match.Status.EXTRA_TIME,
        Match.Status.PENALTY_SHOOTOUT,
    ]
    live_matches = Match.objects.filter(status__in=live_statuses)
    if not live_matches.exists():
        return

    # Snapshot pre-sync state
    pre_sync = {m.pk: (m.home_score, m.away_score, m.status) for m in live_matches}

    # Re-sync from API
    sync_matches()

    # Check for changes
    channel_layer = get_channel_layer()
    for match in Match.objects.filter(pk__in=pre_sync.keys()):
        old = pre_sync[match.pk]
        new = (match.home_score, match.away_score, match.status)
        if old != new:
            logger.info("Score change: %s %s -> %s", match, old, new)
            async_to_sync(channel_layer.group_send)(
                "wc_live_scores",
                {
                    "type": "score_update",
                    "html": f"<!-- score update for {match.pk} -->",
                },
            )

            if match.status == Match.Status.FINISHED:
                from worldcup.betting.tasks import settle_match_bets

                settle_match_bets.delay(match.pk)
