import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from betting.models import BetSlip
from discussions.forms import CommentForm
from discussions.models import Comment
from matches.models import Match

logger = logging.getLogger(__name__)

COMMENTS_PER_PAGE = 20


def _visible_top_level_qs(match):
    """Top-level comments that should appear in the list and be counted.

    A comment is visible if it is not deleted, or if it is deleted but still
    has at least one non-deleted reply (shown as a "[Comment deleted]" placeholder
    to preserve the reply thread).
    """
    has_visible_replies = Exists(
        Comment.objects.filter(parent=OuterRef("pk"), is_deleted=False)
    )
    return (
        Comment.objects.filter(match=match, parent__isnull=True)
        .annotate(has_visible_replies=has_visible_replies)
        .filter(Q(is_deleted=False) | Q(has_visible_replies=True))
    )


def _build_bet_map(match_pk, user_ids):
    """Return a dict mapping user_id -> their most recent BetSlip.Selection."""
    bets = (
        BetSlip.objects.filter(match_id=match_pk, user_id__in=user_ids)
        .order_by("user_id", "-created_at")
        .distinct("user_id")
        .values("user_id", "selection")
    )
    return {b["user_id"]: b["selection"] for b in bets}


def _annotate_bet_positions(comments, bet_map, match):
    """Annotate each comment (and its replies) with bet_position display text."""
    selection_labels = {
        BetSlip.Selection.HOME_WIN: f"Backing {match.home_team.short_name or match.home_team.name}",
        BetSlip.Selection.DRAW: "Backing Draw",
        BetSlip.Selection.AWAY_WIN: f"Backing {match.away_team.short_name or match.away_team.name}",
    }
    for comment in comments:
        selection = bet_map.get(comment.user_id)
        comment.bet_position = selection_labels.get(selection)
        if hasattr(comment, "prefetched_replies"):
            for reply in comment.prefetched_replies:
                sel = bet_map.get(reply.user_id)
                reply.bet_position = selection_labels.get(sel)


