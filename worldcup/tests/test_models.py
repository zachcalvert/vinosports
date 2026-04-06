"""Tests for worldcup Match model properties and behaviour."""

import pytest

from worldcup.matches.models import Match, Stage

from .factories import (
    FinishedMatchFactory,
    GroupFactory,
    MatchFactory,
    StageFactory,
    TeamFactory,
)

pytestmark = pytest.mark.django_db


class TestMatchIsKnockout:
    def test_group_stage_match_is_not_knockout(self):
        stage = StageFactory(stage_type=Stage.StageType.GROUP)
        match = MatchFactory(stage=stage)
        assert match.is_knockout is False

    def test_round_of_32_is_knockout(self):
        stage = StageFactory(stage_type=Stage.StageType.ROUND_OF_32)
        match = MatchFactory(stage=stage)
        assert match.is_knockout is True

    def test_final_is_knockout(self):
        stage = StageFactory(stage_type=Stage.StageType.FINAL)
        match = MatchFactory(stage=stage)
        assert match.is_knockout is True


class TestMatchWinner:
    def test_winner_is_none_when_not_finished(self):
        match = MatchFactory(status=Match.Status.SCHEDULED)
        assert match.winner is None

    def test_winner_is_none_when_in_play(self):
        match = MatchFactory(
            status=Match.Status.IN_PLAY,
            home_score=1,
            away_score=0,
        )
        assert match.winner is None

    def test_home_win_at_90_minutes(self):
        match = FinishedMatchFactory(home_score=2, away_score=1)
        assert match.winner == match.home_team

    def test_away_win_at_90_minutes(self):
        match = FinishedMatchFactory(home_score=0, away_score=3)
        assert match.winner == match.away_team

    def test_draw_at_90_minutes_returns_none(self):
        match = FinishedMatchFactory(home_score=1, away_score=1)
        assert match.winner is None

    def test_home_win_via_extra_time(self):
        match = FinishedMatchFactory(
            home_score=1,
            away_score=1,
            home_score_et=2,
            away_score_et=1,
        )
        assert match.winner == match.home_team

    def test_away_win_via_extra_time(self):
        match = FinishedMatchFactory(
            home_score=0,
            away_score=0,
            home_score_et=1,
            away_score_et=2,
        )
        assert match.winner == match.away_team

    def test_home_win_via_penalties(self):
        match = FinishedMatchFactory(
            home_score=1,
            away_score=1,
            home_score_et=1,
            away_score_et=1,
            home_score_penalties=5,
            away_score_penalties=3,
        )
        assert match.winner == match.home_team

    def test_away_win_via_penalties(self):
        match = FinishedMatchFactory(
            home_score=0,
            away_score=0,
            home_score_et=0,
            away_score_et=0,
            home_score_penalties=2,
            away_score_penalties=4,
        )
        assert match.winner == match.away_team

    def test_penalties_take_priority_over_et(self):
        """If penalties exist, ET scores are irrelevant for winner."""
        home = TeamFactory()
        away = TeamFactory()
        match = FinishedMatchFactory(
            home_team=home,
            away_team=away,
            home_score=1,
            away_score=1,
            home_score_et=2,  # home "won" ET
            away_score_et=1,
            home_score_penalties=3,
            away_score_penalties=5,  # but away won penalties
        )
        assert match.winner == away


class TestMatchSlug:
    def test_slug_generated_on_save(self):
        match = MatchFactory()
        assert match.slug != ""

    def test_slug_includes_team_tlas(self):
        home = TeamFactory(tla="BRA")
        away = TeamFactory(tla="ARG")
        match = MatchFactory(home_team=home, away_team=away)
        assert "bra" in match.slug
        assert "arg" in match.slug

    def test_slug_is_unique_for_same_teams_different_dates(self):
        from django.utils import timezone

        home = TeamFactory(tla="ENG")
        away = TeamFactory(tla="GER")
        m1 = MatchFactory(
            home_team=home,
            away_team=away,
            kickoff=timezone.now() + timezone.timedelta(days=1),
        )
        m2 = MatchFactory(
            home_team=home,
            away_team=away,
            kickoff=timezone.now() + timezone.timedelta(days=7),
        )
        assert m1.slug != m2.slug

    def test_get_absolute_url(self):
        match = MatchFactory()
        url = match.get_absolute_url()
        assert f"/worldcup/match/{match.slug}/" == url


class TestGroupModel:
    def test_group_str(self):
        group = GroupFactory(letter="A")
        assert "A" in str(group)

    def test_group_standings_queryset(self):
        from .factories import StandingFactory

        group = GroupFactory(letter="B")
        team1 = TeamFactory()
        team2 = TeamFactory()
        StandingFactory(group=group, team=team1, position=1)
        StandingFactory(group=group, team=team2, position=2)
        assert group.standings.count() == 2
