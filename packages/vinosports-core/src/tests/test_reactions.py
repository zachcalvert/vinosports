"""Tests for vinosports.reactions — models, toggle views, bot tasks, and template tags."""

from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import Client

from epl.discussions.models import Comment
from epl.matches.models import Match
from epl.tests.factories import (
    CommentFactory,
    MatchFactory,
    TeamFactory,
    UserFactory,
)
from news.tests.factories import NewsArticleFactory
from vinosports.bots.tasks import (
    _bot_team_lost,
    _bot_team_lost_article,
    _pick_positive_reaction,
    dispatch_bot_comment_reactions,
    dispatch_bot_pile_on_downvotes,
    react_as_bot_to_article,
    react_as_bot_to_comment,
)
from vinosports.reactions.models import (
    ArticleReaction,
    CommentReaction,
    ReactionType,
)

from .factories import BotProfileFactory, BotUserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user():
    return UserFactory(password="testpass123")


@pytest.fixture
def auth_client(user):
    c = Client()
    c.login(email=user.email, password="testpass123")
    return c


@pytest.fixture
def match():
    return MatchFactory()


@pytest.fixture
def comment(match, user):
    return CommentFactory(match=match, user=user)


@pytest.fixture
def article():
    return NewsArticleFactory()


@pytest.fixture
def comment_ct():
    return ContentType.objects.get_for_model(Comment)


# ---------------------------------------------------------------------------
# Model constraints
# ---------------------------------------------------------------------------


class TestCommentReactionConstraints:
    def test_one_reaction_per_user_per_comment(self, user, comment, comment_ct):
        CommentReaction.objects.create(
            user=user,
            content_type=comment_ct,
            object_id=comment.pk,
            reaction_type=ReactionType.THUMBS_UP,
        )
        with pytest.raises(Exception):
            CommentReaction.objects.create(
                user=user,
                content_type=comment_ct,
                object_id=comment.pk,
                reaction_type=ReactionType.THUMBS_DOWN,
            )

    def test_different_users_can_react_to_same_comment(self, comment, comment_ct):
        user1 = UserFactory()
        user2 = UserFactory()
        CommentReaction.objects.create(
            user=user1,
            content_type=comment_ct,
            object_id=comment.pk,
            reaction_type=ReactionType.THUMBS_UP,
        )
        r2 = CommentReaction.objects.create(
            user=user2,
            content_type=comment_ct,
            object_id=comment.pk,
            reaction_type=ReactionType.PARTY_CUP,
        )
        assert r2.pk is not None


class TestArticleReactionConstraints:
    def test_one_reaction_per_user_per_article(self, user, article):
        ArticleReaction.objects.create(
            user=user, article=article, reaction_type=ReactionType.THUMBS_UP
        )
        with pytest.raises(Exception):
            ArticleReaction.objects.create(
                user=user, article=article, reaction_type=ReactionType.THUMBS_DOWN
            )

    def test_different_users_can_react_to_same_article(self, article):
        user1 = UserFactory()
        user2 = UserFactory()
        ArticleReaction.objects.create(
            user=user1, article=article, reaction_type=ReactionType.THUMBS_UP
        )
        r2 = ArticleReaction.objects.create(
            user=user2, article=article, reaction_type=ReactionType.PARTY_CUP
        )
        assert r2.pk is not None


# ---------------------------------------------------------------------------
# Toggle views — comments
# ---------------------------------------------------------------------------


