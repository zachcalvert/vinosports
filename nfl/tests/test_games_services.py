"""Tests for nfl/games/services.py (NFLDataClient, sync helpers, standings computation)."""

from unittest.mock import MagicMock

import pytest

from nfl.games.models import (
    Conference,
    Division,
    Game,
    GameStatus,
    Player,
    Standing,
    Team,
)
from nfl.games.services import (
    NFLDataClient,
    _normalize_division,
    _normalize_status,
    compute_standings,
    sync_games,
    sync_players,
    sync_teams,
)
from nfl.tests.factories import GameFactory, TeamFactory


class TestNormalizeStatus:
    def test_final(self):
        assert _normalize_status("Final") == GameStatus.FINAL

    def test_final_ot(self):
        assert _normalize_status("Final/OT") == GameStatus.FINAL_OT

    def test_halftime(self):
        assert _normalize_status("Halftime") == GameStatus.HALFTIME

    def test_quarters_map_to_in_progress(self):
        for q in ("1st Quarter", "2nd Quarter", "3rd Quarter", "4th Quarter"):
            assert _normalize_status(q) == GameStatus.IN_PROGRESS

    def test_overtime_maps_to_in_progress(self):
        assert _normalize_status("Overtime") == GameStatus.IN_PROGRESS

    def test_unknown_defaults_to_scheduled(self):
        assert _normalize_status("SomeOtherStatus") == GameStatus.SCHEDULED

    def test_empty_defaults_to_scheduled(self):
        assert _normalize_status("") == GameStatus.SCHEDULED


class TestNormalizeDivision:
    def test_afc_east(self):
        assert _normalize_division("AFC", "EAST") == Division.AFC_EAST

    def test_nfc_west(self):
        assert _normalize_division("NFC", "WEST") == Division.NFC_WEST

    def test_unknown_defaults(self):
        assert _normalize_division("XFL", "SOUTH") == Division.AFC_EAST


class TestNFLDataClientNormalizers:
    def setup_method(self):
        self.client = NFLDataClient.__new__(NFLDataClient)

    def test_normalize_team(self):
        raw = {
            "id": 14,
            "full_name": "Kansas City Chiefs",
            "name": "Chiefs",
            "abbreviation": "KC",
            "location": "Kansas City",
            "conference": "AFC",
            "division": "WEST",
        }
        result = self.client._normalize_team(raw)
        assert result["external_id"] == 14
        assert result["name"] == "Kansas City Chiefs"
        assert result["short_name"] == "Chiefs"
        assert result["abbreviation"] == "KC"
        assert result["location"] == "Kansas City"
        assert result["conference"] == "AFC"
        assert result["division"] == Division.AFC_WEST

    def test_normalize_game(self):
        raw = {
            "id": 42,
            "home_team": {"id": 14},
            "visitor_team": {"id": 3},
            "home_team_score": 27,
            "visitor_team_score": 24,
            "status": "Final",
            "date": "2025-09-08T20:20:00.000Z",
            "season": 2025,
            "week": 1,
            "postseason": False,
            "venue": "Arrowhead Stadium",
            "home_team_q1": 7,
            "home_team_q2": 10,
            "home_team_q3": 3,
            "home_team_q4": 7,
            "home_team_ot": None,
            "visitor_team_q1": 3,
            "visitor_team_q2": 7,
            "visitor_team_q3": 7,
            "visitor_team_q4": 7,
            "visitor_team_ot": None,
        }
        result = self.client._normalize_game(raw)
        assert result["external_id"] == 42
        assert result["home_team_external_id"] == 14
        assert result["away_team_external_id"] == 3
        assert result["home_score"] == 27
        assert result["away_score"] == 24
        assert result["status"] == GameStatus.FINAL
        assert result["week"] == 1
        assert result["venue"] == "Arrowhead Stadium"
        assert result["home_q1"] == 7
        assert result["away_q4"] == 7
        assert result["home_ot"] is None

    def test_normalize_game_final_ot(self):
        raw = {
            "id": 99,
            "home_team": {"id": 3},
            "visitor_team": {"id": 4},
            "home_team_score": 31,
            "visitor_team_score": 37,
            "status": "Final/OT",
            "date": "2025-09-08T17:00:00.000Z",
            "season": 2025,
            "week": 1,
            "postseason": False,
            "venue": "Highmark Stadium",
            "home_team_q1": 3,
            "home_team_q2": 14,
            "home_team_q3": 7,
            "home_team_q4": 7,
            "home_team_ot": 0,
            "visitor_team_q1": 0,
            "visitor_team_q2": 17,
            "visitor_team_q3": 3,
            "visitor_team_q4": 11,
            "visitor_team_ot": 6,
        }
        result = self.client._normalize_game(raw)
        assert result["status"] == GameStatus.FINAL_OT
        assert result["home_ot"] == 0
        assert result["away_ot"] == 6

    def test_normalize_player(self):
        raw = {
            "id": 500,
            "first_name": "Patrick",
            "last_name": "Mahomes",
            "position": "Quarterback",
            "position_abbreviation": "QB",
            "height": "6-3",
            "weight": 225,
            "jersey_number": "15",
            "college": "Texas Tech",
            "experience": 8,
            "age": 30,
            "team": {"id": 14},
        }
        result = self.client._normalize_player(raw)
        assert result["external_id"] == 500
        assert result["first_name"] == "Patrick"
        assert result["last_name"] == "Mahomes"
        assert result["position"] == "Quarterback"
        assert result["position_abbreviation"] == "QB"
        assert result["weight"] == 225
        assert result["experience"] == 8
        assert result["age"] == 30
        assert result["team_external_id"] == 14

    def test_normalize_player_no_team(self):
        raw = {
            "id": 501,
            "first_name": "Free",
            "last_name": "Agent",
            "position": None,
            "position_abbreviation": None,
            "height": None,
            "weight": None,
            "jersey_number": None,
            "college": None,
            "experience": None,
            "age": None,
            "team": None,
        }
        result = self.client._normalize_player(raw)
        assert result["team_external_id"] is None
        assert result["position"] == ""
        assert result["weight"] is None


