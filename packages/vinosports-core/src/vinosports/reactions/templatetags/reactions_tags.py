from django import template
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from django.urls import reverse

from vinosports.reactions.models import ArticleReaction, CommentReaction, ReactionType

register = template.Library()

REACTION_CHOICES = [(r.value, r.label) for r in ReactionType]


@register.filter
def get_item(dictionary, key):
    """Look up a dictionary value by key in a template."""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.simple_tag
def reaction_url(target_type, content_type_id, target_id, reaction_type):
    """Build the toggle URL for a reaction."""
    if target_type == "comment":
        return reverse(
            "reactions:toggle_comment",
            args=[content_type_id, target_id, reaction_type],
        )
    return reverse(
        "reactions:toggle_article",
        args=[target_id, reaction_type],
    )


@register.inclusion_tag("reactions/partials/reaction_buttons.html", takes_context=True)
def render_reactions(
    context, target_type, content_type_id, target_id, counts, user_reaction
):
    """Render reaction buttons for a comment or article."""
    return {
        "target_type": target_type,
        "content_type_id": content_type_id,
        "target_id": target_id,
        "counts": counts,
        "user_reaction": user_reaction,
        "reaction_choices": REACTION_CHOICES,
        "user": context.get("user"),
    }


@register.inclusion_tag("reactions/partials/reaction_buttons.html", takes_context=True)
def comment_reactions(context, comment):
    """Self-contained reaction buttons for a comment. Fetches data inline."""
    ct = ContentType.objects.get_for_model(comment)
    counts = dict(
        CommentReaction.objects.filter(content_type=ct, object_id=comment.pk)
        .values_list("reaction_type")
        .annotate(count=Count("id"))
    )
    user = context.get("user")
    user_reaction = None
    if user and user.is_authenticated:
        user_reaction = (
            CommentReaction.objects.filter(
                content_type=ct, object_id=comment.pk, user=user
            )
            .values_list("reaction_type", flat=True)
            .first()
        )
    return {
        "target_type": "comment",
        "content_type_id": ct.pk,
        "target_id": comment.pk,
        "counts": counts,
        "user_reaction": user_reaction,
        "reaction_choices": REACTION_CHOICES,
        "user": user,
    }


@register.inclusion_tag("reactions/partials/reaction_buttons.html", takes_context=True)
def article_reactions(context, article):
    """Self-contained reaction buttons for a news article. Fetches data inline."""
    counts = dict(
        ArticleReaction.objects.filter(article=article)
        .values_list("reaction_type")
        .annotate(count=Count("id"))
    )
    user = context.get("user")
    user_reaction = None
    if user and user.is_authenticated:
        user_reaction = (
            ArticleReaction.objects.filter(article=article, user=user)
            .values_list("reaction_type", flat=True)
            .first()
        )
    return {
        "target_type": "article",
        "content_type_id": None,
        "target_id": article.id_hash,
        "counts": counts,
        "user_reaction": user_reaction,
        "reaction_choices": REACTION_CHOICES,
        "user": user,
    }
