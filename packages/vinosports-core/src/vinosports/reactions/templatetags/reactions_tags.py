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


@register.filter
def join_names(names):
    """Join a list of names into a comma-separated string for tooltips."""
    if not names:
        return ""
    return ", ".join(names)


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


def _build_reactors(qs):
    """Build a dict of reaction_type -> [display_name, ...] from a queryset."""
    reactors = {}
    for rtype, name in qs.values_list("reaction_type", "user__display_name"):
        reactors.setdefault(rtype, []).append(name)
    return reactors


@register.inclusion_tag("reactions/partials/reaction_buttons.html", takes_context=True)
def comment_reactions(context, comment):
    """Self-contained reaction buttons for a comment. Fetches data inline."""
    ct = ContentType.objects.get_for_model(comment)
    qs = CommentReaction.objects.filter(content_type=ct, object_id=comment.pk)
    counts = dict(qs.values_list("reaction_type").annotate(count=Count("id")))
    reactors = _build_reactors(qs)
    user = context.get("user")
    user_reaction = None
    if user and user.is_authenticated:
        user_reaction = (
            qs.filter(user=user).values_list("reaction_type", flat=True).first()
        )
    return {
        "target_type": "comment",
        "content_type_id": ct.pk,
        "target_id": comment.pk,
        "counts": counts,
        "reactors": reactors,
        "user_reaction": user_reaction,
        "reaction_choices": REACTION_CHOICES,
        "user": user,
    }


@register.inclusion_tag("reactions/partials/reaction_buttons.html", takes_context=True)
def article_reactions(context, article):
    """Self-contained reaction buttons for a news article. Fetches data inline."""
    qs = ArticleReaction.objects.filter(article=article)
    counts = dict(qs.values_list("reaction_type").annotate(count=Count("id")))
    reactors = _build_reactors(qs)
    user = context.get("user")
    user_reaction = None
    if user and user.is_authenticated:
        user_reaction = (
            qs.filter(user=user).values_list("reaction_type", flat=True).first()
        )
    return {
        "target_type": "article",
        "content_type_id": None,
        "target_id": article.id_hash,
        "counts": counts,
        "reactors": reactors,
        "user_reaction": user_reaction,
        "reaction_choices": REACTION_CHOICES,
        "user": user,
    }
