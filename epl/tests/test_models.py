"""Tests for EPL models — Match, Team, Standing, BetSlip."""

import pytest

from epl.betting.models import BetSlip
from vinosports.betting.models import BetStatus

from .factories import BetSlipFactory, MatchFactory, StandingFactory, TeamFactory

pytestmark = pytest.mark.django_db


class TestTeam:
    def test_str(self):
        team = TeamFactory(name="Arsenal")
        assert str(team) == "Arsenal"


class TestMatch:
    def test_slug_auto_generated(self):
        match = MatchFactory()
        assert match.slug
        assert len(match.slug) > 0

    def test_slug_contains_team_tlas(self):
        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="CHE")
        match = MatchFactory(home_team=home, away_team=away)
        assert "ars" in match.slug
        assert "che" in match.slug

    def test_str_without_score(self):
        home = TeamFactory(short_name="Arsenal")
        away = TeamFactory(short_name="Chelsea")
        match = MatchFactory(home_team=home, away_team=away, home_score=None)
        assert "Arsenal vs Chelsea" in str(match)

    def test_str_with_score(self):
        home = TeamFactory(short_name="Arsenal")
        away = TeamFactory(short_name="Chelsea")
        match = MatchFactory(home_team=home, away_team=away, home_score=2, away_score=1)
        result = str(match)
        assert "2-1" in result

    def test_get_absolute_url(self):
        match = MatchFactory()
        url = match.get_absolute_url()
        assert match.slug in url
        assert "/epl/" in url


class TestStanding:
    def test_str(self):
        team = TeamFactory(name="Liverpool")
        standing = StandingFactory(team=team, position=1, points=50)
        assert "1." in str(standing)
        assert "Liverpool" in str(standing)
        assert "50 pts" in str(standing)

    def test_unique_team_season(self):
        team = TeamFactory()
        StandingFactory(team=team, season="2025")
        with pytest.raises(Exception):
            StandingFactory(team=team, season="2025")


class TestBetSlip:
    def test_selection_choices(self):
        assert BetSlip.Selection.HOME_WIN == "HOME_WIN"
        assert BetSlip.Selection.DRAW == "DRAW"
        assert BetSlip.Selection.AWAY_WIN == "AWAY_WIN"

    def test_str(self):
        bet = BetSlipFactory()
        result = str(bet)
        assert "Home Win" in result

    def test_default_status_pending(self):
        bet = BetSlipFactory()
        assert bet.status == BetStatus.PENDING
