"""
UCL data API client (BallDontLie) and sync helpers.

All public methods return normalized dicts that map directly to model fields.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

import httpx
from django.conf import settings
from django.utils.dateparse import parse_datetime

from ucl.matches.models import Match, Standing, Team

logger = logging.getLogger(__name__)

STATIC_DATA_DIR = Path(__file__).resolve().parent / "static_data"

BDL_BASE = "https://api.balldontlie.io/ucl/v1"

# BDL UCL status strings → our Match.Status choices
# Same status strings as EPL, plus STATUS_FINAL_AET for extra-time finishes.
_UCL_STATUS_MAP = {
    "STATUS_SCHEDULED": Match.Status.SCHEDULED,
    "STATUS_TIMED": Match.Status.TIMED,
    "STATUS_FIRST_HALF": Match.Status.IN_PLAY,
    "STATUS_HALFTIME": Match.Status.PAUSED,
    "STATUS_SECOND_HALF": Match.Status.IN_PLAY,
    "STATUS_EXTRA_TIME": Match.Status.EXTRA_TIME,
    "STATUS_PENALTY": Match.Status.PENALTY_SHOOTOUT,
    "STATUS_FULL_TIME": Match.Status.FINISHED,
    "STATUS_FINAL": Match.Status.FINISHED,
    "STATUS_FINAL_AET": Match.Status.FINISHED,
    "STATUS_POSTPONED": Match.Status.POSTPONED,
    "STATUS_CANCELLED": Match.Status.CANCELLED,
    "STATUS_SUSPENDED": Match.Status.POSTPONED,
}


def _normalize_ucl_status(raw: str) -> str:
    return _UCL_STATUS_MAP.get(raw, Match.Status.SCHEDULED)


class UCLDataClient:
    """BallDontLie UCL v1 API client.

    Uses the same auth header and cursor-based pagination as the EPL client.
    """

    def __init__(self):
        self.client = httpx.Client(
            base_url=BDL_BASE,
            headers={"Authorization": settings.BDL_API_KEY},
            timeout=settings.API_TIMEOUT,
        )

    def _get(self, path, params=None):
        logger.info("BDL UCL GET %s params=%s", path, params)
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
        params = {}
        if season:
            params["season"] = season
        raw = self._get("/teams", params=params)
        return [self._normalize_team(t) for t in raw.get("data", [])]

    def get_matches(self, season, game_date=None):
        params = {"season": season}
        if game_date:
            params["dates[]"] = (
                game_date.isoformat() if hasattr(game_date, "isoformat") else game_date
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
            "name": t.get("name", ""),
            "short_name": t.get("short_name", ""),
            "tla": t.get("abbreviation", ""),
        }

    def _normalize_match(self, m, season):
        raw_dt = m.get("date", "")
        kickoff = None
        if raw_dt:
            kickoff = parse_datetime(
                raw_dt.replace("Z", "+00:00") if raw_dt.endswith("Z") else raw_dt
            )

        # BDL returns 0 for unplayed match scores — convert to None
        raw_status = m.get("status", "")
        status = _normalize_ucl_status(raw_status)
        is_finished = status == Match.Status.FINISHED
        is_live = status in (
            Match.Status.IN_PLAY,
            Match.Status.PAUSED,
            Match.Status.EXTRA_TIME,
            Match.Status.PENALTY_SHOOTOUT,
        )

        home_score = m.get("home_score")
        away_score = m.get("away_score")
        if not is_finished and not is_live:
            home_score = None
            away_score = None

        return {
            "external_id": m["id"],
            "home_team_external_id": m["home_team_id"],
            "away_team_external_id": m["away_team_id"],
            "home_score": home_score,
            "away_score": away_score,
            "status": status,
            "kickoff": kickoff,
            "season": str(season),
            "name": m.get("name", ""),
            "short_name": m.get("short_name", ""),
            "venue_name": m.get("venue_name", "") or "",
            "venue_city": m.get("venue_city", "") or "",
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
            "qualification_note": s.get("note", ""),
        }

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Stage inference
# ---------------------------------------------------------------------------

# UCL 2024-25+ format: league phase (Sep-Jan), knockout playoffs (Feb),
# R16 (Mar), QF (Apr), SF (Apr-May), Final (May-Jun).
# BDL doesn't provide explicit stage info, so we infer from dates and
# match name patterns.

# Stage cutoff dates for the 2025-26 season
_STAGE_DATE_CUTOFFS = [
    ("2026-02-01", "LEAGUE_PHASE"),
    ("2026-03-01", "KNOCKOUT_PLAYOFF"),
    ("2026-04-01", "ROUND_OF_16"),
    ("2026-05-01", "QUARTER"),
    ("2026-05-15", "SEMI"),
    ("9999-12-31", "FINAL"),
]


def _infer_stage(match_data: dict) -> str:
    """Infer stage type from match date and name."""
    name = match_data.get("name", "").lower()

    # Check name patterns first (handles TBD knockout matches)
    if "final" in name and "semifinal" not in name and "quarterfinal" not in name:
        return "FINAL"
    if "semifinal" in name:
        return "SEMI"
    if "quarterfinal" in name:
        return "QUARTER"

    # Fall back to date-based inference
    kickoff = match_data.get("kickoff")
    if kickoff:
        date_str = (
            kickoff.isoformat()[:10]
            if hasattr(kickoff, "isoformat")
            else str(kickoff)[:10]
        )
        for cutoff, stage_type in _STAGE_DATE_CUTOFFS:
            if date_str < cutoff:
                return stage_type

    return "LEAGUE_PHASE"


def _assign_matchdays(matches_data: list[dict]) -> None:
    """Derive matchday numbers for league phase matches.

    UCL league phase has 36 teams = 18 matches per matchday, 8 matchdays total.
    Matches on the same date (or consecutive days) form a single matchday.
    """
    lp_matches = [m for m in matches_data if _infer_stage(m) == "LEAGUE_PHASE"]
    lp_matches.sort(key=lambda m: m.get("kickoff") or "")

    # Group by date clusters (matches within 1 day of each other = same matchday)
    if not lp_matches:
        return

    matchday = 1
    prev_date = None
    date_to_matchday = {}

    for m in lp_matches:
        kickoff = m.get("kickoff")
        if not kickoff:
            continue
        date_str = (
            kickoff.isoformat()[:10]
            if hasattr(kickoff, "isoformat")
            else str(kickoff)[:10]
        )

        if date_str not in date_to_matchday:
            if prev_date and date_str > prev_date:
                # Check if this is a new cluster (more than 1 day gap)
                from datetime import date as date_type
                from datetime import timedelta

                try:
                    prev = date_type.fromisoformat(prev_date)
                    curr = date_type.fromisoformat(date_str)
                    if (curr - prev) > timedelta(days=1):
                        matchday += 1
                except ValueError:
                    matchday += 1

            date_to_matchday[date_str] = matchday
            prev_date = date_str

    for m in matches_data:
        kickoff = m.get("kickoff")
        if not kickoff:
            continue
        date_str = (
            kickoff.isoformat()[:10]
            if hasattr(kickoff, "isoformat")
            else str(kickoff)[:10]
        )
        if date_str in date_to_matchday:
            m["matchday"] = date_to_matchday[date_str]


def _assign_knockout_ties(matches_data: list[dict]) -> None:
    """Detect two-legged knockout ties and assign leg numbers + tie IDs.

    Two matches are a tie when the same two teams play each other in the same
    knockout stage, with home/away swapped for the return leg.
    """
    from ucl.matches.models import Stage

    knockout_stages = [
        Stage.StageType.KNOCKOUT_PLAYOFF,
        Stage.StageType.ROUND_OF_16,
        Stage.StageType.QUARTER,
        Stage.StageType.SEMI,
    ]
    stage_abbrevs = {
        "KNOCKOUT_PLAYOFF": "KP",
        "ROUND_OF_16": "R16",
        "QUARTER": "QF",
        "SEMI": "SF",
    }

    for stage_type in knockout_stages:
        stage_matches = [m for m in matches_data if m.get("_stage_type") == stage_type]
        stage_matches.sort(key=lambda m: m.get("kickoff") or "")

        # Group by team pair
        pair_matches = defaultdict(list)
        for m in stage_matches:
            pair = tuple(
                sorted([m["home_team_external_id"], m["away_team_external_id"]])
            )
            pair_matches[pair].append(m)

        tie_num = 1
        abbrev = stage_abbrevs.get(stage_type, "KO")
        for pair in sorted(pair_matches.keys()):
            ms = pair_matches[pair]
            ms.sort(key=lambda m: m.get("kickoff") or "")
            tie_id = f"{abbrev}-{tie_num}"
            for i, m in enumerate(ms):
                m["leg"] = i + 1
                m["tie_id"] = tie_id
            tie_num += 1


# ---------------------------------------------------------------------------
# Team metadata — country and domestic league for display
# ---------------------------------------------------------------------------

TEAM_METADATA = {
    "Arsenal": ("England", "Premier League"),
    "Aston Villa": ("England", "Premier League"),
    "Chelsea": ("England", "Premier League"),
    "Liverpool": ("England", "Premier League"),
    "Manchester City": ("England", "Premier League"),
    "Newcastle United": ("England", "Premier League"),
    "Tottenham Hotspur": ("England", "Premier League"),
    "Barcelona": ("Spain", "La Liga"),
    "Atlético Madrid": ("Spain", "La Liga"),
    "Atletico Madrid": ("Spain", "La Liga"),
    "Real Madrid": ("Spain", "La Liga"),
    "Villarreal": ("Spain", "La Liga"),
    "Bayern Munich": ("Germany", "Bundesliga"),
    "Borussia Dortmund": ("Germany", "Bundesliga"),
    "Bayer Leverkusen": ("Germany", "Bundesliga"),
    "RB Leipzig": ("Germany", "Bundesliga"),
    "Internazionale": ("Italy", "Serie A"),
    "Juventus": ("Italy", "Serie A"),
    "AC Milan": ("Italy", "Serie A"),
    "Paris Saint-Germain": ("France", "Ligue 1"),
    "AS Monaco": ("France", "Ligue 1"),
    "Marseille": ("France", "Ligue 1"),
    "PSV Eindhoven": ("Netherlands", "Eredivisie"),
    "Feyenoord": ("Netherlands", "Eredivisie"),
    "Benfica": ("Portugal", "Primeira Liga"),
    "Sporting CP": ("Portugal", "Primeira Liga"),
    "Celtic": ("Scotland", "Scottish Premiership"),
    "Club Brugge": ("Belgium", "Pro League"),
    "Union St.-Gilloise": ("Belgium", "Pro League"),
    "Galatasaray": ("Turkey", "Süper Lig"),
    "Red Star Belgrade": ("Serbia", "SuperLiga"),
    "Dinamo Zagreb": ("Croatia", "HNL"),
    "Bodo/Glimt": ("Norway", "Eliteserien"),
    "FK Qarabag": ("Azerbaijan", "Premier League"),
    "Red Bull Salzburg": ("Austria", "Bundesliga"),
    "Shakhtar Donetsk": ("Ukraine", "Premier League"),
    "Ajax Amsterdam": ("Netherlands", "Eredivisie"),
    "Atalanta": ("Italy", "Serie A"),
    "Athletic Club": ("Spain", "La Liga"),
    "Eintracht Frankfurt": ("Germany", "Bundesliga"),
    "F.C. København": ("Denmark", "Superliga"),
    "Napoli": ("Italy", "Serie A"),
    "Olympiacos": ("Greece", "Super League"),
    "Slavia Prague": ("Czech Republic", "First League"),
    "Kairat Almaty": ("Kazakhstan", "Premier League"),
    "Pafos": ("Cyprus", "First Division"),
}

# Wikimedia crest URLs for teams without BDL-provided crests
TEAM_CREST_URLS = {
    "Arsenal": "https://upload.wikimedia.org/wikipedia/sco/5/53/Arsenal_FC.svg",
    "Aston Villa": "https://upload.wikimedia.org/wikipedia/en/9/9a/Aston_Villa_FC_new_crest.svg",
    "Chelsea": "https://upload.wikimedia.org/wikipedia/sco/c/cc/Chelsea_FC.svg",
    "Liverpool": "https://upload.wikimedia.org/wikipedia/sco/0/0c/Liverpool_FC.svg",
    "Manchester City": "https://upload.wikimedia.org/wikipedia/sco/e/eb/Manchester_City_FC_badge.svg",
    "Newcastle United": "https://upload.wikimedia.org/wikipedia/sco/5/56/Newcastle_United_Logo.svg",
    "Tottenham Hotspur": "https://upload.wikimedia.org/wikipedia/sco/b/b4/Tottenham_Hotspur.svg",
    "Barcelona": "https://upload.wikimedia.org/wikipedia/sco/4/47/FC_Barcelona_%28crest%29.svg",
    "Real Madrid": "https://upload.wikimedia.org/wikipedia/sco/5/56/Real_Madrid_CF.svg",
    "Bayern Munich": "https://upload.wikimedia.org/wikipedia/commons/1/1b/FC_Bayern_M%C3%BCnchen_logo_%282017%29.svg",
    "Borussia Dortmund": "https://upload.wikimedia.org/wikipedia/commons/6/67/Borussia_Dortmund_logo.svg",
    "Internazionale": "https://upload.wikimedia.org/wikipedia/commons/0/05/FC_Internazionale_Milano_2021.svg",
    "Juventus": "https://upload.wikimedia.org/wikipedia/commons/a/a8/Juventus_FC_-_pictogram.svg",
    "Paris Saint-Germain": "https://upload.wikimedia.org/wikipedia/sco/8/86/Paris_Saint-Germain_F.C..svg",
}


# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------


def sync_stages():
    """Create the 6 UCL tournament stages."""
    from ucl.matches.models import Stage

    stages = [
        ("League Phase", "LEAGUE_PHASE", 1),
        ("Knockout Playoffs", "KNOCKOUT_PLAYOFF", 2),
        ("Round of 16", "ROUND_OF_16", 3),
        ("Quarter-finals", "QUARTER", 4),
        ("Semi-finals", "SEMI", 5),
        ("Final", "FINAL", 6),
    ]
    for name, stage_type, order in stages:
        Stage.objects.update_or_create(
            stage_type=stage_type,
            defaults={"name": name, "order": order},
        )
    logger.info("sync_stages: created/updated %d stages", len(stages))
    return len(stages)


def sync_teams(season=None, offline=False):
    """Sync teams from BDL or static JSON."""
    season = season or getattr(settings, "UCL_CURRENT_SEASON", "2025")

    if offline:
        with open(STATIC_DATA_DIR / "teams.json") as f:
            teams_raw = json.load(f)
        teams_data = [
            {
                "external_id": t["id"],
                "name": t.get("name", ""),
                "short_name": t.get("short_name", ""),
                "tla": t.get("abbreviation", ""),
            }
            for t in teams_raw
        ]
    else:
        with UCLDataClient() as client:
            teams_data = client.get_teams(season)

    created = updated = 0
    for t in teams_data:
        name = t["name"]
        country, domestic_league = TEAM_METADATA.get(name, ("", ""))
        crest_url = TEAM_CREST_URLS.get(name, "")

        _, was_created = Team.objects.update_or_create(
            external_id=t["external_id"],
            defaults={
                "name": name,
                "short_name": t["short_name"],
                "tla": t["tla"],
                "crest_url": crest_url,
                "country": country,
                "domestic_league": domestic_league,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("sync_teams: created=%d updated=%d", created, updated)
    return created, updated


def sync_matches(season=None, offline=False, game_date=None):
    """Sync matches from BDL or static JSON."""
    from ucl.matches.models import Stage

    season = season or getattr(settings, "UCL_CURRENT_SEASON", "2025")

    if offline:
        with open(STATIC_DATA_DIR / "matches.json") as f:
            matches_raw = json.load(f)
        matches_data = []
        for m in matches_raw:
            raw_dt = m.get("date", "")
            kickoff = None
            if raw_dt:
                kickoff = parse_datetime(
                    raw_dt.replace("Z", "+00:00") if raw_dt.endswith("Z") else raw_dt
                )

            raw_status = m.get("status", "")
            status = _normalize_ucl_status(raw_status)
            is_finished = status == Match.Status.FINISHED
            is_live = status in (
                Match.Status.IN_PLAY,
                Match.Status.PAUSED,
                Match.Status.EXTRA_TIME,
                Match.Status.PENALTY_SHOOTOUT,
            )
            home_score = m.get("home_score")
            away_score = m.get("away_score")
            if not is_finished and not is_live:
                home_score = None
                away_score = None

            matches_data.append(
                {
                    "external_id": m["id"],
                    "home_team_external_id": m["home_team_id"],
                    "away_team_external_id": m["away_team_id"],
                    "home_score": home_score,
                    "away_score": away_score,
                    "status": status,
                    "kickoff": kickoff,
                    "season": str(season),
                    "name": m.get("name", ""),
                    "short_name": m.get("short_name", ""),
                    "venue_name": m.get("venue_name", "") or "",
                    "venue_city": m.get("venue_city", "") or "",
                }
            )
    else:
        with UCLDataClient() as client:
            matches_data = client.get_matches(season, game_date=game_date)

    # Assign stages, matchdays, and knockout tie info
    for m in matches_data:
        m["_stage_type"] = _infer_stage(m)

    _assign_matchdays(matches_data)
    _assign_knockout_ties(matches_data)

    team_map = {t.external_id: t for t in Team.objects.all()}
    stage_map = {s.stage_type: s for s in Stage.objects.all()}

    created = updated = skipped = 0
    for m in matches_data:
        home = team_map.get(m["home_team_external_id"])
        away = team_map.get(m["away_team_external_id"])
        if not home or not away:
            skipped += 1
            continue

        stage = stage_map.get(m["_stage_type"])
        if not stage:
            logger.warning(
                "Skipping match %s: unknown stage %s",
                m["external_id"],
                m["_stage_type"],
            )
            skipped += 1
            continue

        _, was_created = Match.objects.update_or_create(
            external_id=m["external_id"],
            defaults={
                "home_team": home,
                "away_team": away,
                "stage": stage,
                "matchday": m.get("matchday"),
                "leg": m.get("leg"),
                "tie_id": m.get("tie_id", ""),
                "home_score": m["home_score"],
                "away_score": m["away_score"],
                "status": m["status"],
                "kickoff": m["kickoff"],
                "venue_name": m["venue_name"],
                "venue_city": m["venue_city"],
                "season": m["season"],
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info(
        "sync_matches: created=%d updated=%d skipped=%d", created, updated, skipped
    )
    return created, updated


def sync_standings(season=None, offline=False):
    """Sync league phase standings from BDL or static JSON."""
    season = season or getattr(settings, "UCL_CURRENT_SEASON", "2025")

    if offline:
        with open(STATIC_DATA_DIR / "standings.json") as f:
            standings_raw = json.load(f)
        standings_data = [
            {
                "team_external_id": s["team"]["id"],
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
                "qualification_note": s.get("note", ""),
            }
            for s in standings_raw
        ]
    else:
        with UCLDataClient() as client:
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
                "qualification_note": s.get("qualification_note", ""),
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("sync_standings: created=%d updated=%d", created, updated)
    return created, updated


def poll_live_scores():
    """Poll for live score updates and broadcast changes via WebSocket."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    live_statuses = [
        Match.Status.IN_PLAY,
        Match.Status.PAUSED,
        Match.Status.EXTRA_TIME,
        Match.Status.PENALTY_SHOOTOUT,
    ]
    live_matches = Match.objects.filter(status__in=live_statuses)
    if not live_matches.exists():
        return

    pre_sync = {m.pk: (m.home_score, m.away_score, m.status) for m in live_matches}

    sync_matches()

    channel_layer = get_channel_layer()
    for match in Match.objects.filter(pk__in=pre_sync.keys()):
        old = pre_sync[match.pk]
        new = (match.home_score, match.away_score, match.status)
        if old != new:
            logger.info("Score change: %s %s -> %s", match, old, new)
            async_to_sync(channel_layer.group_send)(
                "ucl_live_scores",
                {
                    "type": "score_update",
                    "html": f"<!-- score update for {match.pk} -->",
                },
            )

            if match.status == Match.Status.FINISHED:
                from ucl.betting.tasks import settle_match_bets

                settle_match_bets.delay(match.pk)
