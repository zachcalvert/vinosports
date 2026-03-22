from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.discussions.models import AbstractComment


class Comment(AbstractComment):
    """EPL match comment."""

    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name=_("match"),
    )

    class Meta(AbstractComment.Meta):
        indexes = [
            models.Index(fields=["match", "created_at"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return f"{self.user} on {self.match} ({self.id_hash})"