class TestToggleCommentReaction:
    def _url(self, ct_id, obj_id, rtype):
        return f"/reactions/comment/{ct_id}/{obj_id}/{rtype}/"

    def test_create_reaction(self, auth_client, comment, comment_ct):
        resp = auth_client.post(self._url(comment_ct.pk, comment.pk, "thumbs_up"))
        assert resp.status_code == 200
        assert CommentReaction.objects.filter(
            object_id=comment.pk, reaction_type="thumbs_up"
        ).exists()

    def test_toggle_off_same_emoji(self, auth_client, user, comment, comment_ct):
        CommentReaction.objects.create(
            user=user,
            content_type=comment_ct,
            object_id=comment.pk,
            reaction_type=ReactionType.THUMBS_UP,
        )
        resp = auth_client.post(self._url(comment_ct.pk, comment.pk, "thumbs_up"))
        assert resp.status_code == 200
        assert not CommentReaction.objects.filter(object_id=comment.pk).exists()

    def test_swap_to_different_emoji(self, auth_client, user, comment, comment_ct):
        CommentReaction.objects.create(
            user=user,
            content_type=comment_ct,
            object_id=comment.pk,
            reaction_type=ReactionType.THUMBS_UP,
        )
        resp = auth_client.post(self._url(comment_ct.pk, comment.pk, "party_cup"))
        assert resp.status_code == 200
        reaction = CommentReaction.objects.get(object_id=comment.pk)
        assert reaction.reaction_type == "party_cup"

    def test_invalid_reaction_type_returns_400(self, auth_client, comment, comment_ct):
        resp = auth_client.post(self._url(comment_ct.pk, comment.pk, "invalid_emoji"))
        assert resp.status_code == 400

    def test_unauthenticated_redirects(self, comment, comment_ct):
        c = Client()
        resp = c.post(self._url(comment_ct.pk, comment.pk, "thumbs_up"))
        assert resp.status_code == 302

    @patch("vinosports.reactions.dispatch.dispatch_pile_on_downvotes")
    def test_human_downvote_triggers_pile_on(
        self, mock_dispatch, auth_client, user, comment, comment_ct
    ):
        auth_client.post(self._url(comment_ct.pk, comment.pk, "thumbs_down"))
        mock_dispatch.assert_called_once_with(comment_ct.pk, comment.pk, user.pk)

    @patch("vinosports.reactions.dispatch.dispatch_pile_on_downvotes")
    def test_upvote_does_not_trigger_pile_on(
        self, mock_dispatch, auth_client, comment, comment_ct
    ):
        auth_client.post(self._url(comment_ct.pk, comment.pk, "thumbs_up"))
        mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Toggle views — articles
# ---------------------------------------------------------------------------


class TestToggleArticleReaction:
    def _url(self, id_hash, rtype):
        return f"/reactions/article/{id_hash}/{rtype}/"

    def test_create_reaction(self, auth_client, article):
        resp = auth_client.post(self._url(article.id_hash, "thumbs_up"))
        assert resp.status_code == 200
        assert ArticleReaction.objects.filter(article=article).exists()

    def test_toggle_off(self, auth_client, user, article):
        ArticleReaction.objects.create(
            user=user, article=article, reaction_type=ReactionType.THUMBS_UP
        )
        resp = auth_client.post(self._url(article.id_hash, "thumbs_up"))
        assert resp.status_code == 200
        assert not ArticleReaction.objects.filter(article=article).exists()

    def test_swap(self, auth_client, user, article):
        ArticleReaction.objects.create(
            user=user, article=article, reaction_type=ReactionType.THUMBS_UP
        )
        resp = auth_client.post(self._url(article.id_hash, "party_cup"))
        assert resp.status_code == 200
        reaction = ArticleReaction.objects.get(article=article)
        assert reaction.reaction_type == "party_cup"


# ---------------------------------------------------------------------------
# Bot reaction selection
# ---------------------------------------------------------------------------


class TestPickPositiveReaction:
    def test_only_returns_positive_types(self):
        """Bots should never randomly pick thumbs_down."""
        results = {_pick_positive_reaction("frontrunner") for _ in range(200)}
        assert results <= {"thumbs_up", "party_cup"}
        assert "thumbs_down" not in results

    def test_unknown_strategy_uses_default(self):
        result = _pick_positive_reaction("nonexistent_strategy")
        assert result in ("thumbs_up", "party_cup")


# ---------------------------------------------------------------------------
# Bot team lost — comments
# ---------------------------------------------------------------------------


