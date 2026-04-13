import logging

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from news.models import NewsArticle

from .dispatch import dispatch_pile_on_downvotes
from .models import ArticleReaction, CommentReaction, ReactionType

logger = logging.getLogger(__name__)

VALID_REACTION_TYPES = {choice.value for choice in ReactionType}
REACTION_CHOICES = [(r.value, r.label) for r in ReactionType]


def _build_reactors(qs):
    """Build a dict of reaction_type -> [display_name, ...] from a reaction queryset."""
    reactors = {}
    for rtype, name in qs.values_list("reaction_type", "user__display_name"):
        reactors.setdefault(rtype, []).append(name)
    return reactors


def _render_comment_reaction_buttons(content_type_id, object_id, request):
    """Render the reaction buttons partial for a comment."""
    qs = CommentReaction.objects.filter(
        content_type_id=content_type_id, object_id=object_id
    )
    counts = dict(qs.values_list("reaction_type").annotate(count=Count("id")))
    reactors = _build_reactors(qs)
    user_reaction = None
    if request.user.is_authenticated:
        user_reaction = (
            qs.filter(user=request.user).values_list("reaction_type", flat=True).first()
        )
    return render_to_string(
        "reactions/partials/reaction_buttons.html",
        {
            "target_type": "comment",
            "content_type_id": content_type_id,
            "target_id": object_id,
            "counts": counts,
            "reactors": reactors,
            "user_reaction": user_reaction,
            "reaction_choices": REACTION_CHOICES,
        },
        request=request,
    )


def _render_article_reaction_buttons(article, request):
    """Render the reaction buttons partial for an article."""
    qs = ArticleReaction.objects.filter(article=article)
    counts = dict(qs.values_list("reaction_type").annotate(count=Count("id")))
    reactors = _build_reactors(qs)
    user_reaction = None
    if request.user.is_authenticated:
        user_reaction = (
            qs.filter(user=request.user).values_list("reaction_type", flat=True).first()
        )
    return render_to_string(
        "reactions/partials/reaction_buttons.html",
        {
            "target_type": "article",
            "content_type_id": None,
            "target_id": article.id_hash,
            "counts": counts,
            "reactors": reactors,
            "user_reaction": user_reaction,
            "reaction_choices": REACTION_CHOICES,
        },
        request=request,
    )


@require_POST
@login_required
def toggle_comment_reaction(request, content_type_id, object_id, reaction_type):
    """Toggle a reaction on a comment (any league)."""
    if reaction_type not in VALID_REACTION_TYPES:
        return HttpResponseBadRequest("Invalid reaction type.")

    ct = get_object_or_404(ContentType, pk=content_type_id)
    # Verify the object exists
    model_class = ct.model_class()
    if model_class is None:
        return HttpResponseBadRequest("Invalid content type.")
    get_object_or_404(model_class, pk=object_id)

    existing = CommentReaction.objects.filter(
        user=request.user, content_type_id=content_type_id, object_id=object_id
    ).first()

    created_downvote = False
    if existing:
        if existing.reaction_type == reaction_type:
            # Same emoji — toggle off
            existing.delete()
        else:
            # Different emoji — swap
            existing.reaction_type = reaction_type
            existing.save(update_fields=["reaction_type", "updated_at"])
            created_downvote = reaction_type == "thumbs_down"
    else:
        CommentReaction.objects.create(
            user=request.user,
            content_type_id=content_type_id,
            object_id=object_id,
            reaction_type=reaction_type,
        )
        created_downvote = reaction_type == "thumbs_down"

    # When a real user downvotes, bots pile on
    if created_downvote and not request.user.is_bot:
        dispatch_pile_on_downvotes(content_type_id, object_id, request.user.pk)

    html = _render_comment_reaction_buttons(content_type_id, object_id, request)
    return HttpResponse(html)


@require_POST
@login_required
def toggle_article_reaction(request, id_hash, reaction_type):
    """Toggle a reaction on a news article."""
    if reaction_type not in VALID_REACTION_TYPES:
        return HttpResponseBadRequest("Invalid reaction type.")

    article = get_object_or_404(NewsArticle, id_hash=id_hash)

    existing = ArticleReaction.objects.filter(
        user=request.user, article=article
    ).first()

    if existing:
        if existing.reaction_type == reaction_type:
            existing.delete()
        else:
            existing.reaction_type = reaction_type
            existing.save(update_fields=["reaction_type", "updated_at"])
    else:
        ArticleReaction.objects.create(
            user=request.user,
            article=article,
            reaction_type=reaction_type,
        )

    html = _render_article_reaction_buttons(article, request)
    return HttpResponse(html)


def get_comment_reaction_context(comment, request):
    """Build template context for a single comment's reactions.

    Call this from league discussion views and pass the result into the
    comment_single.html template context.
    """
    ct = ContentType.objects.get_for_model(comment)
    counts = dict(
        CommentReaction.objects.filter(content_type=ct, object_id=comment.pk)
        .values_list("reaction_type")
        .annotate(count=Count("id"))
    )
    user_reaction = None
    if request.user.is_authenticated:
        user_reaction = (
            CommentReaction.objects.filter(
                content_type=ct, object_id=comment.pk, user=request.user
            )
            .values_list("reaction_type", flat=True)
            .first()
        )
    return {
        "content_type_id": ct.pk,
        "target_id": comment.pk,
        "counts": counts,
        "user_reaction": user_reaction,
    }


def bulk_get_comment_reaction_context(comments, request):
    """Build reaction context for a list of comments (avoids N+1).

    Returns a dict mapping comment.pk -> reaction context dict.
    """
    if not comments:
        return {}

    ct = ContentType.objects.get_for_model(comments[0])
    comment_pks = [c.pk for c in comments]

    # Aggregate counts per comment per reaction type
    rows = (
        CommentReaction.objects.filter(content_type=ct, object_id__in=comment_pks)
        .values("object_id", "reaction_type")
        .annotate(count=Count("id"))
    )
    counts_map = {}
    for row in rows:
        counts_map.setdefault(row["object_id"], {})[row["reaction_type"]] = row["count"]

    # User's own reactions
    user_reactions_map = {}
    if request.user.is_authenticated:
        user_rows = CommentReaction.objects.filter(
            content_type=ct, object_id__in=comment_pks, user=request.user
        ).values_list("object_id", "reaction_type")
        for obj_id, rtype in user_rows:
            user_reactions_map[obj_id] = rtype

    result = {}
    for pk in comment_pks:
        result[pk] = {
            "content_type_id": ct.pk,
            "target_id": pk,
            "counts": counts_map.get(pk, {}),
            "user_reaction": user_reactions_map.get(pk),
        }
    return result
