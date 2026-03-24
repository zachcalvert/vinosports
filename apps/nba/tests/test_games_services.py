"""Tests for games/services.py (NBADataClient, sync helpers, standings computation)."""

from unittest.mock import MagicMock, patch

import pytest
from games.models import Conference, Game, GameStatus, Standing, Team
from games.services import (
    NBADataClient,
    _compute_standings_from_games,
    _normalize_conference,
    _normalize_status,
    sync_games,
    sync_live_scores,
    sync_standings,
    sync_teams,
)

from tests.factories import GameFactory, StandingFactory, TeamFactory


class TestNormalizeStatus:
    def test_final_maps_correctly(self):
        assert _normalize_status("Final") == GameStatus.FINAL

    def test_halftime_maps_correctly(self):
        assert _normalize_status("Halftime") == GameStatus.HALFTIME

    def test_first_qtr_maps_to_in_progress(self):
        assert _normalize_status("1st Qtr") == GameStatus.IN_PROGRESS

    def test_second_qtr_maps_to_in_progress(self):
        assert _normalize_status("2nd Qtr") == GameStatus.IN_PROGRESS

    def test_third_qtr_maps_to_in_progress(self):
        assert _normalize_status("3rd Qtr") == GameStatus.IN_PROGRESS

    def test_fourth_qtr_maps_to_in_progress(self):
        assert _normalize_status("4th Qtr") == GameStatus.IN_PROGRESS

    def test_iso_timestamp_maps_to_scheduled(self):
        assert _normalize_status("2026-03-24T23:00:00.000Z") == GameStatus.SCHEDULED

    def test_unknown_status_defaults_to_scheduled(self):
        assert _normalize_status("UnknownStatus") == GameStatus.SCHEDULED

    def test_empty_string_defaults_to_scheduled(self):
        assert _normalize_status("") == GameStatus.SCHEDULED


class TestNormalizeConference:
    def test_east_maps_correctly(self):
        assert _normalize_conference("East") == Conference.EAST

    def test_west_maps_correctly(self):
        assert _normalize_conference("West") == Conference.WEST

    def test_unknown_defaults_to_east(self):
        assert _normalize_conference("Unknown") == Conference.EAST

    def test_empty_string_defaults_to_east(self):
        assert _normalize_conference("") == Conference.EAST