class TestBotTeamLost:
    def test_team_lost_returns_true(self):
        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="CHE")
        match = MatchFactory(
            home_team=home,
            away_team=away,
            home_score=1,
            away_score=3,
            status=Match.Status.FINISHED,
        )
        comment = CommentFactory(match=match)
        profile = BotProfileFactory(epl_team_tla="ARS")

        assert _bot_team_lost(profile, comment) is True

    def test_team_won_returns_false(self):
        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="CHE")
        match = MatchFactory(
            home_team=home,
            away_team=away,
            home_score=3,
            away_score=1,
            status=Match.Status.FINISHED,
        )
        comment = CommentFactory(match=match)
        profile = BotProfileFactory(epl_team_tla="ARS")

        assert _bot_team_lost(profile, comment) is False

    def test_draw_returns_false(self):
        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="CHE")
        match = MatchFactory(
            home_team=home,
            away_team=away,
            home_score=2,
            away_score=2,
            status=Match.Status.FINISHED,
        )
        comment = CommentFactory(match=match)
        profile = BotProfileFactory(epl_team_tla="ARS")

        assert _bot_team_lost(profile, comment) is False

    def test_unfinished_match_returns_false(self):
        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="CHE")
        match = MatchFactory(
            home_team=home,
            away_team=away,
            home_score=0,
            away_score=2,
            status=Match.Status.SCHEDULED,
        )
        comment = CommentFactory(match=match)
        profile = BotProfileFactory(epl_team_tla="ARS")

        assert _bot_team_lost(profile, comment) is False

    def test_no_team_affiliation_returns_false(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=0, away_score=2)
        comment = CommentFactory(match=match)
        profile = BotProfileFactory(epl_team_tla="")

        assert _bot_team_lost(profile, comment) is False

    def test_away_team_lost(self):
        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="CHE")
        match = MatchFactory(
            home_team=home,
            away_team=away,
            home_score=3,
            away_score=1,
            status=Match.Status.FINISHED,
        )
        comment = CommentFactory(match=match)
        profile = BotProfileFactory(epl_team_tla="CHE")

        assert _bot_team_lost(profile, comment) is True


# ---------------------------------------------------------------------------
# Bot team lost — articles
# ---------------------------------------------------------------------------


class TestBotTeamLostArticle:
    def test_recap_with_losing_team(self):
        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="CHE")
        match = MatchFactory(
            home_team=home,
            away_team=away,
            home_score=1,
            away_score=3,
            status=Match.Status.FINISHED,
        )
        article = NewsArticleFactory(
            league="epl",
            article_type="recap",
            game_id_hash=match.id_hash,
        )
        profile = BotProfileFactory(epl_team_tla="ARS")

        assert _bot_team_lost_article(profile, article) is True

    def test_non_recap_article_returns_false(self):
        article = NewsArticleFactory(article_type="roundup")
        profile = BotProfileFactory(epl_team_tla="ARS")

        assert _bot_team_lost_article(profile, article) is False

    def test_recap_without_game_id_hash_returns_false(self):
        article = NewsArticleFactory(article_type="recap", game_id_hash="")
        profile = BotProfileFactory(epl_team_tla="ARS")

        assert _bot_team_lost_article(profile, article) is False


# ---------------------------------------------------------------------------
# Bot reaction tasks
# ---------------------------------------------------------------------------


class TestReactAsBotToComment:
    def test_creates_positive_reaction(self, comment, comment_ct):
        profile = BotProfileFactory()
        result = react_as_bot_to_comment(profile.user_id, comment_ct.pk, comment.pk)

        assert "reacted" in result
        reaction = CommentReaction.objects.get(
            user=profile.user, content_type=comment_ct, object_id=comment.pk
        )
        assert reaction.reaction_type in ("thumbs_up", "party_cup")

    def test_force_type_overrides_selection(self, comment, comment_ct):
        profile = BotProfileFactory()
        react_as_bot_to_comment(
            profile.user_id, comment_ct.pk, comment.pk, force_type="thumbs_down"
        )

        reaction = CommentReaction.objects.get(
            user=profile.user, content_type=comment_ct, object_id=comment.pk
        )
        assert reaction.reaction_type == "thumbs_down"

    def test_salty_bot_downvotes_when_team_lost(self):
        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="CHE")
        match = MatchFactory(
            home_team=home,
            away_team=away,
            home_score=0,
            away_score=2,
            status=Match.Status.FINISHED,
        )
        comment = CommentFactory(match=match)
        ct = ContentType.objects.get_for_model(Comment)
        profile = BotProfileFactory(epl_team_tla="ARS")

        react_as_bot_to_comment(profile.user_id, ct.pk, comment.pk)

        reaction = CommentReaction.objects.get(user=profile.user)
        assert reaction.reaction_type == "thumbs_down"

    def test_skips_if_already_reacted(self, comment, comment_ct):
        profile = BotProfileFactory()
        CommentReaction.objects.create(
            user=profile.user,
            content_type=comment_ct,
            object_id=comment.pk,
            reaction_type=ReactionType.THUMBS_UP,
        )
        result = react_as_bot_to_comment(profile.user_id, comment_ct.pk, comment.pk)
        assert "already reacted" in result

    def test_invalid_bot_user_returns_error(self, comment, comment_ct):
        result = react_as_bot_to_comment(999999, comment_ct.pk, comment.pk)
        assert "not found" in result


