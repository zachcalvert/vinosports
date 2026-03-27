"""Tests for matches/services.py — FootballDataClient and sync helpers."""

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from epl.matches.models import Match, MatchStats, Team
from epl.matches.services import (
    FootballDataClient,
    _assign_matchdays,
    _normalize_epl_status,
    fetch_match_hype_data,
    get_head_to_head,
    get_team_form,
    sync_matches,
    sync_standings,
    sync_teams,
)

from .factories import MatchFactory, TeamFactory

pytestmark = pytest.mark.django_db


class TestNormalizeEplStatus:
    def test_known_statuses(self):
        assert _normalize_epl_status("STATUS_SCHEDULED") == Match.Status.SCHEDULED
        assert _normalize_epl_status("STATUS_TIMED") == Match.Status.TIMED
        assert _normalize_epl_status("STATUS_FIRST_HALF") == Match.Status.IN_PLAY
        assert _normalize_epl_status("STATUS_HALFTIME") == Match.Status.PAUSED
        assert _normalize_epl_status("STATUS_SECOND_HALF") == Match.Status.IN_PLAY
        assert _normalize_epl_status("STATUS_FULL_TIME") == Match.Status.FINISHED
        assert _normalize_epl_status("STATUS_FINAL") == Match.Status.FINISHED
        assert _normalize_epl_status("STATUS_POSTPONED") == Match.Status.POSTPONED
        assert _normalize_epl_status("STATUS_CANCELLED") == Match.Status.CANCELLED
        assert _normalize_epl_status("STATUS_SUSPENDED") == Match.Status.POSTPONED

    def test_unknown_status_defaults_to_scheduled(self):
        assert _normalize_epl_status("STATUS_UNKNOWN") == Match.Status.SCHEDULED
        assert _normalize_epl_status("") == Match.Status.SCHEDULED


class TestFootballDataClient:
    @patch("epl.matches.services.httpx.Client")
    def test_get_teams_normalizes(self, mock_httpx_cls):
        mock_client = MagicMock()
        mock_httpx_cls.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "data": [
                {
                    "id": 57,
                    "name": "Arsenal FC",
                    "short_name": "Arsenal",
                    "abbreviation": "ARS",
                }
            ],
            "meta": {},
        }
        mock_client.get.return_value.raise_for_status = MagicMock()

        with FootballDataClient() as client:
            teams = client.get_teams()

        assert len(teams) == 1
        assert teams[0]["external_id"] == 57
        assert teams[0]["name"] == "Arsenal FC"
        assert teams[0]["tla"] == "ARS"
        assert teams[0]["crest_url"] == ""

    @patch("epl.matches.services.httpx.Client")
    def test_get_matches_normalizes(self, mock_httpx_cls):
        mock_client = MagicMock()
        mock_httpx_cls.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "data": [
                {
                    "id": 400001,
                    "home_team_id": 57,
                    "away_team_id": 65,
                    "home_score": 2,
                    "away_score": 1,
                    "status": "STATUS_FULL_TIME",
                    "matchday": 5,
                    "date": "2025-09-20T15:00:00Z",
                }
            ],
            "meta": {},
        }
        mock_client.get.return_value.raise_for_status = MagicMock()

        with FootballDataClient() as client:
            matches = client.get_matches("2025")

        assert len(matches) == 1
        m = matches[0]
        assert m["external_id"] == 400001
        assert m["home_team_external_id"] == 57
        assert m["away_team_external_id"] == 65
        assert m["status"] == Match.Status.FINISHED
        assert m["home_score"] == 2
        assert m["away_score"] == 1
        assert m["matchday"] == 5
        assert m["season"] == "2025"

    @patch("epl.matches.services.httpx.Client")
    def test_get_standings_normalizes(self, mock_httpx_cls):
        mock_client = MagicMock()
        mock_httpx_cls.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "data": [
                {
                    "team": {"id": 57},
                    "rank": 1,
                    "games_played": 10,
                    "wins": 8,
                    "draws": 1,
                    "losses": 1,
                    "goals_for": 25,
                    "goals_against": 10,
                    "goal_differential": 15,
                    "points": 25,
                }
            ],
        }
        mock_client.get.return_value.raise_for_status = MagicMock()

        with FootballDataClient() as client:
            standings = client.get_standings("2025")

        assert len(standings) == 1
        s = standings[0]
        assert s["team_external_id"] == 57
        assert s["position"] == 1
        assert s["points"] == 25
        assert s["goal_difference"] == 15

    @patch("epl.matches.services.httpx.Client")
    def test_pagination(self, mock_httpx_cls):
        mock_client = MagicMock()
        mock_httpx_cls.return_value = mock_client

        page1 = {
            "data": [
                {"id": 1, "name": "Team A", "short_name": "A", "abbreviation": "TA"}
            ],
            "meta": {"next_cursor": "abc123"},
        }
        page2 = {
            "data": [
                {"id": 2, "name": "Team B", "short_name": "B", "abbreviation": "TB"}
            ],
            "meta": {},
        }
        mock_client.get.return_value.json.side_effect = [page1, page2]
        mock_client.get.return_value.raise_for_status = MagicMock()

        with FootballDataClient() as client:
            teams = client.get_teams()

        assert len(teams) == 2
        assert teams[0]["external_id"] == 1
        assert teams[1]["external_id"] == 2

    @patch("epl.matches.services.httpx.Client")
    def test_get_match_single(self, mock_httpx_cls):
        mock_client = MagicMock()
        mock_httpx_cls.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "data": {
                "id": 500,
                "home_team_id": 10,
                "away_team_id": 20,
                "home_score": 1,
                "away_score": 0,
                "status": "STATUS_FIRST_HALF",
                "matchday": 3,
                "date": "2025-10-01T14:00:00Z",
                "season": "2025",
            }
        }
        mock_client.get.return_value.raise_for_status = MagicMock()

        with FootballDataClient() as client:
            m = client.get_match(500)

        assert m["external_id"] == 500
        assert m["status"] == Match.Status.IN_PLAY

    @patch("epl.matches.services.httpx.Client")
    def test_normalize_match_handles_missing_date(self, mock_httpx_cls):
        mock_client = MagicMock()
        mock_httpx_cls.return_value = mock_client
        mock_client.get.return_value.json.return_value = {
            "data": [
                {
                    "id": 999,
                    "home_team_id": 1,
                    "away_team_id": 2,
                    "home_score": None,
                    "away_score": None,
                    "status": "",
                    "matchday": 0,
                    "date": "",
                }
            ],
            "meta": {},
        }
        mock_client.get.return_value.raise_for_status = MagicMock()

        with FootballDataClient() as client:
            matches = client.get_matches("2025")

        assert matches[0]["kickoff"] is None


