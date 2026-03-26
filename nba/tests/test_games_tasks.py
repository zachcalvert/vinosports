"""Tests for games/tasks.py (Celery tasks and _current_season helper)."""

from datetime import date
from unittest.mock import patch

import pytest

from nba.games.tasks import (
    _current_season,
    fetch_live_scores,
    fetch_players,
    fetch_schedule,
    fetch_standings,
    fetch_teams,
)

# ---------------------------------------------------------------------------
# _current_season (BDL uses start year: 2025-26 season = 2025)
# ---------------------------------------------------------------------------


class TestCurrentSeason:
    @patch("nba.games.tasks.timezone")
    def test_oct_returns_current_year(self, mock_tz):
        mock_tz.now.return_value.date.return_value = date(2025, 10, 15)
        assert _current_season() == 2025

    @patch("nba.games.tasks.timezone")
    def test_nov_returns_current_year(self, mock_tz):
        mock_tz.now.return_value.date.return_value = date(2025, 11, 1)
        assert _current_season() == 2025

    @patch("nba.games.tasks.timezone")
    def test_dec_returns_current_year(self, mock_tz):
        mock_tz.now.return_value.date.return_value = date(2025, 12, 31)
        assert _current_season() == 2025

    @patch("nba.games.tasks.timezone")
    def test_jan_returns_previous_year(self, mock_tz):
        mock_tz.now.return_value.date.return_value = date(2026, 1, 15)
        assert _current_season() == 2025

    @patch("nba.games.tasks.timezone")
    def test_june_returns_previous_year(self, mock_tz):
        mock_tz.now.return_value.date.return_value = date(2026, 6, 1)
        assert _current_season() == 2025

    @patch("nba.games.tasks.timezone")
    def test_sep_returns_previous_year(self, mock_tz):
        mock_tz.now.return_value.date.return_value = date(2026, 9, 30)
        assert _current_season() == 2025


# ---------------------------------------------------------------------------
# fetch_teams
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFetchTeams:
    @patch("nba.games.tasks.sync_teams", return_value=30)
    def test_success_returns_count(self, mock_sync):
        result = fetch_teams()
        assert result == {"synced": 30}
        mock_sync.assert_called_once()

    @patch("nba.games.tasks.sync_teams", side_effect=Exception("API down"))
    def test_retries_on_failure(self, mock_sync):
        with pytest.raises(Exception, match="API down"):
            fetch_teams()


# ---------------------------------------------------------------------------
# fetch_players
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFetchPlayers:
    @patch("nba.games.tasks.sync_players", return_value=500)
    def test_fetch_players_calls_sync(self, mock_sync):
        result = fetch_players()
        assert result == {"synced": 500}
        mock_sync.assert_called_once()

    @patch("nba.games.tasks.sync_players", side_effect=Exception("API down"))
    def test_fetch_players_retries_on_error(self, mock_sync):
        with pytest.raises(Exception, match="API down"):
            fetch_players()


# ---------------------------------------------------------------------------
# fetch_schedule
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFetchSchedule:
    @patch("nba.games.tasks.sync_games", return_value=82)
    def test_success_with_explicit_season(self, mock_sync):
        result = fetch_schedule(season=2025)
        assert result == {"synced": 82, "season": 2025}
        mock_sync.assert_called_once_with(2025)

    @patch("nba.games.tasks.sync_games", return_value=82)
    @patch("nba.games.tasks._current_season", return_value=2025)
    def test_defaults_to_current_season(self, mock_season, mock_sync):
        result = fetch_schedule()
        assert result == {"synced": 82, "season": 2025}
        mock_sync.assert_called_once_with(2025)

    @patch("nba.games.tasks.sync_games", side_effect=Exception("timeout"))
    def test_retries_on_failure(self, mock_sync):
        with pytest.raises(Exception, match="timeout"):
            fetch_schedule(season=2025)


# ---------------------------------------------------------------------------
# fetch_standings
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFetchStandings:
    @patch("nba.games.tasks.sync_standings", return_value=30)
    def test_success_with_explicit_season(self, mock_sync):
        result = fetch_standings(season=2025)
        assert result == {"synced": 30, "season": 2025}
        mock_sync.assert_called_once_with(2025)

    @patch("nba.games.tasks.sync_standings", return_value=30)
    @patch("nba.games.tasks._current_season", return_value=2025)
    def test_defaults_to_current_season(self, mock_season, mock_sync):
        result = fetch_standings()
        assert result == {"synced": 30, "season": 2025}

    @patch("nba.games.tasks.sync_standings", side_effect=Exception("fail"))
    def test_retries_on_failure(self, mock_sync):
        with pytest.raises(Exception, match="fail"):
            fetch_standings(season=2025)


# ---------------------------------------------------------------------------
# fetch_live_scores
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFetchLiveScores:
    @patch("nba.games.tasks.sync_live_scores", return_value=5)
    def test_success_returns_count(self, mock_sync):
        result = fetch_live_scores()
        assert result == {"updated": 5}
        mock_sync.assert_called_once()

    @patch("nba.games.tasks.sync_live_scores", side_effect=Exception("error"))
    def test_retries_on_failure(self, mock_sync):
        with pytest.raises(Exception, match="error"):
            fetch_live_scores()
