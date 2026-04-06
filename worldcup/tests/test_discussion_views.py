"""Tests for worldcup discussions views — CommentListView, CreateCommentView, CreateReplyView, DeleteCommentView."""

import pytest
from django.test import Client

from worldcup.discussions.models import Comment

from .factories import CommentFactory, MatchFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_client():
    user = UserFactory(password="testpass123")
    c = Client()
    c.login(email=user.email, password="testpass123")
    return c, user


class TestCommentListView:
    def test_returns_200(self):
        match = MatchFactory()
        c = Client()
        resp = c.get(f"/worldcup/match/{match.slug}/comments/")
        assert resp.status_code == 200

    def test_returns_comments(self):
        match = MatchFactory()
        CommentFactory(match=match)
        CommentFactory(match=match)
        c = Client()
        resp = c.get(f"/worldcup/match/{match.slug}/comments/")
        assert resp.status_code == 200
        assert len(resp.content) > 0

    def test_pagination_with_offset(self):
        match = MatchFactory()
        user = UserFactory()
        Comment.objects.bulk_create(
            [Comment(user=user, match=match, body=f"Comment {i}") for i in range(25)]
        )
        c = Client()
        resp = c.get(f"/worldcup/match/{match.slug}/comments/?offset=20")
        assert resp.status_code == 200

    def test_invalid_offset_defaults_to_zero(self):
        match = MatchFactory()
        c = Client()
        resp = c.get(f"/worldcup/match/{match.slug}/comments/?offset=abc")
        assert resp.status_code == 200

    def test_deleted_comments_without_replies_hidden(self):
        match = MatchFactory()
        CommentFactory(match=match, is_deleted=True)
        c = Client()
        resp = c.get(f"/worldcup/match/{match.slug}/comments/")
        assert resp.status_code == 200

    def test_deleted_comment_with_visible_replies_shown(self):
        match = MatchFactory()
        parent = CommentFactory(match=match, is_deleted=True)
        CommentFactory(match=match, parent=parent, is_deleted=False)
        c = Client()
        resp = c.get(f"/worldcup/match/{match.slug}/comments/")
        assert resp.status_code == 200
        assert len(resp.content) > 0

    def test_404_for_invalid_slug(self):
        c = Client()
        resp = c.get("/worldcup/match/no-such-match/comments/")
        assert resp.status_code == 404


