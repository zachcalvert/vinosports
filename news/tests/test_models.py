"""Tests for NewsArticle model."""

import pytest
from django.db import IntegrityError
from django.utils import timezone

from news.models import NewsArticle

from .factories import DraftArticleFactory, NewsArticleFactory

pytestmark = pytest.mark.django_db


class TestNewsArticleModel:
    def test_create_article(self):
        article = NewsArticleFactory()
        assert article.pk is not None
        assert article.id_hash
        assert len(article.id_hash) == 8

    def test_str(self):
        article = NewsArticleFactory(title="Lakers Dominate Celtics")
        assert str(article) == "Lakers Dominate Celtics"

    def test_publish(self):
        article = DraftArticleFactory()
        assert article.status == NewsArticle.Status.DRAFT
        assert article.published_at is None

        article.publish()
        article.refresh_from_db()

        assert article.status == NewsArticle.Status.PUBLISHED
        assert article.published_at is not None

    def test_ordering_by_published_at(self):
        old = NewsArticleFactory(
            published_at=timezone.now() - timezone.timedelta(hours=2),
        )
        new = NewsArticleFactory(
            published_at=timezone.now() - timezone.timedelta(hours=1),
        )
        articles = list(NewsArticle.objects.all())
        assert articles == [new, old]

    def test_unique_recap_per_game_constraint(self):
        NewsArticleFactory(
            league="nba",
            article_type=NewsArticle.ArticleType.RECAP,
            game_id_hash="abc12345",
        )
        with pytest.raises(IntegrityError):
            NewsArticleFactory(
                league="nba",
                article_type=NewsArticle.ArticleType.RECAP,
                game_id_hash="abc12345",
            )

    def test_unique_constraint_allows_different_leagues(self):
        NewsArticleFactory(
            league="nba",
            article_type=NewsArticle.ArticleType.RECAP,
            game_id_hash="abc12345",
        )
        # Same game_id_hash but different league should be fine
        article = NewsArticleFactory(
            league="nfl",
            article_type=NewsArticle.ArticleType.RECAP,
            game_id_hash="abc12345",
        )
        assert article.pk is not None

    def test_unique_constraint_allows_non_recap_types(self):
        NewsArticleFactory(
            league="nba",
            article_type=NewsArticle.ArticleType.RECAP,
            game_id_hash="abc12345",
        )
        # Same league but different article type should be fine
        article = NewsArticleFactory(
            league="nba",
            article_type=NewsArticle.ArticleType.ROUNDUP,
            game_id_hash="abc12345",
        )
        assert article.pk is not None

    def test_blank_league_for_cross_league(self):
        article = NewsArticleFactory(
            league="",
            article_type=NewsArticle.ArticleType.CROSS_LEAGUE,
        )
        assert article.league == ""

    def test_nullable_author(self):
        article = NewsArticleFactory(author=None)
        assert article.author is None

    def test_status_choices(self):
        assert NewsArticle.Status.DRAFT == "draft"
        assert NewsArticle.Status.PUBLISHED == "published"
        assert NewsArticle.Status.ARCHIVED == "archived"

    def test_article_type_choices(self):
        assert NewsArticle.ArticleType.RECAP == "recap"
        assert NewsArticle.ArticleType.ROUNDUP == "roundup"
        assert NewsArticle.ArticleType.TREND == "trend"
        assert NewsArticle.ArticleType.CROSS_LEAGUE == "cross_league"
