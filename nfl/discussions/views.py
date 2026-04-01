from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from nfl.discussions.forms import CommentForm
from nfl.discussions.models import Comment
from nfl.games.models import Game


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

        comment.prefetched_replies = []

        html = render_to_string(
            "nfl_discussions/partials/comment.html",
            {"comment": comment, "game": game, "is_reply": False},
            request=request,
        )
        return HttpResponse(html)


class CreateReplyView(LoginRequiredMixin, View):
    def post(self, request, id_hash, comment_id):
        game = get_object_or_404(Game, id_hash=id_hash)
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
                league="nfl",
            )
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to create reply notification", exc_info=True
            )

        reply.prefetched_replies = []

        html = render_to_string(
            "nfl_discussions/partials/comment.html",
            {"comment": reply, "game": game, "is_reply": True},
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
            comment.prefetched_replies = list(
                comment.replies.filter(is_deleted=False)
                .select_related("user")
                .order_by("created_at")
            )
            is_reply = comment.parent_id is not None
            html = render_to_string(
                "nfl_discussions/partials/comment.html",
                {"comment": comment, "game": game, "is_reply": is_reply},
                request=request,
            )
        else:
            html = ""

        return HttpResponse(html)
