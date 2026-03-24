"""Tests for games/services.py (NBADataClient, sync_teams, sync_games, sync_standings, sync_live_scores)."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from games.models import Conference, Game, GameStatus, Standing, Team
from games.services import (
    NBADataClient,
    _normalize_conference,
    _normalize_status,
    _sportsdata_date,
    sync_games,
    sync_live_scores,
    sync_standings,
    sync_teams,
)
from tests.factories import GameFactory, StandingFactory, TeamFactory


class TestNormalizeStatus:
    def test_scheduled_maps_correctly(self):
        assert _normalize_status("Scheduled") == GameStatus.SCHEDULED

    def test_in_progress_maps_correctly(self):
        assert _normalize_status("InProgress") == GameStatus.IN_PROGRESS

    def test_halftime_maps_correctly(self):
        assert _normalize_status("Halftime") == GameStatus.HALFTIME

    def test_final_maps_correctly(self):
        assert _normalize_status("Final") == GameStatus.FINAL

    def test_f_ot_maps_to_final(self):
        assert _normalize_status("F/OT") == GameStatus.FINAL

    def test_postponed_maps_correctly(self):
        assert _normalize_status("Postponed") == GameStatus.POSTPONED

    def test_canceled_maps_correctly(self):
        assert _normalize_status("Canceled") == GameStatus.CANCELLED

    def test_forfeit_maps_to_cancelled(self):
        assert _normalize_status("Forfeit") == GameStatus.CANCELLED

    def test_delayed_maps_to_scheduled(self):
        assert _normalize_status("Delayed") == GameStatus.SCHEDULED

    def test_suspended_maps_to_scheduled(self):
        assert _normalize_status("Suspended") == GameStatus.SCHEDULED

    def test_unknown_status_defaults_to_scheduled(self):
        assert _normalize_status("UnknownStatus") == GameStatus.SCHEDULED

    def test_empty_string_defaults_to_scheduled(self):
        assert _normalize_status("") == GameStatus.SCHEDULED


class TestNormalizeConference:
    def test_eastern_maps_correctly(self):
        assert _normalize_conference("Eastern") == Conference.EAST

    def test_western_maps_correctly(self):
        assert _normalize_conference("Western") == Conference.WEST

    def test_unknown_defaults_to_east(self):
        assert _normalize_conference("Unknown") == Conference.EAST

    def test_empty_string_defaults_to_east(self):
        assert _normalize_conference("") == Conference.EAST


class TestSportsdataDate:
    def test_formats_date_correctly(self):
        d = date(2025, 3, 20)
        assert _sportsdata_date(d) == "2025-MAR-20"

    def test_formats_january_correctly(self):
        d = date(2025, 1, 5)
        assert _sportsdata_date(d) == "2025-JAN-05"

    def test_formats_december_correctly(self):
        d = date(2025, 12, 25)
        assert _sportsdata_date(d) == "2025-DEC-25"


class TestNBADataClientNormalizers:
    def setup_method(self):
        # Create a client without a real API key for testing normalizers
        self.client = NBADataClient.__new__(NBADataClient)

    def test_normalize_team_extracts_fields(self):
        raw = {
            "TeamID": 100,
            "Name": "Lakers",
            "City": "Los Angeles",
            "Key": "LAL",
            "WikipediaLogoUrl": "https://example.com/logo.png",
            "Conference": "Western",
            "Division": "Pacific",
        }
        result = self.client._normalize_team(raw)
        assert result["external_id"] == 100
        assert result["name"] == "Lakers"
        assert result["short_name"] == "Los Angeles Lakers"
        assert result["abbreviation"] == "LAL"
        assert result["logo_url"] == "https://example.com/logo.png"
        assert result["conference"] == Conference.WEST
        assert result["division"] == "Pacific"

    def test_normalize_team_missing_logo_uses_empty_string(self):
        raw = {
            "TeamID": 100,
            "Name": "Lakers",
            "City": "Los Angeles",
            "Key": "LAL",
            "WikipediaLogoUrl": None,
            "Conference": "Western",
            "Division": "Pacific",
        }
        result = self.client._normalize_team(raw)
        assert result["logo_url"] == ""

    def test_normalize_game_with_datetime(self):
        raw = {
            "GameID": 1001,
            "HomeTeamID": 10,
            "AwayTeamID": 20,
            "HomeTeamScore": 110,
            "AwayTeamScore": 100,
            "Status": "Final",
            "DateTime": "2025-03-20T20:00:00",
            "Season": 2025,
            "SeasonType": 1,
        }
        result = self.client._normalize_game(raw)
        assert result["external_id"] == 1001
        assert result["home_team_external_id"] == 10
        assert result["away_team_external_id"] == 20
        assert result["home_score"] == 110
        assert result["away_score"] == 100
        assert result["status"] == GameStatus.FINAL
        assert result["game_date"] == "2025-03-20"
        assert result["tip_off"] is not None
        assert result["season"] == 2025
        assert result["postseason"] is False

    def test_normalize_game_postseason_flag(self):
        raw = {
            "GameID": 1002,
            "HomeTeamID": 10,
            "AwayTeamID": 20,
            "HomeTeamScore": None,
            "AwayTeamScore": None,
            "Status": "Scheduled",
            "DateTime": "2025-04-20T20:00:00",
            "Season": 2025,
            "SeasonType": 3,
        }
        result = self.client._normalize_game(raw)
        assert result["postseason"] is True

    def test_normalize_game_invalid_datetime(self):
        raw = {
            "GameID": 1003,
            "HomeTeamID": 10,
            "AwayTeamID": 20,
            "HomeTeamScore": None,
            "AwayTeamScore": None,
            "Status": "Scheduled",
            "DateTime": "not-a-date",
            "Season": 2025,
            "SeasonType": 1,
        }
        result = self.client._normalize_game(raw)
        assert result["tip_off"] is None

    def test_normalize_game_missing_datetime_uses_day(self):
        raw = {
            "GameID": 1004,
            "HomeTeamID": 10,
            "AwayTeamID": 20,
            "HomeTeamScore": None,
            "AwayTeamScore": None,
            "Status": "Scheduled",
            "Day": "2025-03-21T00:00:00",
            "Season": 2025,
            "SeasonType": 1,
        }
        result = self.client._normalize_game(raw)
        assert result["game_date"] == "2025-03-21"

    def test_normalize_standing_calculates_win_pct(self):
        raw = {
            "TeamID": 10,
            "Season": 2025,
            "Conference": "Eastern",
            "Wins": 40,
            "Losses": 20,
            "GamesBack": 2.5,
            "StreakDescription": "W3",
            "HomeWins": 25,
            "HomeLosses": 5,
            "AwayWins": 15,
            "AwayLosses": 15,
            "ConferenceRank": 2,
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
            "TeamID": 10,
            "Season": 2025,
            "Conference": "Eastern",
            "Wins": 0,
            "Losses": 0,
            "GamesBack": None,
            "StreakDescription": "",
            "HomeWins": 0,
            "HomeLosses": 0,
            "AwayWins": 0,
            "AwayLosses": 0,
            "ConferenceRank": 1,
        }
        result = self.client._normalize_standing(raw)
        assert result["win_pct"] == 0.0
        assert result["games_behind"] == 0.0


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
        home = TeamFactory(external_id=1001)
        away = TeamFactory(external_id=1002)
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
        game = GameFactory(external_id=6001, home_team=home, away_team=away, status=GameStatus.SCHEDULED)
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
        game = GameFactory(
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
