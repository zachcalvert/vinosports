"""Additional tests for nba/games/services.py — covers previously untested paths."""

from datetime import date
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from nba.games.models import Conference, Game, GameStatus, Player, PlayerBoxScore
from nba.games.services import (
    NBADataClient,
    _compute_standings_from_games,
    refresh_active_players,
    sync_box_score,
)
from nba.tests.factories import GameFactory, PlayerFactory, TeamFactory


# ---------------------------------------------------------------------------
# NBADataClient normalizers
# ---------------------------------------------------------------------------


class TestNormalizePlayerStat:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_extracts_player_and_team_external_ids(self):
        raw = {
            "player": {"id": 999, "first_name": "John", "last_name": "Doe"},
            "team": {"id": 1610612737},
            "min": "32:15",
            "pts": 22,
            "fgm": 8,
            "fga": 15,
            "fg3m": 2,
            "fg3a": 5,
            "ftm": 4,
            "fta": 4,
            "oreb": 1,
            "dreb": 5,
            "reb": 6,
            "ast": 4,
            "stl": 1,
            "blk": 0,
            "turnover": 2,
            "pf": 3,
            "plus_minus": 8,
        }
        result = self.client._normalize_player_stat(raw)
        assert result["player_external_id"] == 999
        assert result["team_external_id"] == 1610612737
        assert result["player_name"] == "John Doe"
        assert result["minutes"] == "32:15"
        assert result["points"] == 22

    def test_handles_missing_player_team(self):
        raw = {"min": "0:00", "pts": 0}
        result = self.client._normalize_player_stat(raw)
        assert result["player_external_id"] is None
        assert result["team_external_id"] is None

    def test_handles_none_stats_defaulting_to_zero(self):
        raw = {
            "player": {"id": 1},
            "team": {"id": 2},
            "min": None,
            "pts": None,
            "fgm": None,
        }
        result = self.client._normalize_player_stat(raw)
        assert result["minutes"] == ""
        assert result["points"] == 0
        assert result["fgm"] == 0


# ---------------------------------------------------------------------------
# NBADataClient._get_all pagination
# ---------------------------------------------------------------------------


