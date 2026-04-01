import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from nfl.discussions.forms import CommentForm
from nfl.discussions.models import Comment
from nfl.games.models import Game

logger = logging.getLogger(__name__)


class CreateCommentView(LoginRequiredMixin, View):
    def post(self, request, id_hash):
        game = get_object_or_404(Game, id_hash=id_hash)
        form = CommentForm(request.POST)

        if not form.is_valid():
            return HttpResponse("Invalid comment", status=400)

        comment = Comment.objects.create(
            user=request.user,
            game=game,
            body=form.cleaned_data["body"],
        )

        from hub.consumers import notify_admin_dashboard

        notify_admin_dashboard("new_comment")

        if not request.user.is_bot:
            try:
                from nfl.bots.tasks import maybe_reply_to_human_comment

                maybe_reply_to_human_comment.delay(comment.pk)
            except Exception:
                logger.warning("Failed to dispatch bot reply task", exc_info=True)

        comment.prefetched_replies = []
        comment.reply_count = 0

        html = render_to_string(
            "nfl_discussions/partials/comment.html",
            {"comment": comment, "game": game, "depth": 0},
            request=request,
        )
        return HttpResponse(html)


class CreateReplyView(LoginRequiredMixin, View):
    def post(self, request, id_hash, comment_id):
        game = get_object_or_404(Game, id_hash=id_hash)
        parent = get_object_or_404(
            Comment.objects.select_related("parent"), pk=comment_id, game=game
        )

        if parent.depth >= Comment.MAX_DEPTH:
            return HttpResponse("Maximum reply depth reached.", status=400)

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
                league="nfl",
            )
        except Exception:
            logger.warning("Failed to create reply notification", exc_info=True)

        if not request.user.is_bot:
            try:
                from nfl.bots.tasks import maybe_reply_to_human_comment

                maybe_reply_to_human_comment.delay(reply.pk)
            except Exception:
                logger.warning("Failed to dispatch bot reply task", exc_info=True)

        reply_depth = parent.depth + 1
        reply.prefetched_replies = []

        html = render_to_string(
            "nfl_discussions/partials/comment.html",
            {"comment": reply, "game": game, "depth": reply_depth},
            request=request,
        )
        return HttpResponse(html)


class DeleteCommentView(LoginRequiredMixin, View):
    def post(self, request, id_hash, comment_id):
        comment = get_object_or_404(
            Comment.objects.select_related("game"),
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
            from django.db.models import Prefetch

            gc_qs = (
                Comment.objects.filter(is_deleted=False)
                .select_related("user")
                .order_by("created_at")
            )
            comment.prefetched_replies = list(
                comment.replies.filter(is_deleted=False)
                .select_related("user")
                .prefetch_related(
                    Prefetch("replies", queryset=gc_qs, to_attr="prefetched_replies")
                )
                .order_by("created_at")
            )
            html = render_to_string(
                "nfl_discussions/partials/comment.html",
                {"comment": comment, "game": game, "depth": comment.depth},
                request=request,
            )
        else:
            html = ""

        return HttpResponse(html)
