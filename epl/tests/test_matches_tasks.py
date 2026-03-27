"""Tests for matches/tasks.py — fetch_teams, fetch_fixtures, fetch_standings, fetch_live_scores."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.conf import settings
from django.utils import timezone

from epl.matches.models import Match, MatchStats
from epl.matches.tasks import (
    _broadcast_score_changes,
    _refresh_stale_matches,
    fetch_fixtures,
    fetch_live_scores,
    fetch_standings,
    fetch_teams,
    prefetch_upcoming_hype_data,
)

from .factories import MatchFactory

pytestmark = pytest.mark.django_db


class TestFetchTeams:
    @patch("epl.matches.tasks.sync_teams")
    def test_calls_sync_teams(self, mock_sync):
        mock_sync.return_value = (5, 3)
        fetch_teams()
        mock_sync.assert_called_once_with(settings.EPL_CURRENT_SEASON)

    @patch("epl.matches.tasks.sync_teams", side_effect=Exception("API down"))
    def test_retries_on_failure(self, mock_sync):
        with pytest.raises(Exception, match="API down"):
            fetch_teams()


class TestFetchFixtures:
    @patch("epl.matches.tasks.sync_matches")
    def test_calls_sync_matches(self, mock_sync):
        mock_sync.return_value = (10, 0)
        fetch_fixtures()
        mock_sync.assert_called_once_with(settings.EPL_CURRENT_SEASON)

    @patch("epl.matches.tasks.sync_matches", side_effect=Exception("fail"))
    def test_retries_on_failure(self, mock_sync):
        with pytest.raises(Exception, match="fail"):
            fetch_fixtures()


class TestFetchStandings:
    @patch("epl.matches.tasks.sync_standings")
    def test_calls_sync_standings(self, mock_sync):
        mock_sync.return_value = (20, 0)
        fetch_standings()
        mock_sync.assert_called_once_with(settings.EPL_CURRENT_SEASON)

    @patch("epl.matches.tasks.sync_standings", side_effect=Exception("fail"))
    def test_retries_on_failure(self, mock_sync):
        with pytest.raises(Exception, match="fail"):
            fetch_standings()


class TestFetchLiveScores:
    @patch("epl.matches.tasks._broadcast_score_changes")
    @patch("epl.matches.tasks._refresh_stale_matches", return_value=0)
    @patch("epl.matches.tasks.sync_matches")
    def test_syncs_and_broadcasts(self, mock_sync, mock_refresh, mock_broadcast):
        mock_sync.return_value = (0, 2)
        fetch_live_scores()
        mock_sync.assert_called_once()
        mock_broadcast.assert_called_once()

    @patch("epl.matches.tasks._broadcast_score_changes")
    @patch("epl.matches.tasks._refresh_stale_matches", return_value=0)
    @patch("epl.matches.tasks.sync_matches")
    def test_no_broadcast_when_nothing_changed(
        self, mock_sync, mock_refresh, mock_broadcast
    ):
        mock_sync.return_value = (0, 0)
        fetch_live_scores()
        mock_broadcast.assert_not_called()

    @patch("epl.matches.tasks.sync_matches", side_effect=Exception("fail"))
    def test_retries_on_failure(self, mock_sync):
        with pytest.raises(Exception, match="fail"):
            fetch_live_scores()


class TestRefreshStaleMatches:
    @patch("epl.matches.tasks.FootballDataClient")
    def test_updates_stale_match(self, mock_client_cls):
        match = MatchFactory(status=Match.Status.IN_PLAY, home_score=0, away_score=0)
        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get_match.return_value = {
            "status": Match.Status.IN_PLAY,
            "home_score": 1,
            "away_score": 0,
        }

        updated = _refresh_stale_matches([(match.pk, match.external_id)])
        assert updated == 1
        match.refresh_from_db()
        assert match.home_score == 1

    @patch("epl.matches.tasks.FootballDataClient")
    def test_handles_api_error_gracefully(self, mock_client_cls):
        match = MatchFactory(status=Match.Status.IN_PLAY)
        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.get_match.side_effect = Exception("API error")

        updated = _refresh_stale_matches([(match.pk, match.external_id)])
        assert updated == 0


class TestBroadcastScoreChanges:
    @patch("epl.matches.tasks.settle_match_bets")
    @patch("epl.matches.tasks.get_channel_layer")
    def test_broadcasts_on_score_change(self, mock_get_layer, mock_settle):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        match = MatchFactory(
            status=Match.Status.IN_PLAY,
            home_score=1,
            away_score=0,
            season=settings.EPL_CURRENT_SEASON,
        )
        pre_sync = {match.pk: (0, 0, "IN_PLAY")}

        _broadcast_score_changes(pre_sync)

        # Should have called group_send for live_scores and match channel
        assert mock_layer.group_send.call_count >= 1

    @patch("epl.matches.tasks.get_channel_layer")
    def test_no_broadcast_when_no_channel_layer(self, mock_get_layer):
        mock_get_layer.return_value = None
        pre_sync = {}
        # Should not raise
        _broadcast_score_changes(pre_sync)

    @patch("epl.matches.tasks.settle_match_bets")
    @patch("epl.matches.tasks.get_channel_layer")
    def test_triggers_settlement_on_finish(self, mock_get_layer, mock_settle):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        match = MatchFactory(
            status=Match.Status.FINISHED,
            home_score=2,
            away_score=1,
            season=settings.EPL_CURRENT_SEASON,
        )
        pre_sync = {match.pk: (2, 1, "IN_PLAY")}

        _broadcast_score_changes(pre_sync)
        mock_settle.delay.assert_called_once_with(match.pk)

    @patch("epl.matches.tasks.settle_match_bets")
    @patch("epl.matches.tasks.get_channel_layer")
    def test_no_settlement_when_already_finished(self, mock_get_layer, mock_settle):
        mock_layer = MagicMock()
        mock_layer.group_send = AsyncMock()
        mock_get_layer.return_value = mock_layer

        match = MatchFactory(
            status=Match.Status.FINISHED,
            home_score=2,
            away_score=1,
            season=settings.EPL_CURRENT_SEASON,
        )
        # Old state was already FINISHED
        pre_sync = {match.pk: (2, 1, "FINISHED")}

        _broadcast_score_changes(pre_sync)
        mock_settle.delay.assert_not_called()


class TestPrefetchUpcomingHypeData:
    @patch("epl.matches.tasks.fetch_match_hype_data")
    def test_refreshes_upcoming_matches(self, mock_fetch):
        now = timezone.now()
        MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=now + timedelta(hours=12),
            season=settings.EPL_CURRENT_SEASON,
        )

        prefetch_upcoming_hype_data()
        mock_fetch.assert_called_once()

    @patch("epl.matches.tasks.fetch_match_hype_data")
    def test_skips_matches_with_fresh_stats(self, mock_fetch):
        now = timezone.now()
        match = MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=now + timedelta(hours=12),
            season=settings.EPL_CURRENT_SEASON,
        )
        MatchStats.objects.create(match=match, fetched_at=now)

        prefetch_upcoming_hype_data()
        mock_fetch.assert_not_called()

    @patch("epl.matches.tasks.fetch_match_hype_data")
    def test_skips_far_future_matches(self, mock_fetch):
        now = timezone.now()
        MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=now + timedelta(days=5),
            season=settings.EPL_CURRENT_SEASON,
        )

        prefetch_upcoming_hype_data()
        mock_fetch.assert_not_called()