class TestNBADataClientNormalizers:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_normalize_team_extracts_fields(self):
        raw = {
            "id": 14,
            "name": "Lakers",
            "full_name": "Los Angeles Lakers",
            "city": "Los Angeles",
            "abbreviation": "LAL",
            "conference": "West",
            "division": "Pacific",
        }
        result = self.client._normalize_team(raw)
        assert result["external_id"] == 14
        assert result["name"] == "Lakers"
        assert result["short_name"] == "Los Angeles Lakers"
        assert result["abbreviation"] == "LAL"
        assert result["logo_url"] == ""
        assert result["conference"] == Conference.WEST
        assert result["division"] == "Pacific"

    def test_normalize_game_with_datetime(self):
        raw = {
            "id": 18447232,
            "home_team": {
                "id": 20,
                "abbreviation": "NYK",
                "city": "New York",
                "name": "Knicks",
            },
            "visitor_team": {
                "id": 6,
                "abbreviation": "CLE",
                "city": "Cleveland",
                "name": "Cavaliers",
            },
            "home_team_score": 126,
            "visitor_team_score": 124,
            "status": "Final",
            "date": "2025-12-25",
            "datetime": "2025-12-25T17:00:00.000Z",
            "season": 2025,
            "postseason": False,
        }
        result = self.client._normalize_game(raw)
        assert result["external_id"] == 18447232
        assert result["home_team_external_id"] == 20
        assert result["away_team_external_id"] == 6
        assert result["home_score"] == 126
        assert result["away_score"] == 124
        assert result["status"] == GameStatus.FINAL
        assert result["game_date"] == "2025-12-25"
        assert result["tip_off"] is not None
        assert result["season"] == 2025
        assert result["postseason"] is False

    def test_normalize_game_postseason_flag(self):
        raw = {
            "id": 1002,
            "home_team": {"id": 10},
            "visitor_team": {"id": 20},
            "home_team_score": None,
            "visitor_team_score": None,
            "status": "2026-04-20T20:00:00.000Z",
            "date": "2026-04-20",
            "datetime": "2026-04-20T20:00:00.000Z",
            "season": 2025,
            "postseason": True,
        }
        result = self.client._normalize_game(raw)
        assert result["postseason"] is True

    def test_normalize_game_scheduled_status_from_iso(self):
        raw = {
            "id": 1003,
            "home_team": {"id": 10},
            "visitor_team": {"id": 20},
            "home_team_score": 0,
            "visitor_team_score": 0,
            "status": "2026-03-25T00:00:00.000Z",
            "date": "2026-03-25",
            "datetime": "2026-03-25T00:00:00.000Z",
            "season": 2025,
            "postseason": False,
        }
        result = self.client._normalize_game(raw)
        assert result["status"] == GameStatus.SCHEDULED

    def test_normalize_game_missing_datetime_uses_date(self):
        raw = {
            "id": 1004,
            "home_team": {"id": 10},
            "visitor_team": {"id": 20},
            "home_team_score": None,
            "visitor_team_score": None,
            "status": "Final",
            "date": "2025-03-21",
            "season": 2025,
            "postseason": False,
        }
        result = self.client._normalize_game(raw)
        assert result["game_date"] == "2025-03-21"
        assert result["tip_off"] is None

    def test_normalize_standing_calculates_win_pct(self):
        raw = {
            "team": {"id": 10, "conference": "East"},
            "season": 2025,
            "wins": 40,
            "losses": 20,
            "home_record": "25-5",
            "road_record": "15-15",
            "conference_rank": 2,
        }
        result = self.client._normalize_standing(raw)
        assert result["team_external_id"] == 10
        assert result["wins"] == 40
        assert result["losses"] == 20
        assert result["win_pct"] == round(40 / 60, 3)
        assert result["home_record"] == "25-5"
        assert result["away_record"] == "15-15"
        assert result["conference_rank"] == 2

    def test_normalize_standing_zero_games_win_pct(self):
        raw = {
            "team": {"id": 10, "conference": "East"},
            "season": 2025,
            "wins": 0,
            "losses": 0,
            "home_record": "",
            "road_record": "",
            "conference_rank": 1,
        }
        result = self.client._normalize_standing(raw)
        assert result["win_pct"] == 0.0