@pytest.mark.django_db
class TestSyncTeams:
    def test_creates_teams(self):
        mock_client = MagicMock(spec=NFLDataClient)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_teams.return_value = [
            {
                "external_id": 14,
                "name": "Kansas City Chiefs",
                "short_name": "Chiefs",
                "abbreviation": "KC",
                "location": "Kansas City",
                "conference": "AFC",
                "division": Division.AFC_WEST,
            },
        ]
        count = sync_teams(client=mock_client)
        assert count == 1
        team = Team.objects.get(external_id=14)
        assert team.name == "Kansas City Chiefs"
        assert team.abbreviation == "KC"

    def test_updates_existing_team(self):
        TeamFactory(external_id=14, name="Old Name")
        mock_client = MagicMock(spec=NFLDataClient)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_teams.return_value = [
            {
                "external_id": 14,
                "name": "Kansas City Chiefs",
                "short_name": "Chiefs",
                "abbreviation": "KC",
                "location": "Kansas City",
                "conference": "AFC",
                "division": Division.AFC_WEST,
            },
        ]
        count = sync_teams(client=mock_client)
        assert count == 1
        assert Team.objects.get(external_id=14).name == "Kansas City Chiefs"


@pytest.mark.django_db
class TestSyncGames:
    def test_creates_games(self):
        home = TeamFactory(external_id=14)
        away = TeamFactory(external_id=3)
        mock_client = MagicMock(spec=NFLDataClient)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_games.return_value = [
            {
                "external_id": 42,
                "home_team_external_id": 14,
                "away_team_external_id": 3,
                "home_score": 27,
                "away_score": 24,
                "status": GameStatus.FINAL,
                "game_date": "2025-09-08",
                "kickoff": None,
                "season": 2025,
                "week": 1,
                "postseason": False,
                "venue": "Arrowhead Stadium",
                "home_q1": 7,
                "home_q2": 10,
                "home_q3": 3,
                "home_q4": 7,
                "home_ot": None,
                "away_q1": 3,
                "away_q2": 7,
                "away_q3": 7,
                "away_q4": 7,
                "away_ot": None,
            },
        ]
        count = sync_games(2025, client=mock_client)
        assert count == 1
        game = Game.objects.get(external_id=42)
        assert game.home_team == home
        assert game.away_team == away
        assert game.home_score == 27
        assert game.week == 1

    def test_skips_unknown_teams(self):
        mock_client = MagicMock(spec=NFLDataClient)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_games.return_value = [
            {
                "external_id": 99,
                "home_team_external_id": 999,
                "away_team_external_id": 998,
                "home_score": None,
                "away_score": None,
                "status": GameStatus.SCHEDULED,
                "game_date": "2025-09-08",
                "kickoff": None,
                "season": 2025,
                "week": 1,
                "postseason": False,
                "venue": "",
                "home_q1": None,
                "home_q2": None,
                "home_q3": None,
                "home_q4": None,
                "home_ot": None,
                "away_q1": None,
                "away_q2": None,
                "away_q3": None,
                "away_q4": None,
                "away_ot": None,
            },
        ]
        count = sync_games(2025, client=mock_client)
        assert count == 0


