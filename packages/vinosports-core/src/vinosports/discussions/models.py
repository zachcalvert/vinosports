from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel


class AbstractComment(BaseModel):
    """Abstract comment model for match/game discussions.

    League projects must add a ForeignKey to their match/game model.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_comments",
        verbose_name=_("user"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name=_("parent comment"),
    )
    body = models.TextField(_("body"), max_length=1000)
    is_deleted = models.BooleanField(_("deleted"), default=False)

    class Meta:
        abstract = True
        ordering = ["created_at"]
