from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel


class ReactionType(models.TextChoices):
    THUMBS_UP = "thumbs_up", _("👍")
    THUMBS_DOWN = "thumbs_down", _("👎")
    PARTY_CUP = "party_cup", _("🥤")


class AbstractReaction(BaseModel):
    """Base reaction — concrete subclasses add the target FK."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_reactions",
        verbose_name=_("user"),
    )
    reaction_type = models.CharField(
        _("reaction type"),
        max_length=20,
        choices=ReactionType.choices,
    )

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.user} → {self.get_reaction_type_display()}"


class CommentReaction(AbstractReaction):
    """Reaction on a comment. Uses GenericForeignKey to support all league Comment models."""

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("content type"),
    )
    object_id = models.PositiveBigIntegerField(_("object ID"))
    comment = GenericForeignKey("content_type", "object_id")

    class Meta:
        verbose_name = _("comment reaction")
        verbose_name_plural = _("comment reactions")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content_type", "object_id"],
                name="unique_comment_reaction",
            ),
        ]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]


class ArticleReaction(AbstractReaction):
    """Reaction on a NewsArticle."""

    article = models.ForeignKey(
        "news.NewsArticle",
        on_delete=models.CASCADE,
        related_name="reactions",
        verbose_name=_("article"),
    )

    class Meta:
        verbose_name = _("article reaction")
        verbose_name_plural = _("article reactions")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "article"],
                name="unique_article_reaction",
            ),
        ]