@pytest.mark.django_db
class TestSyncTeams:
    def test_creates_teams_from_api(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_teams.return_value = [
            {
                "external_id": 9001,
                "name": "Warriors",
                "short_name": "Golden State Warriors",
                "abbreviation": "GSW",
                "logo_url": "",
                "conference": Conference.WEST,
                "division": "Pacific",
            }
        ]
        count = sync_teams(client=mock_client)
        assert count == 1
        assert Team.objects.filter(external_id=9001).exists()

    def test_updates_existing_team(self):
        team = TeamFactory(external_id=9002, name="OldName")
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_teams.return_value = [
            {
                "external_id": 9002,
                "name": "NewName",
                "short_name": "City NewName",
                "abbreviation": "NEW",
                "logo_url": "",
                "conference": Conference.EAST,
                "division": "Atlantic",
            }
        ]
        sync_teams(client=mock_client)
        team.refresh_from_db()
        assert team.name == "NewName"

    def test_returns_zero_for_empty_response(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_teams.return_value = []
        count = sync_teams(client=mock_client)
        assert count == 0


@pytest.mark.django_db
class TestSyncGames:
    def test_creates_games_for_known_teams(self):
        TeamFactory(external_id=1001)
        TeamFactory(external_id=1002)
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_games.return_value = [
            {
                "external_id": 5001,
                "home_team_external_id": 1001,
                "away_team_external_id": 1002,
                "home_score": None,
                "away_score": None,
                "status": GameStatus.SCHEDULED,
                "game_date": "2025-03-20",
                "tip_off": None,
                "season": 2025,
                "arena": "",
                "postseason": False,
            }
        ]
        count = sync_games(2025, client=mock_client)
        assert count == 1
        assert Game.objects.filter(external_id=5001).exists()

    def test_skips_unknown_teams(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_games.return_value = [
            {
                "external_id": 5002,
                "home_team_external_id": 9999,
                "away_team_external_id": 8888,
                "home_score": None,
                "away_score": None,
                "status": GameStatus.SCHEDULED,
                "game_date": "2025-03-20",
                "tip_off": None,
                "season": 2025,
                "arena": "",
                "postseason": False,
            }
        ]
        count = sync_games(2025, client=mock_client)
        assert count == 0
        assert not Game.objects.filter(external_id=5002).exists()

    def test_updates_existing_game(self):
        home = TeamFactory(external_id=2001)
        away = TeamFactory(external_id=2002)
        game = GameFactory(
            external_id=6001,
            home_team=home,
            away_team=away,
            status=GameStatus.SCHEDULED,
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_games.return_value = [
            {
                "external_id": 6001,
                "home_team_external_id": 2001,
                "away_team_external_id": 2002,
                "home_score": 110,
                "away_score": 100,
                "status": GameStatus.FINAL,
                "game_date": "2025-03-20",
                "tip_off": None,
                "season": 2025,
                "arena": "",
                "postseason": False,
            }
        ]
        sync_games(2025, client=mock_client)
        game.refresh_from_db()
        assert game.status == GameStatus.FINAL
        assert game.home_score == 110


@pytest.mark.django_db
class TestSyncStandings:
    def test_creates_standings_for_known_teams(self):
        team = TeamFactory(external_id=3001)
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_standings.return_value = [
            {
                "team_external_id": 3001,
                "season": 2025,
                "conference": Conference.EAST,
                "wins": 40,
                "losses": 20,
                "win_pct": 0.667,
                "games_behind": 0.0,
                "streak": "W3",
                "home_record": "25-5",
                "away_record": "15-15",
                "conference_rank": 2,
            }
        ]
        count = sync_standings(2025, client=mock_client)
        assert count == 1
        assert Standing.objects.filter(team=team, season=2025).exists()

    def test_skips_unknown_teams(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_standings.return_value = [
            {
                "team_external_id": 9999,
                "season": 2025,
                "conference": Conference.EAST,
                "wins": 30,
                "losses": 30,
                "win_pct": 0.500,
                "games_behind": 5.0,
                "streak": "L2",
                "home_record": "15-15",
                "away_record": "15-15",
                "conference_rank": 8,
            }
        ]
        count = sync_standings(2025, client=mock_client)
        assert count == 0

    def test_updates_existing_standing(self):
        team = TeamFactory(external_id=4001)
        standing = StandingFactory(team=team, season=2025, wins=30)
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_standings.return_value = [
            {
                "team_external_id": 4001,
                "season": 2025,
                "conference": Conference.EAST,
                "wins": 45,
                "losses": 15,
                "win_pct": 0.750,
                "games_behind": 0.0,
                "streak": "W5",
                "home_record": "28-2",
                "away_record": "17-13",
                "conference_rank": 1,
            }
        ]
        sync_standings(2025, client=mock_client)
        standing.refresh_from_db()
        assert standing.wins == 45

    def test_falls_back_to_computed_standings_on_api_error(self):
        """When the API raises (e.g. 401), standings are computed from games."""
        import httpx

        home = TeamFactory(external_id=7001, conference=Conference.EAST)
        away = TeamFactory(external_id=7002, conference=Conference.WEST)
        GameFactory(
            external_id=90001,
            home_team=home,
            away_team=away,
            season=2025,
            status=GameStatus.FINAL,
            home_score=110,
            away_score=100,
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.request = httpx.Request("GET", "https://example.com")
        mock_client.get_standings.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=mock_response.request, response=mock_response
        )

        count = sync_standings(2025, client=mock_client)
        assert count == 2
        assert Standing.objects.filter(
            team=home, season=2025, wins=1, losses=0
        ).exists()
        assert Standing.objects.filter(
            team=away, season=2025, wins=0, losses=1
        ).exists()


@pytest.mark.django_db
class TestComputeStandingsFromGames:
    def test_computes_records_from_final_games(self):
        home = TeamFactory(external_id=8001, conference=Conference.EAST)
        away = TeamFactory(external_id=8002, conference=Conference.WEST)
        GameFactory(
            external_id=80001,
            home_team=home,
            away_team=away,
            season=2025,
            status=GameStatus.FINAL,
            home_score=110,
            away_score=100,
        )
        GameFactory(
            external_id=80002,
            home_team=away,
            away_team=home,
            season=2025,
            status=GameStatus.FINAL,
            home_score=105,
            away_score=95,
        )
        count = _compute_standings_from_games(2025)
        assert count == 2
        home_standing = Standing.objects.get(team=home, season=2025)
        assert home_standing.wins == 1
        assert home_standing.losses == 1
        assert home_standing.home_record == "1-0"
        assert home_standing.away_record == "0-1"

    def test_ignores_non_final_games(self):
        home = TeamFactory(external_id=8003)
        away = TeamFactory(external_id=8004)
        GameFactory(
            external_id=80003,
            home_team=home,
            away_team=away,
            season=2025,
            status=GameStatus.SCHEDULED,
        )
        count = _compute_standings_from_games(2025)
        assert count == 0


@pytest.mark.django_db
class TestSyncLiveScores:
    def test_no_games_in_progress_returns_zero(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_live_scores.return_value = []
        count = sync_live_scores(client=mock_client)
        assert count == 0

    def test_updates_score_for_known_game(self):
        home = TeamFactory(external_id=5001)
        away = TeamFactory(external_id=5002)
        game = GameFactory(
            external_id=7001,
            home_team=home,
            away_team=away,
            status=GameStatus.IN_PROGRESS,
            home_score=55,
            away_score=50,
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_live_scores.return_value = [
            {
                "external_id": 7001,
                "home_team_external_id": 5001,
                "away_team_external_id": 5002,
                "home_score": 80,
                "away_score": 75,
                "status": GameStatus.IN_PROGRESS,
                "game_date": "2025-03-20",
                "tip_off": None,
                "season": 2025,
                "arena": "",
                "postseason": False,
            }
        ]

        with patch("games.services._broadcast_score_updates"):
            count = sync_live_scores(client=mock_client)

        assert count == 1
        game.refresh_from_db()
        assert game.home_score == 80
        assert game.away_score == 75

    def test_skips_unknown_game_external_id(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_live_scores.return_value = [
            {
                "external_id": 99999,
                "home_team_external_id": 5001,
                "away_team_external_id": 5002,
                "home_score": 80,
                "away_score": 75,
                "status": GameStatus.IN_PROGRESS,
                "game_date": "2025-03-20",
                "tip_off": None,
                "season": 2025,
                "arena": "",
                "postseason": False,
            }
        ]
        count = sync_live_scores(client=mock_client)
        assert count == 0

    def test_unchanged_score_does_not_broadcast(self):
        home = TeamFactory(external_id=6001)
        away = TeamFactory(external_id=6002)
        GameFactory(
            external_id=8001,
            home_team=home,
            away_team=away,
            status=GameStatus.IN_PROGRESS,
            home_score=80,
            away_score=75,
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_live_scores.return_value = [
            {
                "external_id": 8001,
                "home_team_external_id": 6001,
                "away_team_external_id": 6002,
                "home_score": 80,
                "away_score": 75,
                "status": GameStatus.IN_PROGRESS,
                "game_date": "2025-03-20",
                "tip_off": None,
                "season": 2025,
                "arena": "",
                "postseason": False,
            }
        ]
        with patch("games.services._broadcast_score_updates") as mock_broadcast:
            sync_live_scores(client=mock_client)

        mock_broadcast.assert_not_called()