class TestAssignMatchdays:
    def test_assigns_matchdays_in_batches_of_10(self):
        matches = [
            {"kickoff": f"2025-09-{i + 1:02d}T15:00:00+00:00"} for i in range(20)
        ]
        _assign_matchdays(matches)
        # First 10 should be matchday 1, next 10 matchday 2
        assert matches[0]["matchday"] == 1
        assert matches[9]["matchday"] == 1
        assert matches[10]["matchday"] == 2
        assert matches[19]["matchday"] == 2

    def test_handles_empty_list(self):
        matches = []
        _assign_matchdays(matches)
        assert matches == []


class TestSyncTeams:
    @patch("epl.matches.services.FootballDataClient")
    def test_creates_new_teams(self, mock_client_cls):
        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get_teams.return_value = [
            {
                "external_id": 100,
                "name": "New Team",
                "short_name": "NT",
                "tla": "NWT",
                "crest_url": "",
                "venue": "",
            }
        ]

        created, updated = sync_teams("2025")
        assert created == 1
        assert updated == 0
        assert Team.objects.filter(external_id=100).exists()

    @patch("epl.matches.services.FootballDataClient")
    def test_updates_existing_teams(self, mock_client_cls):
        TeamFactory(external_id=100, name="Old Name")

        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get_teams.return_value = [
            {
                "external_id": 100,
                "name": "New Name",
                "short_name": "NN",
                "tla": "NWN",
                "crest_url": "",
                "venue": "",
            }
        ]

        created, updated = sync_teams("2025")
        assert created == 0
        assert updated == 1
        assert Team.objects.get(external_id=100).name == "New Name"


class TestSyncMatches:
    @patch("epl.matches.services.FootballDataClient")
    def test_creates_matches(self, mock_client_cls):
        TeamFactory(external_id=10)
        TeamFactory(external_id=20)

        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get_matches.return_value = [
            {
                "external_id": 5001,
                "home_team_external_id": 10,
                "away_team_external_id": 20,
                "home_score": None,
                "away_score": None,
                "status": Match.Status.SCHEDULED,
                "matchday": 1,
                "kickoff": timezone.now(),
                "season": "2025",
            }
        ]

        created, updated = sync_matches("2025")
        assert created == 1
        assert updated == 0

    @patch("epl.matches.services.FootballDataClient")
    def test_skips_matches_with_missing_teams(self, mock_client_cls):
        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get_matches.return_value = [
            {
                "external_id": 5002,
                "home_team_external_id": 999,
                "away_team_external_id": 998,
                "home_score": None,
                "away_score": None,
                "status": Match.Status.SCHEDULED,
                "matchday": 1,
                "kickoff": timezone.now(),
                "season": "2025",
            }
        ]

        created, updated = sync_matches("2025")
        assert created == 0
        assert updated == 0


