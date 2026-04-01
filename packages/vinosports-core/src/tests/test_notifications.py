"""Tests for vinosports.activity — Notification model, notify_comment_reply helper, context processor, Celery task."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from vinosports.activity.models import Notification
from vinosports.activity.notifications import (
    NOTIFICATION_TTL,
    _build_match_subject,
    notify_comment_reply,
)
from vinosports.activity.tasks import dismiss_expired_notifications

from .factories import BotUserFactory, UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers — lightweight stubs for match/game and comment objects
# ---------------------------------------------------------------------------


class _FakeTeam:
    def __init__(self, *, tla=None, abbreviation=None):
        self.tla = tla
        self.abbreviation = abbreviation


class _FakeMatchOrGame:
    def __init__(self, *, home_team, away_team, dt, url="/fake/url/"):
        self.home_team = home_team
        self.away_team = away_team
        # EPL uses kickoff, NBA uses tip_off, NFL uses kickoff
        self.kickoff = dt
        self.tip_off = dt
        self._url = url

    def get_absolute_url(self):
        return self._url


class _FakeComment:
    def __init__(self, *, user, body="Test comment"):
        self.user = user
        self.body = body


# ---------------------------------------------------------------------------
# Notification model basics
# ---------------------------------------------------------------------------


class TestNotificationModel:
    def test_create_notification(self):
        user = UserFactory()
        actor = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            actor=actor,
            category=Notification.Category.REPLY,
            title="Someone replied",
            body="Nice bet!",
            url="/epl/match/test/",
            expires_at=timezone.now() + timedelta(hours=48),
        )
        assert n.id_hash
        assert n.is_read is False
        assert n.read_at is None

    def test_str_representation(self):
        user = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            category=Notification.Category.REPLY,
            title="test",
            expires_at=timezone.now() + timedelta(hours=48),
        )
        assert "REPLY" in str(n)
        assert n.id_hash in str(n)

    def test_ordering_newest_first(self):
        user = UserFactory()
        old = Notification.objects.create(
            recipient=user,
            category=Notification.Category.REPLY,
            title="old",
            expires_at=timezone.now() + timedelta(hours=48),
        )
        new = Notification.objects.create(
            recipient=user,
            category=Notification.Category.REPLY,
            title="new",
            expires_at=timezone.now() + timedelta(hours=48),
        )
        results = list(Notification.objects.filter(recipient=user))
        assert results[0] == new
        assert results[1] == old

    def test_cascade_delete_on_recipient(self):
        user = UserFactory()
        Notification.objects.create(
            recipient=user,
            category=Notification.Category.REPLY,
            title="test",
            expires_at=timezone.now() + timedelta(hours=48),
        )
        user.delete()
        assert Notification.objects.count() == 0

    def test_actor_set_null_on_delete(self):
        user = UserFactory()
        actor = UserFactory()
        n = Notification.objects.create(
            recipient=user,
            actor=actor,
            category=Notification.Category.REPLY,
            title="test",
            expires_at=timezone.now() + timedelta(hours=48),
        )
        actor.delete()
        n.refresh_from_db()
        assert n.actor is None


# ---------------------------------------------------------------------------
# notify_comment_reply helper
# ---------------------------------------------------------------------------


class TestNotifyCommentReply:
    def _make_match(self, league="epl"):
        if league == "epl":
            home = _FakeTeam(tla="ARS")
            away = _FakeTeam(tla="CHE")
        else:
            home = _FakeTeam(abbreviation="LAL")
            away = _FakeTeam(abbreviation="BOS")
        return _FakeMatchOrGame(
            home_team=home,
            away_team=away,
            dt=timezone.now(),
            url=f"/{league}/match/test/",
        )

    @patch("vinosports.activity.notifications._push_notification_ws")
    def test_creates_notification(self, mock_ws):
        parent_user = UserFactory(display_name="Alice")
        reply_user = UserFactory(display_name="Bob")
        match = self._make_match()

        n = notify_comment_reply(
            parent_comment=_FakeComment(user=parent_user),
            reply_comment=_FakeComment(user=reply_user, body="Great point!"),
            match_or_game=match,
            league="epl",
        )

        assert n is not None
        assert n.recipient == parent_user
        assert n.actor == reply_user
        assert n.category == Notification.Category.REPLY
        assert "Bob" in n.title
        assert "ARS vs CHE" in n.title
        assert n.body == "Great point!"
        assert n.url == "/epl/match/test/"
        assert n.expires_at > timezone.now()
        mock_ws.assert_called_once_with(n)

    @patch("vinosports.activity.notifications._push_notification_ws")
    def test_skips_self_reply(self, mock_ws):
        user = UserFactory()
        match = self._make_match()

        n = notify_comment_reply(
            parent_comment=_FakeComment(user=user),
            reply_comment=_FakeComment(user=user),
            match_or_game=match,
            league="epl",
        )

        assert n is None
        assert Notification.objects.count() == 0
        mock_ws.assert_not_called()

    @patch("vinosports.activity.notifications._push_notification_ws")
    def test_skips_bot_recipient(self, mock_ws):
        bot = BotUserFactory()
        human = UserFactory()
        match = self._make_match()

        n = notify_comment_reply(
            parent_comment=_FakeComment(user=bot),
            reply_comment=_FakeComment(user=human),
            match_or_game=match,
            league="epl",
        )

        assert n is None
        assert Notification.objects.count() == 0
        mock_ws.assert_not_called()

    @patch("vinosports.activity.notifications._push_notification_ws")
    def test_truncates_long_body(self, mock_ws):
        parent_user = UserFactory()
        reply_user = UserFactory()
        match = self._make_match()
        long_body = "x" * 300

        n = notify_comment_reply(
            parent_comment=_FakeComment(user=parent_user),
            reply_comment=_FakeComment(user=reply_user, body=long_body),
            match_or_game=match,
            league="epl",
        )

        assert len(n.body) == 203  # 200 chars + "..."
        assert n.body.endswith("...")

    @patch("vinosports.activity.notifications._push_notification_ws")
    def test_fallback_display_name(self, mock_ws):
        parent_user = UserFactory()
        reply_user = UserFactory(display_name="")
        match = self._make_match()

        n = notify_comment_reply(
            parent_comment=_FakeComment(user=parent_user),
            reply_comment=_FakeComment(user=reply_user),
            match_or_game=match,
            league="epl",
        )

        assert "Someone" in n.title

    @patch("vinosports.activity.notifications._push_notification_ws")
    def test_nba_league_subject(self, mock_ws):
        parent_user = UserFactory()
        reply_user = UserFactory(display_name="Bob")
        match = self._make_match(league="nba")

        n = notify_comment_reply(
            parent_comment=_FakeComment(user=parent_user),
            reply_comment=_FakeComment(user=reply_user),
            match_or_game=match,
            league="nba",
        )

        assert "NBA" in n.title
        assert "LAL vs BOS" in n.title

    @patch("vinosports.activity.notifications._push_notification_ws")
    def test_expires_at_uses_ttl(self, mock_ws):
        parent_user = UserFactory()
        reply_user = UserFactory()
        match = self._make_match()
        before = timezone.now()

        n = notify_comment_reply(
            parent_comment=_FakeComment(user=parent_user),
            reply_comment=_FakeComment(user=reply_user),
            match_or_game=match,
            league="epl",
        )

        after = timezone.now()
        assert n.expires_at >= before + NOTIFICATION_TTL
        assert n.expires_at <= after + NOTIFICATION_TTL


# ---------------------------------------------------------------------------
# _build_match_subject
# ---------------------------------------------------------------------------


class TestBuildMatchSubject:
    def test_epl_format(self):
        dt = timezone.now().replace(month=3, day=29)
        match = _FakeMatchOrGame(
            home_team=_FakeTeam(tla="ARS"),
            away_team=_FakeTeam(tla="CHE"),
            dt=dt,
        )
        result = _build_match_subject(match, "epl")
        assert result.startswith("EPL — ARS vs CHE — Mar 29")

    def test_nba_format(self):
        dt = timezone.now().replace(month=4, day=1)
        match = _FakeMatchOrGame(
            home_team=_FakeTeam(abbreviation="LAL"),
            away_team=_FakeTeam(abbreviation="BOS"),
            dt=dt,
        )
        result = _build_match_subject(match, "nba")
        assert result.startswith("NBA — LAL vs BOS — Apr 1")

    def test_nfl_format(self):
        dt = timezone.now().replace(month=1, day=12)
        match = _FakeMatchOrGame(
            home_team=_FakeTeam(abbreviation="KC"),
            away_team=_FakeTeam(abbreviation="BUF"),
            dt=dt,
        )
        result = _build_match_subject(match, "nfl")
        assert result.startswith("NFL — KC vs BUF — Jan 12")


# ---------------------------------------------------------------------------
# Context processor
# ---------------------------------------------------------------------------


class TestUnreadNotificationCountProcessor:
    def test_returns_zero_for_anonymous(self, client):
        resp = client.get("/")
        assert resp.context["unread_notification_count"] == 0

    def test_returns_zero_when_no_notifications(self):
        user = UserFactory()
        c = _authed_client(user)
        resp = c.get("/")
        assert resp.context["unread_notification_count"] == 0

    def test_counts_unread_only(self):
        user = UserFactory()
        _make_notification(user, is_read=False)
        _make_notification(user, is_read=False)
        _make_notification(user, is_read=True)

        c = _authed_client(user)
        resp = c.get("/")
        assert resp.context["unread_notification_count"] == 2

    def test_excludes_expired(self):
        user = UserFactory()
        _make_notification(user, is_read=False)
        _make_notification(
            user, is_read=False, expires_at=timezone.now() - timedelta(hours=1)
        )

        c = _authed_client(user)
        resp = c.get("/")
        assert resp.context["unread_notification_count"] == 1

    def test_excludes_other_users(self):
        user = UserFactory()
        other = UserFactory()
        _make_notification(user, is_read=False)
        _make_notification(other, is_read=False)

        c = _authed_client(user)
        resp = c.get("/")
        assert resp.context["unread_notification_count"] == 1


# ---------------------------------------------------------------------------
# Inbox views
# ---------------------------------------------------------------------------


class TestInboxView:
    def test_requires_login(self, client):
        resp = client.get("/inbox/")
        assert resp.status_code == 302

    def test_renders_for_authenticated_user(self):
        user = UserFactory()
        c = _authed_client(user)
        resp = c.get("/inbox/")
        assert resp.status_code == 200
        assert "hub/inbox.html" in [t.name for t in resp.templates]

    def test_shows_user_notifications(self):
        user = UserFactory()
        _make_notification(user)
        _make_notification(user)

        c = _authed_client(user)
        resp = c.get("/inbox/")
        assert len(resp.context["notifications"]) == 2

    def test_excludes_expired_notifications(self):
        user = UserFactory()
        _make_notification(user)
        _make_notification(user, expires_at=timezone.now() - timedelta(hours=1))

        c = _authed_client(user)
        resp = c.get("/inbox/")
        assert len(resp.context["notifications"]) == 1

    def test_excludes_other_users_notifications(self):
        user = UserFactory()
        other = UserFactory()
        _make_notification(user)
        _make_notification(other)

        c = _authed_client(user)
        resp = c.get("/inbox/")
        assert len(resp.context["notifications"]) == 1

    def test_unread_count_in_context(self):
        user = UserFactory()
        _make_notification(user, is_read=False)
        _make_notification(user, is_read=False)
        _make_notification(user, is_read=True)

        c = _authed_client(user)
        resp = c.get("/inbox/")
        assert resp.context["unread_count"] == 2


class TestMarkNotificationReadView:
    def test_requires_login(self, client):
        user = UserFactory()
        n = _make_notification(user)
        resp = client.post(f"/inbox/read/{n.id_hash}/")
        assert resp.status_code == 302

    def test_marks_as_read(self):
        user = UserFactory()
        n = _make_notification(user, is_read=False)
        c = _authed_client(user)
        resp = c.post(f"/inbox/read/{n.id_hash}/")
        assert resp.status_code == 302
        n.refresh_from_db()
        assert n.is_read is True
        assert n.read_at is not None

    def test_already_read_stays_read(self):
        user = UserFactory()
        original_read_at = timezone.now() - timedelta(hours=1)
        n = _make_notification(user, is_read=True)
        n.read_at = original_read_at
        n.save(update_fields=["read_at"])

        c = _authed_client(user)
        c.post(f"/inbox/read/{n.id_hash}/")
        n.refresh_from_db()
        assert n.is_read is True
        # read_at should not change since it was already read
        assert n.read_at == original_read_at

    def test_returns_partial_for_htmx(self):
        user = UserFactory()
        n = _make_notification(user, is_read=False)
        c = _authed_client(user)
        resp = c.post(
            f"/inbox/read/{n.id_hash}/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        assert b"notification-" in resp.content

    def test_cannot_mark_other_users_notification(self):
        user = UserFactory()
        other = UserFactory()
        n = _make_notification(other)
        c = _authed_client(user)
        resp = c.post(f"/inbox/read/{n.id_hash}/")
        assert resp.status_code == 404

    def test_404_for_invalid_id_hash(self):
        user = UserFactory()
        c = _authed_client(user)
        resp = c.post("/inbox/read/ZZZZZZZZ/")
        assert resp.status_code == 404


class TestMarkAllReadView:
    def test_requires_login(self, client):
        resp = client.post("/inbox/read-all/")
        assert resp.status_code == 302

    def test_marks_all_as_read(self):
        user = UserFactory()
        n1 = _make_notification(user, is_read=False)
        n2 = _make_notification(user, is_read=False)
        n3 = _make_notification(user, is_read=True)

        c = _authed_client(user)
        resp = c.post("/inbox/read-all/")
        assert resp.status_code == 302

        for n in [n1, n2, n3]:
            n.refresh_from_db()
            assert n.is_read is True

    def test_does_not_affect_other_users(self):
        user = UserFactory()
        other = UserFactory()
        n_user = _make_notification(user, is_read=False)
        n_other = _make_notification(other, is_read=False)

        c = _authed_client(user)
        c.post("/inbox/read-all/")

        n_user.refresh_from_db()
        n_other.refresh_from_db()
        assert n_user.is_read is True
        assert n_other.is_read is False

    def test_htmx_returns_refresh(self):
        user = UserFactory()
        _make_notification(user, is_read=False)
        c = _authed_client(user)
        resp = c.post("/inbox/read-all/", HTTP_HX_REQUEST="true")
        assert resp["HX-Refresh"] == "true"


# ---------------------------------------------------------------------------
# Celery task — dismiss_expired_notifications
# ---------------------------------------------------------------------------


class TestDismissExpiredNotifications:
    def test_deletes_expired_unread(self):
        user = UserFactory()
        _make_notification(
            user, is_read=False, expires_at=timezone.now() - timedelta(hours=1)
        )
        _make_notification(user, is_read=False)  # still valid

        result = dismiss_expired_notifications()
        assert "1 expired" in result
        assert Notification.objects.count() == 1

    def test_keeps_expired_read(self):
        """Read notifications aren't deleted by expiry — only by age (30 days)."""
        user = UserFactory()
        _make_notification(
            user, is_read=True, expires_at=timezone.now() - timedelta(hours=1)
        )

        dismiss_expired_notifications()
        assert Notification.objects.count() == 1

    def test_deletes_old_read(self):
        user = UserFactory()
        n = _make_notification(user, is_read=True)
        # Backdate created_at
        Notification.objects.filter(pk=n.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )

        result = dismiss_expired_notifications()
        assert "1 old read" in result
        assert Notification.objects.count() == 0

    def test_keeps_recent_read(self):
        user = UserFactory()
        _make_notification(user, is_read=True)

        dismiss_expired_notifications()
        assert Notification.objects.count() == 1

    def test_combined_cleanup(self):
        user = UserFactory()
        # Expired unread
        _make_notification(
            user, is_read=False, expires_at=timezone.now() - timedelta(hours=1)
        )
        # Old read
        n = _make_notification(user, is_read=True)
        Notification.objects.filter(pk=n.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        # Still valid
        _make_notification(user, is_read=False)

        result = dismiss_expired_notifications()
        assert "1 expired" in result
        assert "1 old read" in result
        assert Notification.objects.count() == 1


# ---------------------------------------------------------------------------
# Test utilities
# ---------------------------------------------------------------------------


def _authed_client(user):
    from django.test import Client

    c = Client()
    c.login(email=user.email, password="testpass123")
    return c


def _make_notification(user, *, is_read=False, expires_at=None):
    return Notification.objects.create(
        recipient=user,
        actor=UserFactory(),
        category=Notification.Category.REPLY,
        title="Test notification",
        body="Test body",
        url="/test/",
        is_read=is_read,
        read_at=timezone.now() if is_read else None,
        expires_at=expires_at or (timezone.now() + timedelta(hours=48)),
    )
