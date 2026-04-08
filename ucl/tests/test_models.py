"""Tests for UCL Match model properties and behaviour."""

import pytest

from ucl.matches.models import Match, Stage

from .factories import (
    FinishedMatchFactory,
    MatchFactory,
    StageFactory,
    StandingFactory,
    TeamFactory,
)

pytestmark = pytest.mark.django_db


class TestMatchIsKnockout:
    def test_league_phase_match_is_not_knockout(self):
        stage = StageFactory(stage_type=Stage.StageType.LEAGUE_PHASE)
        match = MatchFactory(stage=stage)
        assert match.is_knockout is False

    def test_knockout_playoff_is_knockout(self):
        stage = StageFactory(stage_type=Stage.StageType.KNOCKOUT_PLAYOFF)
        match = MatchFactory(stage=stage)
        assert match.is_knockout is True

    def test_round_of_16_is_knockout(self):
        stage = StageFactory(stage_type=Stage.StageType.ROUND_OF_16)
        match = MatchFactory(stage=stage)
        assert match.is_knockout is True

    def test_final_is_knockout(self):
        stage = StageFactory(stage_type=Stage.StageType.FINAL)
        match = MatchFactory(stage=stage)
        assert match.is_knockout is True


class TestMatchIsSecondLeg:
    def test_none_leg_is_not_second(self):
        match = MatchFactory(leg=None)
        assert match.is_second_leg is False

    def test_leg_1_is_not_second(self):
        match = MatchFactory(leg=1)
        assert match.is_second_leg is False

    def test_leg_2_is_second(self):
        match = MatchFactory(leg=2)
        assert match.is_second_leg is True


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
            home_score_et=2,
            away_score_et=1,
            home_score_penalties=3,
            away_score_penalties=5,
        )
        assert match.winner == away


class TestMatchSlug:
    def test_slug_generated_on_save(self):
        match = MatchFactory()
        assert match.slug != ""

    def test_slug_includes_team_tlas(self):
        home = TeamFactory(tla="LIV")
        away = TeamFactory(tla="BAR")
        match = MatchFactory(home_team=home, away_team=away)
        assert "liv" in match.slug
        assert "bar" in match.slug

    def test_slug_is_unique_for_same_teams_different_dates(self):
        from django.utils import timezone

        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="BAY")
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
        assert f"/ucl/match/{match.slug}/" == url


class TestStandingModel:
    def test_standing_str(self):
        team = TeamFactory(name="Arsenal")
        standing = StandingFactory(team=team, position=1, points=24)
        assert "Arsenal" in str(standing)
        assert "24" in str(standing)

    def test_unique_team_season_constraint(self):
        from django.db import IntegrityError

        team = TeamFactory()
        StandingFactory(team=team, season="2025")
        with pytest.raises(IntegrityError):
            StandingFactory(team=team, season="2025")
