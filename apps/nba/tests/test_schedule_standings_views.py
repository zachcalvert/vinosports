"""Tests for ScheduleView and StandingsView."""

from datetime import date, timedelta

import pytest
from django.test import Client
from django.utils import timezone
from games.models import Conference

from tests.factories import (
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


@pytest.mark.django_db
class TestScheduleView:
    def test_unauthenticated_redirected(self):
        response = Client().get("/games/schedule/")
        assert response.status_code in (301, 302)

    def test_returns_200(self, auth_client):
        response = auth_client.get("/games/schedule/")
        assert response.status_code == 200

    def test_uses_schedule_template(self, auth_client):
        response = auth_client.get("/games/schedule/")
        templates = [t.name for t in response.templates]
        assert "games/schedule.html" in templates

    def test_games_shown_for_today(self, auth_client):
        today = timezone.localdate()
        game = GameFactory(game_date=today)
        response = auth_client.get("/games/schedule/")
        assert game in response.context["games"]

    def test_games_filtered_by_date_param(self, auth_client):
        target = date(2026, 1, 15)
        game = GameFactory(game_date=target)
        other = GameFactory(game_date=target + timedelta(days=1))
        response = auth_client.get("/games/schedule/", {"date": "2026-01-15"})
        assert game in response.context["games"]
        assert other not in response.context["games"]

    def test_invalid_date_falls_back_to_today(self, auth_client):
        today = timezone.localdate()
        game = GameFactory(game_date=today)
        response = auth_client.get("/games/schedule/", {"date": "not-a-date"})
        assert response.context["target_date"] == today
        assert game in response.context["games"]

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
        response = auth_client.get("/games/schedule/", {"conference": "EAST"})
        game_ids = [g.pk for g in response.context["games"]]
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
        response = auth_client.get("/games/schedule/", {"conference": "WEST"})
        game_ids = [g.pk for g in response.context["games"]]
        assert west_game.pk in game_ids

    def test_invalid_conference_ignored(self, auth_client):
        today = timezone.localdate()
        game = GameFactory(game_date=today)
        response = auth_client.get("/games/schedule/", {"conference": "NORTH"})
        assert game in response.context["games"]

    def test_context_has_prev_and_next_dates(self, auth_client):
        today = timezone.localdate()
        response = auth_client.get("/games/schedule/")
        assert response.context["prev_date"] == today - timedelta(days=1)
        assert response.context["next_date"] == today + timedelta(days=1)

    def test_htmx_returns_partial(self, auth_client):
        response = auth_client.get("/games/schedule/", HTTP_HX_REQUEST="true")
        templates = [t.name for t in response.templates]
        assert "games/partials/game_list.html" in templates


# ---------------------------------------------------------------------------
# StandingsView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStandingsView:
    def test_unauthenticated_redirected(self):
        response = Client().get("/games/standings/")
        assert response.status_code in (301, 302)

    def test_returns_200(self, auth_client):
        response = auth_client.get("/games/standings/")
        assert response.status_code == 200

    def test_uses_standings_template(self, auth_client):
        response = auth_client.get("/games/standings/")
        templates = [t.name for t in response.templates]
        assert "games/standings.html" in templates

    def test_east_standings_in_context(self, auth_client):
        standing = StandingFactory(conference=Conference.EAST, season=2026)
        response = auth_client.get("/games/standings/")
        assert standing in response.context["east_standings"]

    def test_west_standings_in_context(self, auth_client):
        standing = StandingFactory(conference=Conference.WEST, season=2026)
        response = auth_client.get("/games/standings/")
        assert standing in response.context["west_standings"]

    def test_tab_defaults_to_east(self, auth_client):
        response = auth_client.get("/games/standings/")
        assert response.context["tab"] == "west"

    def test_tab_param_respected(self, auth_client):
        response = auth_client.get("/games/standings/", {"tab": "west"})
        assert response.context["tab"] == "west"

    def test_season_in_context(self, auth_client):
        response = auth_client.get("/games/standings/")
        assert response.context["season"] == 2026

    def test_htmx_returns_partial(self, auth_client):
        response = auth_client.get("/games/standings/", HTTP_HX_REQUEST="true")
        templates = [t.name for t in response.templates]
        assert "games/partials/standings_table.html" in templates
