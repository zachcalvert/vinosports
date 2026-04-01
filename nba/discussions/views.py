import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from nba.betting.models import BetSlip
from nba.discussions.forms import CommentForm
from nba.discussions.models import Comment
from nba.games.models import Game

logger = logging.getLogger(__name__)


def _build_bet_map(game_pk, user_ids):
    """Return a dict mapping user_id -> their most recent moneyline BetSlip.Selection."""
    bets = (
        BetSlip.objects.filter(
            game_id=game_pk, user_id__in=user_ids, market=BetSlip.Market.MONEYLINE
        )
        .order_by("user_id", "-created_at")
        .distinct("user_id")
        .values("user_id", "selection")
    )
    return {b["user_id"]: b["selection"] for b in bets}


def _annotate_bet_positions(comments, bet_map, game):
    """Annotate each comment (and its replies) with bet_position display text."""
    selection_labels = {
        BetSlip.Selection.HOME: f"Backing {game.home_team.short_name or game.home_team.name}",
        BetSlip.Selection.AWAY: f"Backing {game.away_team.short_name or game.away_team.name}",
    }
    for comment in comments:
        selection = bet_map.get(comment.user_id)
        comment.bet_position = selection_labels.get(selection)
        if hasattr(comment, "prefetched_replies"):
            for reply in comment.prefetched_replies:
                sel = bet_map.get(reply.user_id)
                reply.bet_position = selection_labels.get(sel)


class CreateCommentView(LoginRequiredMixin, View):
    def post(self, request, id_hash):
        game = get_object_or_404(
            Game.objects.select_related("home_team", "away_team"),
            id_hash=id_hash,
        )
        form = CommentForm(request.POST)

        if not form.is_valid():
            return HttpResponse("Invalid comment", status=400)

        comment = Comment.objects.create(
            user=request.user,
            game=game,
            body=form.cleaned_data["body"],
        )

        if not request.user.is_bot:
            try:
                from nba.bots.tasks import maybe_reply_to_human_comment

                maybe_reply_to_human_comment.delay(comment.pk)
            except Exception:
                logger.warning("Failed to dispatch bot reply task", exc_info=True)

        bet_map = _build_bet_map(game.pk, {request.user.pk})
        comment.prefetched_replies = []
        comment.reply_count = 0
        _annotate_bet_positions([comment], bet_map, game)

        html = render_to_string(
            "nba_discussions/partials/comment.html",
            {"comment": comment, "game": game, "is_reply": False},
            request=request,
        )
        return HttpResponse(html)


class CreateReplyView(LoginRequiredMixin, View):
    def post(self, request, id_hash, comment_id):
        game = get_object_or_404(
            Game.objects.select_related("home_team", "away_team"),
            id_hash=id_hash,
        )
        parent = get_object_or_404(Comment, pk=comment_id, game=game)

        if parent.parent_id is not None:
            return HttpResponse("Cannot reply to a reply.", status=400)

        form = CommentForm(request.POST)
        if not form.is_valid():
            error_msg = (
                form.errors["body"][0] if "body" in form.errors else "Invalid reply."
            )
            html = (
                f'<div id="reply-error-{parent.id_hash}" hx-swap-oob="true" '
                f'class="text-danger text-xs mt-1">{error_msg}</div>'
            )
            return HttpResponse(html, status=422)

        reply = Comment.objects.create(
            user=request.user,
            game=game,
            parent=parent,
            body=form.cleaned_data["body"],
        )

        # Notify parent comment author
        try:
            from vinosports.activity.notifications import notify_comment_reply

            notify_comment_reply(
                parent_comment=parent,
                reply_comment=reply,
                match_or_game=game,
                league="nba",
            )
        except Exception:
            logger.warning("Failed to create reply notification", exc_info=True)

        if not request.user.is_bot:
            try:
                from nba.bots.tasks import maybe_reply_to_human_comment

                maybe_reply_to_human_comment.delay(parent.pk)
            except Exception:
                logger.warning("Failed to dispatch bot reply task", exc_info=True)

        bet_map = _build_bet_map(game.pk, {request.user.pk})
        reply.prefetched_replies = []
        _annotate_bet_positions([reply], bet_map, game)

        html = render_to_string(
            "nba_discussions/partials/comment.html",
            {"comment": reply, "game": game, "is_reply": True},
            request=request,
        )
        return HttpResponse(html)


class DeleteCommentView(LoginRequiredMixin, View):
    def post(self, request, id_hash, comment_id):
        comment = get_object_or_404(
            Comment.objects.select_related("game__home_team", "game__away_team"),
            pk=comment_id,
            game__id_hash=id_hash,
        )

        if comment.user_id != request.user.pk:
            return HttpResponseForbidden()

        comment.is_deleted = True
        comment.save(update_fields=["is_deleted", "updated_at"])

        game = comment.game
        has_replies = comment.replies.filter(is_deleted=False).exists()

        if has_replies:
            comment.prefetched_replies = list(
                comment.replies.filter(is_deleted=False)
                .select_related("user")
                .order_by("created_at")
            )
            user_ids = {comment.user_id} | {
                r.user_id for r in comment.prefetched_replies
            }
            bet_map = _build_bet_map(game.pk, user_ids) if user_ids else {}
            _annotate_bet_positions([comment], bet_map, game)
            is_reply = comment.parent_id is not None
            html = render_to_string(
                "nba_discussions/partials/comment.html",
                {"comment": comment, "game": game, "is_reply": is_reply},
                request=request,
            )
        else:
            html = ""

        return HttpResponse(html)
