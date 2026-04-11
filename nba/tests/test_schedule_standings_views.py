"""Tests for ScheduleView and StandingsView."""

from datetime import date, timedelta

import pytest
from django.test import Client
from django.utils import timezone

from nba.games.models import Conference
from nba.tests.factories import (
    GameFactory,
    StandingFactory,
    TeamFactory,
    UserBalanceFactory,
    UserFactory,
)


@pytest.fixture
def auth_client(db):
    user = UserFactory()
    UserBalanceFactory(user=user)
    c = Client()
    c.force_login(user)
    return c


# ---------------------------------------------------------------------------
# ScheduleView
# ---------------------------------------------------------------------------


def _all_schedule_games(response):
    """Return all games from the schedule context (featured + remaining)."""
    games = list(response.context["games"])
    featured = response.context.get("featured_game")
    if featured:
        games.insert(0, featured)
    return games


@pytest.mark.django_db
class TestScheduleView:
    def test_anonymous_user_can_browse(self):
        response = Client().get("/nba/games/schedule/")
        assert response.status_code == 200

    def test_returns_200(self, auth_client):
        response = auth_client.get("/nba/games/schedule/")
        assert response.status_code == 200

    def test_uses_schedule_template(self, auth_client):
        response = auth_client.get("/nba/games/schedule/")
        templates = [t.name for t in response.templates]
        assert "games/schedule.html" in templates

    def test_games_shown_for_today(self, auth_client):
        today = timezone.localdate()
        game = GameFactory(game_date=today)
        response = auth_client.get("/nba/games/schedule/")
        all_games = _all_schedule_games(response)
        assert game in all_games

    def test_games_filtered_by_date_param(self, auth_client):
        target = date(2026, 1, 15)
        game = GameFactory(game_date=target)
        other = GameFactory(game_date=target + timedelta(days=1))
        response = auth_client.get("/nba/games/schedule/", {"date": "2026-01-15"})
        all_games = _all_schedule_games(response)
        assert game in all_games
        assert other not in all_games

    def test_invalid_date_falls_back_to_today(self, auth_client):
        today = timezone.localdate()
        game = GameFactory(game_date=today)
        response = auth_client.get("/nba/games/schedule/", {"date": "not-a-date"})
        assert response.context["target_date"] == today
        all_games = _all_schedule_games(response)
        assert game in all_games

    def test_out_of_range_date_returns_400(self, auth_client):
        response = auth_client.get("/nba/games/schedule/", {"date": "2055-10-22"})
        assert response.status_code == 400

    def test_far_past_date_returns_400(self, auth_client):
        response = auth_client.get("/nba/games/schedule/", {"date": "1996-10-07"})
        assert response.status_code == 400

    def test_conference_filter_east(self, auth_client):
        today = timezone.localdate()
        east_team = TeamFactory(conference=Conference.EAST)
        west_team = TeamFactory(conference=Conference.WEST)
        east_game = GameFactory(
            game_date=today,
            home_team=east_team,
            away_team=TeamFactory(conference=Conference.EAST),
        )
        west_game = GameFactory(
            game_date=today,
            home_team=west_team,
            away_team=TeamFactory(conference=Conference.WEST),
        )
        response = auth_client.get("/nba/games/schedule/", {"conference": "EAST"})
        all_games = _all_schedule_games(response)
        game_ids = [g.pk for g in all_games]
        assert east_game.pk in game_ids
        assert west_game.pk not in game_ids

    def test_conference_filter_west(self, auth_client):
        today = timezone.localdate()
        west_team = TeamFactory(conference=Conference.WEST)
        west_game = GameFactory(
            game_date=today,
            home_team=west_team,
            away_team=TeamFactory(conference=Conference.WEST),
        )
        response = auth_client.get("/nba/games/schedule/", {"conference": "WEST"})
        all_games = _all_schedule_games(response)
        game_ids = [g.pk for g in all_games]
        assert west_game.pk in game_ids

    def test_invalid_conference_ignored(self, auth_client):
        today = timezone.localdate()
        game = GameFactory(game_date=today)
        response = auth_client.get("/nba/games/schedule/", {"conference": "NORTH"})
        all_games = _all_schedule_games(response)
        assert game in all_games

    def test_context_has_week_dates(self, auth_client):
        response = auth_client.get("/nba/games/schedule/")
        assert "week_dates" in response.context
        assert len(response.context["week_dates"]) == 7

    def test_htmx_returns_partial(self, auth_client):
        response = auth_client.get("/nba/games/schedule/", HTTP_HX_REQUEST="true")
        templates = [t.name for t in response.templates]
        assert "games/partials/schedule_content.html" in templates


