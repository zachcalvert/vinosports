from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.discussions.models import AbstractComment


class Comment(AbstractComment):
    """NFL game comment."""

    game = models.ForeignKey(
        "nfl_games.Game",
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name=_("game"),
    )

    class Meta(AbstractComment.Meta):
        indexes = [
            models.Index(fields=["game", "created_at"]),
            models.Index(fields=["parent"]),
        ]

    def __str__(self):
        return f"{self.user} on {self.game} ({self.id_hash})"
