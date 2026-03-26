"""Tests for EPL views — dashboard, odds board, match detail."""

import pytest
from django.test import Client

from .factories import (
    MatchFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def authed_client():
    user = UserFactory(password="testpass123")
    c = Client()
    c.login(email=user.email, password="testpass123")
    return c, user


class TestDashboardView:
    def test_renders_publicly(self, client):
        resp = client.get("/epl/")
        assert resp.status_code == 200


class TestOddsBoard:
    def test_renders_publicly(self, client):
        resp = client.get("/epl/odds/")
        assert resp.status_code == 200


class TestMatchDetailView:
    def test_renders_match(self, client):
        match = MatchFactory()
        resp = client.get(f"/epl/match/{match.slug}/")
        assert resp.status_code == 200

    def test_404_for_invalid_slug(self, client):
        resp = client.get("/epl/match/nonexistent-match/")
        assert resp.status_code == 404


class TestLeaderboardView:
    def test_renders(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/leaderboard/")
        assert resp.status_code == 200

    def test_board_type_filter(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/leaderboard/?type=profit")
        assert resp.status_code == 200


class TestLeagueTableView:
    def test_renders(self, authed_client):
        c, user = authed_client
        resp = c.get("/epl/table/")
        assert resp.status_code == 200
