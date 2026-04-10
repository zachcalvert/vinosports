"""Tests for GameNotes — model, views, and bot prompt injection."""

import pytest
from django.test import Client

from nfl.bots.comment_service import _build_user_prompt
from nfl.bots.models import BotComment
from nfl.games.models import GameNotes, GameStatus
from nfl.tests.factories import (
    GameFactory,
    UserBalanceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_client():
    user = UserFactory()
    UserBalanceFactory(user=user)
    c = Client()
    c.force_login(user)
    return c, user


@pytest.fixture
def superuser_client():
    user = UserFactory()
    user.is_superuser = True
    user.save()
    UserBalanceFactory(user=user)
    c = Client()
    c.force_login(user)
    return c, user


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class TestGameNotesModel:
    def test_create_game_notes(self):
        game = GameFactory()
        notes = GameNotes.objects.create(game=game, body="Great game!")
        assert notes.body == "Great game!"
        assert notes.game == game

    def test_str(self):
        game = GameFactory()
        notes = GameNotes.objects.create(game=game, body="test")
        assert str(notes) == f"Notes for {game}"

    def test_one_to_one_constraint(self):
        game = GameFactory()
        GameNotes.objects.create(game=game, body="first")
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            GameNotes.objects.create(game=game, body="second")

    def test_related_name(self):
        game = GameFactory()
        notes = GameNotes.objects.create(game=game, body="test")
        assert game.notes == notes


# ---------------------------------------------------------------------------
# GameNotesView (HTMX endpoint)
# ---------------------------------------------------------------------------


class TestGameNotesView:
    def test_non_superuser_forbidden(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        resp = c.post(f"/nfl/games/{game.id_hash}/notes/", {"body": "test notes"})
        assert resp.status_code == 403

    def test_superuser_can_create_notes(self, superuser_client):
        c, user = superuser_client
        game = GameFactory()
        resp = c.post(f"/nfl/games/{game.id_hash}/notes/", {"body": "Great game!"})
        assert resp.status_code == 200
        assert GameNotes.objects.filter(game=game).exists()
        assert GameNotes.objects.get(game=game).body == "Great game!"

    def test_superuser_can_update_notes(self, superuser_client):
        c, user = superuser_client
        game = GameFactory()
        GameNotes.objects.create(game=game, body="initial")
        resp = c.post(f"/nfl/games/{game.id_hash}/notes/", {"body": "updated"})
        assert resp.status_code == 200
        assert GameNotes.objects.get(game=game).body == "updated"

    def test_response_contains_success_message(self, superuser_client):
        c, user = superuser_client
        game = GameFactory()
        resp = c.post(f"/nfl/games/{game.id_hash}/notes/", {"body": "notes"})
        assert resp.status_code == 200
        assert b"Notes saved" in resp.content

    def test_unauthenticated_redirected(self):
        c = Client()
        game = GameFactory()
        resp = c.post(f"/nfl/games/{game.id_hash}/notes/", {"body": "test"})
        assert resp.status_code in (301, 302)


# ---------------------------------------------------------------------------
# GameDetailView context
# ---------------------------------------------------------------------------


class TestGameDetailViewNotes:
    def test_superuser_sees_notes_form(self, superuser_client):
        c, user = superuser_client
        game = GameFactory()
        resp = c.get(f"/nfl/games/{game.id_hash}/")
        assert "game_notes_form" in resp.context

    def test_regular_user_does_not_see_notes_form(self, auth_client):
        c, user = auth_client
        game = GameFactory()
        resp = c.get(f"/nfl/games/{game.id_hash}/")
        assert "game_notes_form" not in resp.context

    def test_superuser_sees_existing_notes(self, superuser_client):
        c, user = superuser_client
        game = GameFactory()
        GameNotes.objects.create(game=game, body="existing notes")
        resp = c.get(f"/nfl/games/{game.id_hash}/")
        assert resp.context["game_notes"] is not None
        assert resp.context["game_notes"].body == "existing notes"

    def test_superuser_notes_none_when_no_notes(self, superuser_client):
        c, user = superuser_client
        game = GameFactory()
        resp = c.get(f"/nfl/games/{game.id_hash}/")
        assert resp.context["game_notes"] is None


# ---------------------------------------------------------------------------
# Bot prompt injection
# ---------------------------------------------------------------------------


class TestBuildUserPromptNotes:
    def test_post_match_includes_notes(self):
        game = GameFactory(status=GameStatus.FINAL, home_score=28, away_score=21)
        GameNotes.objects.create(game=game, body="Amazing goal-line stand in the 4th")
        prompt = _build_user_prompt(game, BotComment.TriggerType.POST_MATCH)
        assert "Match notes (from a real viewer):" in prompt
        assert "Amazing goal-line stand in the 4th" in prompt

    def test_reply_includes_notes(self):
        from nfl.discussions.models import Comment

        game = GameFactory(status=GameStatus.FINAL, home_score=28, away_score=21)
        GameNotes.objects.create(game=game, body="Two pick-sixes in the second half")
        user = UserFactory()
        comment = Comment.objects.create(game=game, user=user, body="What a game!")
        prompt = _build_user_prompt(
            game, BotComment.TriggerType.REPLY, parent_comment=comment
        )
        assert "Match notes (from a real viewer):" in prompt
        assert "Two pick-sixes in the second half" in prompt

    def test_pre_match_excludes_notes(self):
        game = GameFactory()
        GameNotes.objects.create(game=game, body="Should not appear")
        prompt = _build_user_prompt(game, BotComment.TriggerType.PRE_MATCH)
        assert "Match notes (from a real viewer):" not in prompt
        assert "Should not appear" not in prompt

    def test_post_bet_excludes_notes(self):
        from django.utils import timezone

        from nfl.betting.models import BetSlip, Odds

        game = GameFactory()
        Odds.objects.create(
            game=game,
            bookmaker="test",
            home_moneyline=-150,
            away_moneyline=130,
            fetched_at=timezone.now(),
        )
        user = UserFactory()
        UserBalanceFactory(user=user)
        bet = BetSlip.objects.create(
            user=user,
            game=game,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            odds_at_placement=-150,
            stake=50,
        )
        GameNotes.objects.create(game=game, body="Should not appear")
        prompt = _build_user_prompt(game, BotComment.TriggerType.POST_BET, bet_slip=bet)
        assert "Match notes (from a real viewer):" not in prompt

    def test_post_match_without_notes_succeeds(self):
        game = GameFactory(status=GameStatus.FINAL, home_score=35, away_score=17)
        prompt = _build_user_prompt(game, BotComment.TriggerType.POST_MATCH)
        assert "Match notes (from a real viewer):" not in prompt

    def test_empty_notes_excluded(self):
        game = GameFactory(status=GameStatus.FINAL, home_score=35, away_score=17)
        GameNotes.objects.create(game=game, body="   ")
        prompt = _build_user_prompt(game, BotComment.TriggerType.POST_MATCH)
        assert "Match notes (from a real viewer):" not in prompt