class TestCreateCommentView:
    def test_unauthenticated_redirected(self):
        match = MatchFactory()
        c = Client()
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/create/",
            {"body": "Great match!"},
        )
        assert resp.status_code in (301, 302)

    def test_valid_comment_creates_record(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        count_before = Comment.objects.count()
        c.post(
            f"/worldcup/match/{match.slug}/comments/create/",
            {"body": "Great match!"},
        )
        assert Comment.objects.count() == count_before + 1

    def test_sets_user_and_match(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        c.post(
            f"/worldcup/match/{match.slug}/comments/create/",
            {"body": "My comment."},
        )
        comment = Comment.objects.latest("created_at")
        assert comment.user == user
        assert comment.match == match
        assert comment.body == "My comment."
        assert comment.parent is None

    def test_empty_body_returns_422(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/create/",
            {"body": ""},
        )
        assert resp.status_code == 422

    def test_body_too_long_returns_422(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/create/",
            {"body": "x" * 1001},
        )
        assert resp.status_code == 422

    def test_match_not_found_returns_404(self, auth_client):
        c, user = auth_client
        resp = c.post(
            "/worldcup/match/nonexistent/comments/create/",
            {"body": "test"},
        )
        assert resp.status_code == 404

    def test_returns_html_response(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/create/",
            {"body": "HTMX comment!"},
        )
        assert resp.status_code == 200
        assert len(resp.content) > 0


class TestCreateReplyView:
    def test_unauthenticated_redirected(self):
        match = MatchFactory()
        parent = CommentFactory(match=match)
        c = Client()
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/{parent.pk}/reply/",
            {"body": "Reply!"},
        )
        assert resp.status_code in (301, 302)

    def test_valid_reply_creates_record(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        parent = CommentFactory(match=match)
        count_before = Comment.objects.count()
        c.post(
            f"/worldcup/match/{match.slug}/comments/{parent.pk}/reply/",
            {"body": "I agree!"},
        )
        assert Comment.objects.count() == count_before + 1

    def test_reply_has_correct_parent(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        parent = CommentFactory(match=match)
        c.post(
            f"/worldcup/match/{match.slug}/comments/{parent.pk}/reply/",
            {"body": "Reply text."},
        )
        reply = Comment.objects.filter(parent=parent).latest("created_at")
        assert reply.parent == parent
        assert reply.match == match
        assert reply.user == user

    def test_can_reply_to_a_reply(self, auth_client):
        """Depth-1 replies can receive replies (grandchildren at depth 2)."""
        c, user = auth_client
        match = MatchFactory()
        parent = CommentFactory(match=match)
        reply = CommentFactory(match=match, parent=parent)
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/{reply.pk}/reply/",
            {"body": "Nested reply."},
        )
        assert resp.status_code == 200

    def test_cannot_reply_beyond_max_depth(self, auth_client):
        """Depth-2 grandchildren cannot receive further replies."""
        c, user = auth_client
        match = MatchFactory()
        parent = CommentFactory(match=match)
        reply = CommentFactory(match=match, parent=parent)
        grandchild = CommentFactory(match=match, parent=reply)
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/{grandchild.pk}/reply/",
            {"body": "Too deep."},
        )
        assert resp.status_code == 400

    def test_empty_body_returns_422(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        parent = CommentFactory(match=match)
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/{parent.pk}/reply/",
            {"body": ""},
        )
        assert resp.status_code == 422

    def test_parent_not_found_returns_404(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/999999/reply/",
            {"body": "test"},
        )
        assert resp.status_code == 404

    def test_parent_from_different_match_returns_404(self, auth_client):
        c, user = auth_client
        match1 = MatchFactory()
        match2 = MatchFactory()
        parent = CommentFactory(match=match1)
        resp = c.post(
            f"/worldcup/match/{match2.slug}/comments/{parent.pk}/reply/",
            {"body": "test"},
        )
        assert resp.status_code == 404


class TestDeleteCommentView:
    def test_unauthenticated_redirected(self):
        match = MatchFactory()
        comment = CommentFactory(match=match)
        c = Client()
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/{comment.pk}/delete/",
        )
        assert resp.status_code in (301, 302)

    def test_owner_can_delete(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        comment = CommentFactory(match=match, user=user)
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/{comment.pk}/delete/",
        )
        assert resp.status_code == 200
        comment.refresh_from_db()
        assert comment.is_deleted is True

    def test_non_owner_gets_403(self, auth_client):
        c, user = auth_client
        other = UserFactory()
        match = MatchFactory()
        comment = CommentFactory(match=match, user=other)
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/{comment.pk}/delete/",
        )
        assert resp.status_code == 403
        comment.refresh_from_db()
        assert comment.is_deleted is False

    def test_returns_empty_when_no_replies(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        comment = CommentFactory(match=match, user=user)
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/{comment.pk}/delete/",
        )
        assert resp.status_code == 200

    def test_returns_html_when_replies_exist(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        comment = CommentFactory(match=match, user=user)
        CommentFactory(match=match, parent=comment)  # a reply
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/{comment.pk}/delete/",
        )
        assert resp.status_code == 200
        assert len(resp.content) > 0

    def test_comment_not_found_returns_404(self, auth_client):
        c, user = auth_client
        match = MatchFactory()
        resp = c.post(
            f"/worldcup/match/{match.slug}/comments/999999/delete/",
        )
        assert resp.status_code == 404