class TestGetAllPagination:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_follows_cursor_to_next_page(self):
        page1 = {"data": [{"id": 1}], "meta": {"next_cursor": 42}}
        page2 = {"data": [{"id": 2}], "meta": {"next_cursor": None}}

        call_count = 0

        def fake_get_with_retry(path, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return page1
            return page2

        self.client._get_with_retry = fake_get_with_retry
        results = self.client._get_all("/teams")
        assert results == [{"id": 1}, {"id": 2}]
        assert call_count == 2

    def test_stops_when_no_cursor(self):
        self.client._get_with_retry = MagicMock(
            return_value={"data": [{"id": 1}], "meta": {"next_cursor": None}}
        )
        results = self.client._get_all("/teams")
        assert len(results) == 1
        self.client._get_with_retry.assert_called_once()


# ---------------------------------------------------------------------------
# NBADataClient._get_with_retry
# ---------------------------------------------------------------------------


class TestGetWithRetry:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_retries_on_429_then_succeeds(self):
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        exc_429 = httpx.HTTPStatusError(
            "rate limited", request=MagicMock(), response=mock_response_429
        )

        call_count = 0

        def fake_get(path, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise exc_429
            return {"data": []}

        self.client._get = fake_get

        with patch("nba.games.services.time.sleep") as mock_sleep:
            result = self.client._get_with_retry("/test", max_retries=2)

        assert result == {"data": []}
        assert call_count == 2
        mock_sleep.assert_called_once_with(1)

    def test_raises_non_429_error_immediately(self):
        mock_response_404 = MagicMock()
        mock_response_404.status_code = 404
        exc_404 = httpx.HTTPStatusError(
            "not found", request=MagicMock(), response=mock_response_404
        )
        self.client._get = MagicMock(side_effect=exc_404)

        with pytest.raises(httpx.HTTPStatusError):
            self.client._get_with_retry("/test", max_retries=3)

        # Should only be called once (no retry for 404)
        assert self.client._get.call_count == 1

    def test_raises_after_max_retries_exhausted(self):
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        exc_429 = httpx.HTTPStatusError(
            "rate limited", request=MagicMock(), response=mock_response_429
        )
        self.client._get = MagicMock(side_effect=exc_429)

        with patch("nba.games.services.time.sleep"):
            with pytest.raises(httpx.HTTPStatusError):
                self.client._get_with_retry("/test", max_retries=2)

        assert self.client._get.call_count == 3  # initial + 2 retries


# ---------------------------------------------------------------------------
# NBADataClient.get_games
# ---------------------------------------------------------------------------


class TestGetGames:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_uses_date_param_when_provided(self):
        self.client._normalize_game = MagicMock(side_effect=lambda x: x)
        self.client._get_all = MagicMock(return_value=[])
        target_date = date(2026, 3, 15)
        self.client.get_games(2026, game_date=target_date)
        call_params = self.client._get_all.call_args[1].get(
            "params"
        ) or self.client._get_all.call_args[0][1]
        assert call_params.get("dates[]") == "2026-03-15"
        assert "seasons[]" not in call_params

    def test_uses_season_param_when_no_date(self):
        self.client._normalize_game = MagicMock(side_effect=lambda x: x)
        self.client._get_all = MagicMock(return_value=[])
        self.client.get_games(2026)
        call_params = self.client._get_all.call_args[1].get(
            "params"
        ) or self.client._get_all.call_args[0][1]
        assert call_params.get("seasons[]") == 2026
        assert "dates[]" not in call_params


# ---------------------------------------------------------------------------
# NBADataClient.get_standings
# ---------------------------------------------------------------------------


class TestGetStandings:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_handles_dict_response_with_data_key(self):
        self.client._get = MagicMock(return_value={"data": [{"season": 2026}]})
        self.client._normalize_standing = MagicMock(side_effect=lambda x: x)
        result = self.client.get_standings(2026)
        assert len(result) == 1

    def test_handles_list_response_directly(self):
        self.client._get = MagicMock(return_value=[{"season": 2026}])
        self.client._normalize_standing = MagicMock(side_effect=lambda x: x)
        result = self.client.get_standings(2026)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# NBADataClient.get_players
# ---------------------------------------------------------------------------


class TestGetPlayers:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_calls_on_page_callback_after_each_page(self):
        self.client._get_with_retry = MagicMock(
            return_value={"data": [{"id": 1}], "meta": {"next_cursor": None}}
        )
        self.client._normalize_player = MagicMock(side_effect=lambda x: x)
        page_counts = []
        self.client.get_players(on_page=lambda n: page_counts.append(n))
        assert page_counts == [1]

    def test_page_delay_causes_sleep(self):
        self.client._get_with_retry = MagicMock(
            side_effect=[
                {"data": [{"id": 1}], "meta": {"next_cursor": 42}},
                {"data": [{"id": 2}], "meta": {"next_cursor": None}},
            ]
        )
        self.client._normalize_player = MagicMock(side_effect=lambda x: x)
        with patch("nba.games.services.time.sleep") as mock_sleep:
            self.client.get_players(page_delay=0.5)
        mock_sleep.assert_called_once_with(0.5)


# ---------------------------------------------------------------------------
# NBADataClient.get_game_stats
# ---------------------------------------------------------------------------


class TestGetGameStats:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_calls_stats_endpoint_with_game_id(self):
        self.client._get_all = MagicMock(return_value=[])
        self.client._normalize_player_stat = MagicMock(side_effect=lambda x: x)
        self.client.get_game_stats(12345)
        self.client._get_all.assert_called_once_with(
            "/stats", params={"game_ids[]": 12345}
        )

    def test_returns_normalized_stats(self):
        raw = [{"player": {"id": 1}, "team": {"id": 2}, "pts": 10}]
        self.client._get_all = MagicMock(return_value=raw)
        self.client._normalize_player_stat = MagicMock(side_effect=lambda x: x)
        result = self.client.get_game_stats(99)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# NBADataClient.get_live_scores
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGetLiveScores:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_returns_empty_when_no_live_or_scheduled_games(self):
        result = self.client.get_live_scores()
        assert result == []

    def test_fetches_when_live_game_exists(self):
        from django.utils import timezone

        GameFactory(
            game_date=timezone.localdate(),
            status=GameStatus.IN_PROGRESS,
        )
        self.client._get_all = MagicMock(return_value=[])
        self.client._normalize_game = MagicMock(side_effect=lambda x: x)
        result = self.client.get_live_scores()
        assert result == []
        self.client._get_all.assert_called_once()

    def test_fetches_when_only_scheduled_games_today(self):
        from django.utils import timezone

        GameFactory(
            game_date=timezone.localdate(),
            status=GameStatus.SCHEDULED,
        )
        self.client._get_all = MagicMock(return_value=[])
        self.client._normalize_game = MagicMock(side_effect=lambda x: x)
        result = self.client.get_live_scores()
        assert result == []
        self.client._get_all.assert_called_once()


# ---------------------------------------------------------------------------
# refresh_active_players
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRefreshActivePlayers:
    def test_activates_players_with_box_scores(self):
        from nba.games.models import GameStatus, PlayerBoxScore

        team = TeamFactory()
        game = GameFactory(season=2026, status=GameStatus.FINAL, home_team=team)
        player = PlayerFactory(team=team, is_active=False)
        PlayerBoxScore.objects.create(
            game=game,
            team=team,
            player_external_id=player.external_id,
            player_name=f"{player.first_name} {player.last_name}",
        )

        count = refresh_active_players(season=2026)

        player.refresh_from_db()
        assert player.is_active is True
        assert count == 1

    def test_deactivates_players_without_box_scores(self):
        team = TeamFactory()
        active_player = PlayerFactory(team=team, is_active=True)

        count = refresh_active_players(season=2026)

        active_player.refresh_from_db()
        assert active_player.is_active is False
        assert count == 0

    def test_uses_current_season_when_none_passed(self):
        with patch("nba.games.services.PlayerBoxScore") as mock_pbs:
            mock_pbs.objects.filter.return_value.values_list.return_value.distinct.return_value = (
                []
            )
            with patch("nba.games.services.Player") as mock_player:
                mock_player.objects.filter.return_value.exclude.return_value.update.return_value = (
                    0
                )
                mock_player.objects.filter.return_value.update.return_value = 0
                with patch("nba.games.tasks._current_season", return_value=2026):
                    refresh_active_players(season=None)


# ---------------------------------------------------------------------------
# _compute_standings_from_games (away team wins path)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestComputeStandingsFromGamesAwayWins:
    def test_credits_away_team_when_away_wins(self):
        home_team = TeamFactory(conference=Conference.EAST)
        away_team = TeamFactory(conference=Conference.EAST)
        GameFactory(
            season=2026,
            status=GameStatus.FINAL,
            home_team=home_team,
            away_team=away_team,
            home_score=100,
            away_score=110,
        )

        count = _compute_standings_from_games(season=2026)

        from nba.games.models import Standing

        home_standing = Standing.objects.get(team=home_team, season=2026)
        away_standing = Standing.objects.get(team=away_team, season=2026)

        assert home_standing.wins == 0
        assert home_standing.losses == 1
        assert away_standing.wins == 1
        assert away_standing.losses == 0
        assert count == 2


# ---------------------------------------------------------------------------
# sync_box_score
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSyncBoxScore:
    def _make_mock_client(self, stats):
        mock = MagicMock()
        mock.__enter__ = MagicMock(return_value=mock)
        mock.__exit__ = MagicMock(return_value=False)
        mock.get_game_stats.return_value = stats
        return mock

    def test_returns_zero_when_no_stats(self):
        game = GameFactory()
        mock_client = self._make_mock_client([])
        count = sync_box_score(game, client=mock_client)
        assert count == 0

    def test_creates_box_score_records(self):
        team = TeamFactory()
        game = GameFactory(home_team=team)

        stats = [
            {
                "player_external_id": 1001,
                "player_name": "Alice Smith",
                "player_position": "G",
                "team_external_id": team.external_id,
                "minutes": "35:00",
                "points": 25,
                "fgm": 9,
                "fga": 18,
                "fg3m": 3,
                "fg3a": 7,
                "ftm": 4,
                "fta": 5,
                "oreb": 1,
                "dreb": 4,
                "reb": 5,
                "ast": 6,
                "stl": 2,
                "blk": 1,
                "turnovers": 3,
                "pf": 2,
                "plus_minus": 10,
            }
        ]
        mock_client = self._make_mock_client(stats)
        count = sync_box_score(game, client=mock_client)

        assert count == 1
        box = PlayerBoxScore.objects.get(game=game, player_external_id=1001)
        assert box.points == 25
        assert box.team == team

    def test_top5_by_minutes_marked_as_starters(self):
        team = TeamFactory()
        game = GameFactory(home_team=team)

        stats = [
            {
                "player_external_id": 1000 + i,
                "player_name": f"Player {i}",
                "player_position": "G",
                "team_external_id": team.external_id,
                "minutes": f"{30 - i}:00",
                "points": 10,
                "fgm": 4,
                "fga": 8,
                "fg3m": 1,
                "fg3a": 3,
                "ftm": 1,
                "fta": 2,
                "oreb": 0,
                "dreb": 3,
                "reb": 3,
                "ast": 2,
                "stl": 1,
                "blk": 0,
                "turnovers": 1,
                "pf": 2,
                "plus_minus": 5,
            }
            for i in range(7)
        ]
        mock_client = self._make_mock_client(stats)
        sync_box_score(game, client=mock_client)

        starters = PlayerBoxScore.objects.filter(game=game, starter=True)
        benchers = PlayerBoxScore.objects.filter(game=game, starter=False)
        assert starters.count() == 5
        assert benchers.count() == 2

    def test_resolves_player_fk_when_player_exists(self):
        team = TeamFactory()
        game = GameFactory(home_team=team)
        player = PlayerFactory(team=team, is_active=False)

        stats = [
            {
                "player_external_id": player.external_id,
                "player_name": f"{player.first_name} {player.last_name}",
                "player_position": "G",
                "team_external_id": team.external_id,
                "minutes": "28:00",
                "points": 15,
                "fgm": 5,
                "fga": 10,
                "fg3m": 2,
                "fg3a": 4,
                "ftm": 3,
                "fta": 4,
                "oreb": 1,
                "dreb": 3,
                "reb": 4,
                "ast": 3,
                "stl": 1,
                "blk": 0,
                "turnovers": 2,
                "pf": 2,
                "plus_minus": 3,
            }
        ]
        mock_client = self._make_mock_client(stats)
        sync_box_score(game, client=mock_client)

        box = PlayerBoxScore.objects.get(game=game, player_external_id=player.external_id)
        assert box.player == player
        player.refresh_from_db()
        assert player.is_active is True

    def test_skips_stats_with_unknown_team(self):
        team = TeamFactory()
        game = GameFactory(home_team=team)

        stats = [
            {
                "player_external_id": 9999,
                "player_name": "Unknown Player",
                "player_position": "F",
                "team_external_id": 99999999,  # Does not exist in DB
                "minutes": "20:00",
                "points": 5,
                "fgm": 2,
                "fga": 5,
                "fg3m": 0,
                "fg3a": 2,
                "ftm": 1,
                "fta": 1,
                "oreb": 0,
                "dreb": 2,
                "reb": 2,
                "ast": 1,
                "stl": 0,
                "blk": 0,
                "turnovers": 1,
                "pf": 1,
                "plus_minus": -4,
            }
        ]
        mock_client = self._make_mock_client(stats)
        count = sync_box_score(game, client=mock_client)
        assert count == 0


# ---------------------------------------------------------------------------
# NBADataClient._get
# ---------------------------------------------------------------------------


class TestNBADataClientGet:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_calls_inner_client_get(self):
        mock_http = MagicMock()
        self.client._client = mock_http
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_http.get.return_value = mock_response

        result = self.client._get("/teams")

        mock_http.get.assert_called_once_with("/teams", params=None)
        mock_response.raise_for_status.assert_called_once()
        assert result == {"data": []}

    def test_returns_json_response(self):
        mock_http = MagicMock()
        self.client._client = mock_http
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [{"id": 1}]
        mock_http.get.return_value = mock_response

        result = self.client._get("/standings", params={"season": 2026})

        assert result == [{"id": 1}]


# ---------------------------------------------------------------------------
# NBADataClient.get_teams
# ---------------------------------------------------------------------------


class TestGetTeams:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_calls_get_all_and_normalizes(self):
        raw_team = {
            "id": 14,
            "name": "Lakers",
            "full_name": "Los Angeles Lakers",
            "city": "Los Angeles",
            "abbreviation": "LAL",
            "conference": "West",
            "division": "Pacific",
        }
        self.client._get_all = MagicMock(return_value=[raw_team])
        result = self.client.get_teams()
        assert len(result) == 1
        assert result[0]["external_id"] == 14
        self.client._get_all.assert_called_once_with("/teams")


# ---------------------------------------------------------------------------
# NBADataClient._normalize_game with invalid datetime
# ---------------------------------------------------------------------------


class TestNormalizeGameValueError:
    def setup_method(self):
        self.client = NBADataClient.__new__(NBADataClient)

    def test_handles_invalid_iso_datetime(self):
        raw = {
            "id": 100,
            "home_team": {"id": 1},
            "visitor_team": {"id": 2},
            "home_team_score": 110,
            "visitor_team_score": 105,
            "status": "Final",
            "datetime": "INVALID_T_DATE_FORMAT",
            "date": "2026-03-15",
            "season": 2026,
            "postseason": False,
        }
        result = self.client._normalize_game(raw)
        # Should not raise, just skip the tip_off parsing
        assert result["external_id"] == 100
        assert result["tip_off"] is None


# ---------------------------------------------------------------------------
# sync_box_score with malformed minutes (covers _minutes_sort_key edge cases)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSyncBoxScoreEdgeCases:
    def _make_mock_client(self, stats):
        mock = MagicMock()
        mock.__enter__ = MagicMock(return_value=mock)
        mock.__exit__ = MagicMock(return_value=False)
        mock.get_game_stats.return_value = stats
        return mock

    def test_handles_malformed_minutes_string(self):
        """_minutes_sort_key: 'XX:YY' where parts aren't integers."""
        team = TeamFactory()
        game = GameFactory(home_team=team)

        stats = [
            {
                "player_external_id": 2001,
                "player_name": "Bad Minutes",
                "player_position": "G",
                "team_external_id": team.external_id,
                "minutes": "XX:YY",
                "points": 5,
                "fgm": 2,
                "fga": 4,
                "fg3m": 0,
                "fg3a": 1,
                "ftm": 1,
                "fta": 1,
                "oreb": 0,
                "dreb": 1,
                "reb": 1,
                "ast": 1,
                "stl": 0,
                "blk": 0,
                "turnovers": 1,
                "pf": 1,
                "plus_minus": -2,
            }
        ]
        mock_client = self._make_mock_client(stats)
        count = sync_box_score(game, client=mock_client)
        assert count == 1

    def test_handles_float_minutes_string(self):
        """_minutes_sort_key: minutes without ':' as float string."""
        team = TeamFactory()
        game = GameFactory(home_team=team)

        stats = [
            {
                "player_external_id": 2002,
                "player_name": "Float Minutes",
                "player_position": "F",
                "team_external_id": team.external_id,
                "minutes": "28.5",
                "points": 12,
                "fgm": 5,
                "fga": 10,
                "fg3m": 1,
                "fg3a": 3,
                "ftm": 1,
                "fta": 2,
                "oreb": 1,
                "dreb": 3,
                "reb": 4,
                "ast": 2,
                "stl": 1,
                "blk": 0,
                "turnovers": 2,
                "pf": 2,
                "plus_minus": 4,
            }
        ]
        mock_client = self._make_mock_client(stats)
        count = sync_box_score(game, client=mock_client)
        assert count == 1

    def test_handles_non_numeric_float_minutes(self):
        """_minutes_sort_key: minutes without ':' that aren't numeric."""
        team = TeamFactory()
        game = GameFactory(home_team=team)

        stats = [
            {
                "player_external_id": 2003,
                "player_name": "Non Numeric",
                "player_position": "C",
                "team_external_id": team.external_id,
                "minutes": "DNP",
                "points": 0,
                "fgm": 0,
                "fga": 0,
                "fg3m": 0,
                "fg3a": 0,
                "ftm": 0,
                "fta": 0,
                "oreb": 0,
                "dreb": 0,
                "reb": 0,
                "ast": 0,
                "stl": 0,
                "blk": 0,
                "turnovers": 0,
                "pf": 0,
                "plus_minus": 0,
            }
        ]
        mock_client = self._make_mock_client(stats)
        count = sync_box_score(game, client=mock_client)
        assert count == 1


# ---------------------------------------------------------------------------
# _broadcast_score_updates
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBroadcastScoreUpdates:
    def test_creates_activity_event_for_score_change(self):
        from nba.activity.models import ActivityEvent
        from nba.games.services import _broadcast_score_updates

        game = GameFactory(home_score=110, away_score=100, status=GameStatus.FINAL)

        mock_send = MagicMock()
        mock_channel_layer = MagicMock()

        with (
            patch("channels.layers.get_channel_layer", return_value=mock_channel_layer),
            patch("asgiref.sync.async_to_sync", return_value=mock_send),
            patch("nba.games.services.sync_box_score"),
        ):
            _broadcast_score_updates([game.pk])

        assert ActivityEvent.objects.filter(
            event_type=ActivityEvent.EventType.SCORE_CHANGE
        ).exists()

    def test_skips_missing_game_pk(self):
        from nba.activity.models import ActivityEvent
        from nba.games.services import _broadcast_score_updates

        mock_send = MagicMock()
        mock_channel_layer = MagicMock()

        with (
            patch("channels.layers.get_channel_layer", return_value=mock_channel_layer),
            patch("asgiref.sync.async_to_sync", return_value=mock_send),
        ):
            _broadcast_score_updates([999999])

        assert not ActivityEvent.objects.filter(
            event_type=ActivityEvent.EventType.SCORE_CHANGE
        ).exists()

    def test_handles_sync_box_score_exception(self):
        from nba.activity.models import ActivityEvent
        from nba.games.services import _broadcast_score_updates

        game = GameFactory(home_score=95, away_score=88, status=GameStatus.FINAL)

        mock_send = MagicMock()
        mock_channel_layer = MagicMock()

        with (
            patch("channels.layers.get_channel_layer", return_value=mock_channel_layer),
            patch("asgiref.sync.async_to_sync", return_value=mock_send),
            patch("nba.games.services.sync_box_score", side_effect=Exception("API error")),
        ):
            _broadcast_score_updates([game.pk])

        # Should still create activity event even if box score sync fails
        assert ActivityEvent.objects.filter(
            event_type=ActivityEvent.EventType.SCORE_CHANGE
        ).exists()