class TestReactAsBotToArticle:
    def test_creates_positive_reaction(self, article):
        profile = BotProfileFactory()
        result = react_as_bot_to_article(profile.user_id, article.pk)

        assert "reacted" in result
        reaction = ArticleReaction.objects.get(user=profile.user, article=article)
        assert reaction.reaction_type in ("thumbs_up", "party_cup")

    def test_salty_bot_downvotes_recap_of_loss(self):
        home = TeamFactory(tla="ARS")
        away = TeamFactory(tla="CHE")
        match = MatchFactory(
            home_team=home,
            away_team=away,
            home_score=0,
            away_score=2,
            status=Match.Status.FINISHED,
        )
        article = NewsArticleFactory(
            league="epl",
            article_type="recap",
            game_id_hash=match.id_hash,
        )
        profile = BotProfileFactory(epl_team_tla="ARS")

        react_as_bot_to_article(profile.user_id, article.pk)

        reaction = ArticleReaction.objects.get(user=profile.user)
        assert reaction.reaction_type == "thumbs_down"


# ---------------------------------------------------------------------------
# Dispatch tasks
# ---------------------------------------------------------------------------


class TestDispatchBotCommentReactions:
    def test_dispatches_reactions_from_multiple_bots(self, comment, comment_ct):
        for _ in range(5):
            BotProfileFactory()

        result = dispatch_bot_comment_reactions(
            comment_ct.pk, comment.pk, comment.user_id
        )

        assert "dispatched" in result
        count = CommentReaction.objects.filter(
            content_type=comment_ct, object_id=comment.pk
        ).count()
        assert 2 <= count <= 5

    def test_excludes_comment_author(self, match, comment_ct):
        bot_user = BotUserFactory()
        BotProfileFactory(user=bot_user)
        comment = CommentFactory(match=match, user=bot_user)

        # Only one bot exists and it's the author — should be excluded
        result = dispatch_bot_comment_reactions(
            comment_ct.pk, comment.pk, comment.user_id
        )
        assert result == "no active bots"


class TestDispatchBotPileOnDownvotes:
    def test_dispatches_downvotes(self, comment, comment_ct, user):
        for _ in range(5):
            BotProfileFactory()

        result = dispatch_bot_pile_on_downvotes(comment_ct.pk, comment.pk, user.pk)

        assert "dispatched" in result
        downvotes = CommentReaction.objects.filter(
            content_type=comment_ct,
            object_id=comment.pk,
            reaction_type="thumbs_down",
        ).count()
        assert 1 <= downvotes <= 3

    def test_skips_bots_that_already_reacted(self, comment, comment_ct, user):
        profiles = [BotProfileFactory() for _ in range(3)]
        # All bots already reacted
        for p in profiles:
            CommentReaction.objects.create(
                user=p.user,
                content_type=comment_ct,
                object_id=comment.pk,
                reaction_type=ReactionType.THUMBS_UP,
            )

        result = dispatch_bot_pile_on_downvotes(comment_ct.pk, comment.pk, user.pk)
        assert "no available bots" in result


# ---------------------------------------------------------------------------
# Response includes reactors for tooltips
# ---------------------------------------------------------------------------


class TestReactionTooltips:
    def test_toggle_response_includes_reactor_names(
        self, auth_client, user, comment, comment_ct
    ):
        # Another user reacts first
        other = UserFactory(display_name="OtherUser")
        CommentReaction.objects.create(
            user=other,
            content_type=comment_ct,
            object_id=comment.pk,
            reaction_type=ReactionType.THUMBS_UP,
        )

        # Our user reacts with a different emoji
        resp = auth_client.post(
            f"/reactions/comment/{comment_ct.pk}/{comment.pk}/party_cup/"
        )
        html = resp.content.decode()

        # The response should include the other user's name in a title attribute
        assert "OtherUser" in html

    def test_article_response_includes_reactor_names(self, auth_client, user, article):
        other = UserFactory(display_name="ArticleFan")
        ArticleReaction.objects.create(
            user=other,
            article=article,
            reaction_type=ReactionType.PARTY_CUP,
        )

        resp = auth_client.post(f"/reactions/article/{article.id_hash}/thumbs_up/")
        html = resp.content.decode()
        assert "ArticleFan" in html
