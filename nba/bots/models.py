from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.bots.models import AbstractBotComment


class BotComment(AbstractBotComment):
    """NBA bot comment linked to a Game."""

    game = models.ForeignKey(
        "nba_games.Game",
        on_delete=models.CASCADE,
        related_name="bot_comments",
        verbose_name=_("game"),
    )
    comment = models.OneToOneField(
        "nba_discussions.Comment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_comment_meta",
        verbose_name=_("posted comment"),
    )
    parent_comment = models.ForeignKey(
        "nba_discussions.Comment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_replies",
        verbose_name=_("replied to"),
    )

    class Meta(AbstractBotComment.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game", "trigger_type"],
                name="unique_nba_bot_comment_per_trigger",
            ),
        ]
        indexes = [
            models.Index(fields=["game", "trigger_type"]),
        ]

    def __str__(self):
        return f"{self.user.display_name} | {self.trigger_type} | {self.game}"
