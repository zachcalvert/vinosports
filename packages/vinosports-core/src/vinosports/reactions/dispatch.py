"""Helpers for dispatching bot reactions from view code."""

import logging

from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)


def dispatch_comment_reactions(comment):
    """Dispatch bot reactions for a newly created comment.

    Safe to call from views — broker failures are caught and logged.
    """
    try:
        from vinosports.bots.tasks import dispatch_bot_comment_reactions

        ct = ContentType.objects.get_for_model(comment)
        dispatch_bot_comment_reactions.delay(ct.pk, comment.pk, comment.user_id)
    except Exception:
        logger.warning("Failed to dispatch bot comment reactions", exc_info=True)


def dispatch_pile_on_downvotes(content_type_id, object_id, author_user_id):
    """Dispatch bots to pile on with thumbs_down after a human downvotes.

    Safe to call from views — broker failures are caught and logged.
    """
    try:
        from vinosports.bots.tasks import dispatch_bot_pile_on_downvotes

        dispatch_bot_pile_on_downvotes.delay(content_type_id, object_id, author_user_id)
    except Exception:
        logger.warning("Failed to dispatch pile-on downvotes", exc_info=True)


def dispatch_article_reactions(article):
    """Dispatch bot reactions for a newly published article.

    Safe to call from views/tasks — broker failures are caught and logged.
    """
    try:
        from vinosports.bots.tasks import dispatch_bot_article_reactions

        author_id = article.author_id if article.author_id else None
        dispatch_bot_article_reactions.delay(article.pk, author_id)
    except Exception:
        logger.warning("Failed to dispatch bot article reactions", exc_info=True)