# ---------------------------------------------------------------------------
# StandingsView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStandingsView:
    def test_anonymous_user_can_browse(self):
        response = Client().get("/nba/games/standings/")
        assert response.status_code == 200

    def test_returns_200(self, auth_client):
        response = auth_client.get("/nba/games/standings/")
        assert response.status_code == 200

    def test_uses_standings_template(self, auth_client):
        response = auth_client.get("/nba/games/standings/")
        templates = [t.name for t in response.templates]
        assert "games/standings.html" in templates

    def test_east_standings_in_context(self, auth_client):
        standing = StandingFactory(conference=Conference.EAST, season=2025)
        response = auth_client.get("/nba/games/standings/")
        assert standing in response.context["east_standings"]

    def test_west_standings_in_context(self, auth_client):
        standing = StandingFactory(conference=Conference.WEST, season=2025)
        response = auth_client.get("/nba/games/standings/")
        assert standing in response.context["west_standings"]

    def test_tab_defaults_to_east(self, auth_client):
        response = auth_client.get("/nba/games/standings/")
        assert response.context["tab"] == "west"

    def test_tab_param_respected(self, auth_client):
        response = auth_client.get("/nba/games/standings/", {"tab": "west"})
        assert response.context["tab"] == "west"

    def test_season_in_context(self, auth_client):
        response = auth_client.get("/nba/games/standings/")
        assert response.context["season"] == 2025

    def test_htmx_returns_partial(self, auth_client):
        response = auth_client.get("/nba/games/standings/", HTTP_HX_REQUEST="true")
        templates = [t.name for t in response.templates]
        assert "games/partials/standings_table.html" in templates


@pytest.mark.django_db
class TestScheduleViewAdditional:
    def test_featured_game_is_first_when_all_final(self, auth_client):
        """When all games are FINAL, featured_game = first game in list."""
        from nba.games.models import GameStatus

        c = auth_client
        today = timezone.localdate()
        GameFactory(
            game_date=today, status=GameStatus.FINAL, home_score=110, away_score=100
        )
        response = c.get(f"/nba/games/schedule/?date={today.isoformat()}")
        assert response.status_code == 200
        featured = response.context.get("featured_game")
        assert featured is not None

    def test_odds_appear_in_context_when_game_has_odds(self, auth_client):
        """When a game has odds, they appear in the odds_by_game context."""
        from nba.tests.factories import OddsFactory

        c = auth_client
        today = timezone.localdate()
        game = GameFactory(game_date=today)
        OddsFactory(game=game)
        response = c.get(f"/nba/games/schedule/?date={today.isoformat()}")
        assert response.status_code == 200
        odds_by_game = response.context.get("odds_by_game", {})
        assert game.id in odds_by_game


@pytest.mark.django_db
class TestStandingsViewAdditional:
    def test_projected_matchup_shown_with_8_plus_standings(self, auth_client):
        """When 8+ standings exist, projected_matchup is populated."""
        from nba.games.tasks import _current_season

        c = auth_client
        season = _current_season()

        for i in range(9):
            team = TeamFactory(conference=Conference.WEST)
            StandingFactory(
                team=team,
                season=season,
                conference=Conference.WEST,
                conference_rank=i + 1,
            )

        response = c.get("/nba/games/standings/?tab=west")
        assert response.status_code == 200
        matchup = response.context.get("projected_matchup", {})
        assert "seed_1" in matchup
        assert "seed_8" in matchup