class CommentListView(View):
    def get(self, request, match_slug):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"), slug=match_slug
        )
        try:
            offset = max(0, int(request.GET.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0

        replies_qs = (
            Comment.objects.filter(is_deleted=False)
            .select_related("user")
            .order_by("created_at")
        )
        visible_qs = _visible_top_level_qs(match)
        comments = list(
            visible_qs.select_related("user")
            .prefetch_related(
                Prefetch("replies", queryset=replies_qs, to_attr="prefetched_replies")
            )
            .order_by("-created_at")[offset : offset + COMMENTS_PER_PAGE]
        )

        total_count = visible_qs.count()

        user_ids = {c.user_id for c in comments}
        for c in comments:
            user_ids.update(r.user_id for r in c.prefetched_replies)
        bet_map = _build_bet_map(match.pk, user_ids) if user_ids else {}
        _annotate_bet_positions(comments, bet_map, match)

        has_more = (offset + COMMENTS_PER_PAGE) < total_count
        next_offset = offset + COMMENTS_PER_PAGE

        context = {
            "match": match,
            "comments": comments,
            "comment_count": total_count,
            "has_more": has_more,
            "next_offset": next_offset,
            "form": CommentForm(),
            "request": request,
        }

        if offset > 0:
            html = render_to_string(
                "discussions/partials/comment_page.html", context, request=request
            )
        else:
            html = render_to_string(
                "discussions/partials/comment_list.html", context, request=request
            )
        return HttpResponse(html)


class CreateCommentView(LoginRequiredMixin, View):
    def post(self, request, match_slug):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"), slug=match_slug
        )
        form = CommentForm(request.POST)
        if not form.is_valid():
            html = render_to_string(
                "discussions/partials/comment_form.html",
                {"form": form, "match": match},
                request=request,
            )
            return HttpResponse(html, status=422)

        comment = Comment.objects.create(
            match=match,
            user=request.user,
            body=form.cleaned_data["body"],
        )

        # Maybe trigger a bot reply to this human comment.
        # Wrapped in try/except so broker failures don't break the user's post.
        if not request.user.is_bot:
            try:
                from bots.tasks import maybe_reply_to_human_comment

                maybe_reply_to_human_comment.delay(comment.pk)
            except Exception:
                logger.warning("Failed to dispatch bot reply task", exc_info=True)

        bet_map = _build_bet_map(match.pk, {request.user.pk})
        comment.prefetched_replies = []
        _annotate_bet_positions([comment], bet_map, match)

        new_count = _visible_top_level_qs(match).count()

        html = render_to_string(
            "discussions/partials/comment_single.html",
            {"comment": comment, "match": match, "is_reply": False},
            request=request,
        )
        html += render_to_string(
            "discussions/partials/comment_count_oob.html",
            {"comment_count": new_count},
        )
        return HttpResponse(html)


class CreateReplyView(LoginRequiredMixin, View):
    def post(self, request, match_slug, comment_pk):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"), slug=match_slug
        )
        parent = get_object_or_404(Comment, pk=comment_pk, match=match)

        if parent.parent_id is not None:
            return HttpResponse("Cannot reply to a reply.", status=400)

        form = CommentForm(request.POST)
        if not form.is_valid():
            error_msg = form.errors["body"][0] if "body" in form.errors else "Invalid reply."
            html = (
                f'<div id="reply-error-{parent.id_hash}" hx-swap-oob="true" '
                f'class="text-red-400 text-xs mt-1">{error_msg}</div>'
            )
            return HttpResponse(html, status=422)

        reply = Comment.objects.create(
            match=match,
            user=request.user,
            parent=parent,
            body=form.cleaned_data["body"],
        )

        # Maybe trigger a bot reply to the parent thread (not the reply itself,
        # since the UI only renders one level of nesting).
        # Wrapped in try/except so broker failures don't break the user's post.
        if not request.user.is_bot:
            try:
                from bots.tasks import maybe_reply_to_human_comment

                maybe_reply_to_human_comment.delay(parent.pk)
            except Exception:
                logger.warning("Failed to dispatch bot reply task", exc_info=True)

        bet_map = _build_bet_map(match.pk, {request.user.pk})
        reply.prefetched_replies = []
        _annotate_bet_positions([reply], bet_map, match)

        html = render_to_string(
            "discussions/partials/comment_single.html",
            {"comment": reply, "match": match, "is_reply": True},
            request=request,
        )
        return HttpResponse(html)


class DeleteCommentView(LoginRequiredMixin, View):
    def post(self, request, match_slug, comment_pk):
        comment = get_object_or_404(
            Comment.objects.select_related("match"),
            pk=comment_pk,
            match__slug=match_slug,
        )
        match = comment.match

        if comment.user_id != request.user.pk:
            return HttpResponseForbidden()

        comment.is_deleted = True
        comment.save(update_fields=["is_deleted", "updated_at"])

        has_replies = comment.replies.filter(is_deleted=False).exists()

        if has_replies:
            comment.prefetched_replies = list(
                comment.replies.filter(is_deleted=False)
                .select_related("user")
                .order_by("created_at")
            )
            user_ids = {comment.user_id} | {r.user_id for r in comment.prefetched_replies}
            bet_map = _build_bet_map(match.pk, user_ids) if user_ids else {}
            _annotate_bet_positions([comment], bet_map, match)
            html = render_to_string(
                "discussions/partials/comment_single.html",
                {"comment": comment, "match": match, "is_reply": False},
                request=request,
            )
        else:
            html = ""

        if not has_replies and comment.parent_id is None:
            new_count = _visible_top_level_qs(match).count()
            html += render_to_string(
                "discussions/partials/comment_count_oob.html",
                {"comment_count": new_count},
            )

        return HttpResponse(html)