class TestSyncStandings:
    @patch("epl.matches.services.FootballDataClient")
    def test_creates_standings(self, mock_client_cls):
        TeamFactory(external_id=10)

        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get_standings.return_value = [
            {
                "team_external_id": 10,
                "season": "2025",
                "position": 1,
                "played": 10,
                "won": 8,
                "drawn": 1,
                "lost": 1,
                "goals_for": 25,
                "goals_against": 10,
                "goal_difference": 15,
                "points": 25,
            }
        ]

        created, updated = sync_standings("2025")
        assert created == 1
        assert updated == 0

    @patch("epl.matches.services.FootballDataClient")
    def test_skips_standings_with_missing_teams(self, mock_client_cls):
        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get_standings.return_value = [
            {
                "team_external_id": 999,
                "season": "2025",
                "position": 1,
                "played": 10,
                "won": 8,
                "drawn": 1,
                "lost": 1,
                "goals_for": 25,
                "goals_against": 10,
                "goal_difference": 15,
                "points": 25,
            }
        ]

        created, updated = sync_standings("2025")
        assert created == 0
        assert updated == 0


class TestGetTeamForm:
    def test_returns_recent_results(self):
        team = TeamFactory()
        other = TeamFactory()
        now = timezone.now()
        # Home win
        MatchFactory(
            home_team=team,
            away_team=other,
            home_score=2,
            away_score=1,
            status=Match.Status.FINISHED,
            kickoff=now - timezone.timedelta(days=3),
        )
        # Away loss
        MatchFactory(
            home_team=other,
            away_team=team,
            home_score=3,
            away_score=0,
            status=Match.Status.FINISHED,
            kickoff=now - timezone.timedelta(days=2),
        )
        # Away draw
        MatchFactory(
            home_team=other,
            away_team=team,
            home_score=1,
            away_score=1,
            status=Match.Status.FINISHED,
            kickoff=now - timezone.timedelta(days=1),
        )

        form = get_team_form(team, limit=5)
        assert len(form) == 3
        # Oldest first (reversed)
        assert form[0]["result"] == "W"
        assert form[1]["result"] == "L"
        assert form[2]["result"] == "D"

    def test_empty_when_no_matches(self):
        team = TeamFactory()
        form = get_team_form(team)
        assert form == []


class TestGetHeadToHead:
    def test_returns_h2h_data(self):
        home = TeamFactory()
        away = TeamFactory()
        now = timezone.now()

        # The "current" match
        current = MatchFactory(
            home_team=home,
            away_team=away,
            status=Match.Status.SCHEDULED,
            kickoff=now + timezone.timedelta(days=1),
        )

        # Past h2h: home wins
        MatchFactory(
            home_team=home,
            away_team=away,
            home_score=2,
            away_score=0,
            status=Match.Status.FINISHED,
            kickoff=now - timezone.timedelta(days=10),
        )
        # Past h2h: away wins (reversed fixture)
        MatchFactory(
            home_team=away,
            away_team=home,
            home_score=3,
            away_score=1,
            status=Match.Status.FINISHED,
            kickoff=now - timezone.timedelta(days=5),
        )

        h2h_matches, summary = get_head_to_head(current)
        assert len(h2h_matches) == 2
        assert summary["home_wins"] == 1
        assert summary["away_wins"] == 1
        assert summary["draws"] == 0

    def test_excludes_current_match(self):
        home = TeamFactory()
        away = TeamFactory()
        now = timezone.now()

        current = MatchFactory(
            home_team=home,
            away_team=away,
            home_score=1,
            away_score=1,
            status=Match.Status.FINISHED,
            kickoff=now,
        )

        h2h_matches, summary = get_head_to_head(current)
        assert len(h2h_matches) == 0


class TestFetchMatchHypeData:
    def test_creates_and_populates_stats(self):
        home = TeamFactory()
        away = TeamFactory()
        match = MatchFactory(home_team=home, away_team=away)

        stats = fetch_match_hype_data(match)
        assert isinstance(stats, MatchStats)
        assert stats.match == match
        assert stats.fetched_at is not None

    def test_skips_if_not_stale(self):
        home = TeamFactory()
        away = TeamFactory()
        match = MatchFactory(home_team=home, away_team=away)
        stats = MatchStats.objects.create(
            match=match,
            fetched_at=timezone.now(),
        )

        result = fetch_match_hype_data(match)
        assert result.pk == stats.pk
        # Should not have re-fetched

    def test_handles_exception_gracefully(self):
        home = TeamFactory()
        away = TeamFactory()
        match = MatchFactory(home_team=home, away_team=away)

        with patch(
            "epl.matches.services.get_head_to_head",
            side_effect=Exception("boom"),
        ):
            stats = fetch_match_hype_data(match)
            assert stats.last_attempt_at is not None
