"""Tests for news views and context processor."""

import pytest
from django.test import Client, RequestFactory

from news.context_processors import latest_articles

from .factories import DraftArticleFactory, NewsArticleFactory, UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def auth_client():
    user = UserFactory()
    c = Client()
    c.force_login(user)
    return c, user


@pytest.fixture
def superuser_client():
    user = UserFactory()
    user.is_superuser = True
    user.save()
    c = Client()
    c.force_login(user)
    return c, user


# ---------------------------------------------------------------------------
# ArticleListView
# ---------------------------------------------------------------------------


class TestArticleListView:
    def test_empty_list(self, client):
        resp = client.get("/news/")
        assert resp.status_code == 200
        assert len(resp.context["articles"]) == 0

    def test_lists_published_articles(self, client):
        NewsArticleFactory.create_batch(3)
        DraftArticleFactory()  # should not appear
        resp = client.get("/news/")
        assert resp.status_code == 200
        assert len(resp.context["articles"]) == 3

    def test_filters_by_league(self, client):
        NewsArticleFactory(league="nba")
        NewsArticleFactory(league="epl")
        resp = client.get("/news/?league=nba")
        assert len(resp.context["articles"]) == 1
        assert resp.context["articles"][0].league == "nba"

    def test_ignores_invalid_league_filter(self, client):
        NewsArticleFactory(league="nba")
        resp = client.get("/news/?league=invalid")
        # Invalid league param returns all articles (no filter applied)
        assert len(resp.context["articles"]) == 1

    def test_pagination(self, client):
        NewsArticleFactory.create_batch(15)
        resp = client.get("/news/")
        assert resp.context["is_paginated"] is True
        assert len(resp.context["articles"]) == 12  # paginate_by = 12

    def test_htmx_returns_partial(self, client):
        NewsArticleFactory()
        resp = client.get("/news/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        # HTMX requests get the feed partial, not the full page
        assert "news/partials/article_feed.html" in [t.name for t in resp.templates]

    def test_league_choices_in_context(self, client):
        resp = client.get("/news/")
        assert resp.context["league_choices"] == [
            ("epl", "EPL"),
            ("nba", "NBA"),
            ("nfl", "NFL"),
        ]


# ---------------------------------------------------------------------------
# ArticleDetailView
# ---------------------------------------------------------------------------


class TestArticleDetailView:
    def test_published_article(self, client):
        article = NewsArticleFactory(title="Big Win Recap")
        resp = client.get(f"/news/{article.id_hash}/")
        assert resp.status_code == 200
        assert resp.context["article"] == article

    def test_draft_404_for_anonymous(self, client):
        article = DraftArticleFactory()
        resp = client.get(f"/news/{article.id_hash}/")
        assert resp.status_code == 404

    def test_draft_404_for_regular_user(self, auth_client):
        c, _ = auth_client
        article = DraftArticleFactory()
        resp = c.get(f"/news/{article.id_hash}/")
        assert resp.status_code == 404

    def test_draft_visible_for_superuser(self, superuser_client):
        c, _ = superuser_client
        article = DraftArticleFactory(title="Draft Preview")
        resp = c.get(f"/news/{article.id_hash}/")
        assert resp.status_code == 200
        assert resp.context["article"] == article

    def test_nonexistent_article_404(self, client):
        resp = client.get("/news/ZZZZZZZZ/")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Context Processor
# ---------------------------------------------------------------------------


class TestLatestArticlesContextProcessor:
    def _make_request(self, league=None):
        factory = RequestFactory()
        request = factory.get("/")
        if league:
            request.league = league
        return request

    def test_returns_published_articles(self):
        NewsArticleFactory.create_batch(3)
        DraftArticleFactory()
        ctx = latest_articles(self._make_request())
        assert len(ctx["latest_articles"]) == 3

    def test_limits_to_four(self):
        NewsArticleFactory.create_batch(6)
        ctx = latest_articles(self._make_request())
        assert len(ctx["latest_articles"]) == 4

    def test_filters_by_league(self):
        NewsArticleFactory(league="nba")
        NewsArticleFactory(league="epl")
        ctx = latest_articles(self._make_request(league="nba"))
        assert len(ctx["latest_articles"]) == 1
        assert ctx["latest_articles"][0].league == "nba"

    def test_no_league_returns_all(self):
        NewsArticleFactory(league="nba")
        NewsArticleFactory(league="epl")
        ctx = latest_articles(self._make_request())
        assert len(ctx["latest_articles"]) == 2

    def test_empty_when_no_articles(self):
        ctx = latest_articles(self._make_request())
        assert len(ctx["latest_articles"]) == 0