@pytest.mark.django_db
class TestSyncPlayers:
    def test_creates_players(self):
        TeamFactory(external_id=14)
        mock_client = MagicMock(spec=NFLDataClient)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_players.return_value = [
            {
                "external_id": 500,
                "first_name": "Patrick",
                "last_name": "Mahomes",
                "position": "Quarterback",
                "position_abbreviation": "QB",
                "height": "6-3",
                "weight": 225,
                "jersey_number": "15",
                "college": "Texas Tech",
                "experience": 8,
                "age": 30,
                "team_external_id": 14,
            },
        ]
        count = sync_players(client=mock_client)
        assert count == 1
        player = Player.objects.get(external_id=500)
        assert player.first_name == "Patrick"
        assert player.team.external_id == 14
        assert player.is_active is True


@pytest.mark.django_db
class TestComputeStandings:
    def test_computes_from_game_results(self):
        kc = TeamFactory(
            external_id=14, conference=Conference.AFC, division=Division.AFC_WEST
        )
        buf = TeamFactory(
            external_id=3, conference=Conference.AFC, division=Division.AFC_EAST
        )
        # KC beats BUF
        GameFactory(
            home_team=kc,
            away_team=buf,
            status=GameStatus.FINAL,
            home_score=27,
            away_score=24,
            season=2025,
        )
        # BUF beats KC
        GameFactory(
            home_team=buf,
            away_team=kc,
            status=GameStatus.FINAL,
            home_score=31,
            away_score=17,
            season=2025,
        )

        count = compute_standings(2025)
        assert count == 2

        kc_standing = Standing.objects.get(team=kc, season=2025)
        assert kc_standing.wins == 1
        assert kc_standing.losses == 1
        assert kc_standing.win_pct == 0.5
        assert kc_standing.points_for == 44  # 27 + 17
        assert kc_standing.points_against == 55  # 24 + 31
        assert kc_standing.conference_wins == 1
        assert kc_standing.conference_losses == 1

    def test_handles_ties(self):
        t1 = TeamFactory(conference=Conference.AFC, division=Division.AFC_EAST)
        t2 = TeamFactory(conference=Conference.AFC, division=Division.AFC_EAST)
        GameFactory(
            home_team=t1,
            away_team=t2,
            status=GameStatus.FINAL_OT,
            home_score=20,
            away_score=20,
            season=2025,
        )

        compute_standings(2025)

        s1 = Standing.objects.get(team=t1, season=2025)
        assert s1.wins == 0
        assert s1.losses == 0
        assert s1.ties == 1
        assert s1.win_pct == 0.5  # (0 + 0.5*1) / 1

    def test_tracks_division_record(self):
        t1 = TeamFactory(conference=Conference.AFC, division=Division.AFC_WEST)
        t2 = TeamFactory(conference=Conference.AFC, division=Division.AFC_WEST)
        GameFactory(
            home_team=t1,
            away_team=t2,
            status=GameStatus.FINAL,
            home_score=24,
            away_score=17,
            season=2025,
        )

        compute_standings(2025)

        s1 = Standing.objects.get(team=t1, season=2025)
        assert s1.division_wins == 1
        assert s1.division_losses == 0
