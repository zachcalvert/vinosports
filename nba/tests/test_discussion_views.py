"""Tests for discussions/views.py (CreateCommentView, CreateReplyView)."""

import pytest
from django.test import Client

from nba.discussions.models import Comment
from nba.tests.factories import CommentFactory, GameFactory, UserFactory


@pytest.fixture
def auth_client(db):
    user = UserFactory()
    c = Client()
    c.force_login(user)
    return c, user


@pytest.mark.django_db
class TestCreateCommentView:
    def test_unauthenticated_redirected(self):
        c = Client()
        game = GameFactory()
        response = c.post(
            f"/nba/game/{game.id_hash}/comments/create/",
            {"body": "Great game!"},
        )
        assert response.status_code in (301, 302)

    def test_valid_comment_creates_record(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        count_before = Comment.objects.count()
        c.post(
            f"/nba/game/{game.id_hash}/comments/create/",
            {"body": "Great game!"},
        )
        assert Comment.objects.count() == count_before + 1

    def test_valid_comment_sets_user_and_game(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        c.post(
            f"/nba/game/{game.id_hash}/comments/create/",
            {"body": "This is my comment."},
        )
        comment = Comment.objects.latest("created_at")
        assert comment.user == user
        assert comment.game == game
        assert comment.body == "This is my comment."

    def test_valid_comment_redirects(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        response = c.post(
            f"/nba/game/{game.id_hash}/comments/create/",
            {"body": "Nice!"},
        )
        assert response.status_code in (301, 302)

    def test_empty_body_returns_400(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        response = c.post(
            f"/nba/game/{game.id_hash}/comments/create/",
            {"body": ""},
        )
        assert response.status_code == 400

    def test_body_too_long_returns_400(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        response = c.post(
            f"/nba/game/{game.id_hash}/comments/create/",
            {"body": "x" * 1001},
        )
        assert response.status_code == 400

    def test_game_not_found_returns_404(self, auth_client):
        c, user = auth_client
        response = c.post(
            "/nba/game/nonexistent/comments/create/",
            {"body": "test"},
        )
        assert response.status_code == 404

    def test_comment_has_no_parent(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        c.post(
            f"/nba/game/{game.id_hash}/comments/create/",
            {"body": "Top-level comment."},
        )
        comment = Comment.objects.latest("created_at")
        assert comment.parent is None


@pytest.mark.django_db
class TestCreateReplyView:
    def test_unauthenticated_redirected(self):
        c = Client()
        game = GameFactory()
        parent = CommentFactory(game=game)
        response = c.post(
            f"/nba/game/{game.id_hash}/comments/{parent.pk}/reply/",
            {"body": "Great reply!"},
        )
        assert response.status_code in (301, 302)

    def test_valid_reply_creates_record(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        parent = CommentFactory(game=game)
        count_before = Comment.objects.count()
        c.post(
            f"/nba/game/{game.id_hash}/comments/{parent.pk}/reply/",
            {"body": "I agree!"},
        )
        assert Comment.objects.count() == count_before + 1

    def test_reply_has_correct_parent(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        parent = CommentFactory(game=game)
        c.post(
            f"/nba/game/{game.id_hash}/comments/{parent.pk}/reply/",
            {"body": "Reply text."},
        )
        reply = Comment.objects.filter(parent=parent).latest("created_at")
        assert reply.parent == parent
        assert reply.game == game
        assert reply.user == user

    def test_reply_redirects(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        parent = CommentFactory(game=game)
        response = c.post(
            f"/nba/game/{game.id_hash}/comments/{parent.pk}/reply/",
            {"body": "Agreed!"},
        )
        assert response.status_code in (301, 302)

    def test_empty_body_returns_400(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        parent = CommentFactory(game=game)
        response = c.post(
            f"/nba/game/{game.id_hash}/comments/{parent.pk}/reply/",
            {"body": ""},
        )
        assert response.status_code == 400

    def test_game_not_found_returns_404(self, auth_client):
        c, user = auth_client
        parent_id = 999
        response = c.post(
            f"/nba/game/nonexistent/comments/{parent_id}/reply/",
            {"body": "test"},
        )
        assert response.status_code == 404

    def test_parent_comment_not_found_returns_404(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        response = c.post(
            f"/nba/game/{game.id_hash}/comments/999999/reply/",
            {"body": "test"},
        )
        assert response.status_code == 404

    def test_parent_from_different_game_returns_404(self, auth_client):
        c, user = auth_client
        game1 = GameFactory()
        game2 = GameFactory()
        parent = CommentFactory(game=game1)
        response = c.post(
            f"/nba/game/{game2.id_hash}/comments/{parent.pk}/reply/",
            {"body": "test"},
        )
        assert response.status_code == 404
