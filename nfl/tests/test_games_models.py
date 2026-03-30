"""Tests for nfl/games/models.py."""

import pytest

from nfl.games.models import GameStatus
from nfl.tests.factories import GameFactory, PlayerFactory, StandingFactory, TeamFactory


@pytest.mark.django_db
class TestTeam:
    def test_str(self):
        team = TeamFactory(name="Kansas City Chiefs")
        assert str(team) == "Kansas City Chiefs"

    # get_absolute_url tested in Phase 4 when URL routes are wired up


@pytest.mark.django_db
class TestGame:
    def test_str_includes_week(self):
        home = TeamFactory(abbreviation="KC")
        away = TeamFactory(abbreviation="BUF")
        game = GameFactory(home_team=home, away_team=away, week=3)
        assert "BUF @ KC" in str(game)
        assert "Wk 3" in str(game)

    def test_is_live_in_progress(self):
        game = GameFactory(status=GameStatus.IN_PROGRESS)
        assert game.is_live is True

    def test_is_live_halftime(self):
        game = GameFactory(status=GameStatus.HALFTIME)
        assert game.is_live is True

    def test_is_live_scheduled(self):
        game = GameFactory(status=GameStatus.SCHEDULED)
        assert game.is_live is False

    def test_is_final(self):
        game = GameFactory(status=GameStatus.FINAL, home_score=24, away_score=17)
        assert game.is_final is True

    def test_is_final_ot(self):
        game = GameFactory(status=GameStatus.FINAL_OT, home_score=31, away_score=28)
        assert game.is_final is True

    def test_winner_home(self):
        home = TeamFactory()
        away = TeamFactory()
        game = GameFactory(
            home_team=home,
            away_team=away,
            status=GameStatus.FINAL,
            home_score=24,
            away_score=17,
        )
        assert game.winner == home

    def test_winner_away(self):
        home = TeamFactory()
        away = TeamFactory()
        game = GameFactory(
            home_team=home,
            away_team=away,
            status=GameStatus.FINAL,
            home_score=17,
            away_score=24,
        )
        assert game.winner == away

    def test_winner_none_when_not_final(self):
        game = GameFactory(status=GameStatus.SCHEDULED)
        assert game.winner is None

    def test_is_tie(self):
        game = GameFactory(
            status=GameStatus.FINAL_OT,
            home_score=20,
            away_score=20,
        )
        assert game.is_tie is True
        assert game.winner is None

    def test_is_tie_false(self):
        game = GameFactory(
            status=GameStatus.FINAL,
            home_score=21,
            away_score=20,
        )
        assert game.is_tie is False


@pytest.mark.django_db
class TestStanding:
    def test_str(self):
        team = TeamFactory(abbreviation="KC")
        standing = StandingFactory(team=team, season=2025, wins=10, losses=7, ties=0)
        assert str(standing) == "KC 2025 (10-7-0)"

    def test_point_differential(self):
        standing = StandingFactory(points_for=350, points_against=300)
        assert standing.point_differential == 50


@pytest.mark.django_db
class TestPlayer:
    def test_str(self):
        player = PlayerFactory(first_name="Patrick", last_name="Mahomes")
        assert str(player) == "Patrick Mahomes"

    def test_full_name(self):
        player = PlayerFactory(first_name="Patrick", last_name="Mahomes")
        assert player.full_name == "Patrick Mahomes"

    def test_slug_includes_id_hash(self):
        player = PlayerFactory(first_name="Patrick", last_name="Mahomes")
        assert player.slug.startswith("patrick-mahomes-")
        assert player.id_hash in player.slug
