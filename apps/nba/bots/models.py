from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.bots.models import AbstractBotComment, AbstractBotProfile


class BotProfile(AbstractBotProfile):
    """NBA bot profile with basketball-specific strategy types."""

    class StrategyType(models.TextChoices):
        FRONTRUNNER = "frontrunner", _("Frontrunner")
        UNDERDOG = "underdog", _("Underdog")
        SPREAD_SHARK = "spread_shark", _("Spread Shark")
        PARLAY = "parlay", _("Parlay")
        TOTAL_GURU = "total_guru", _("Total Guru")
        CHAOS_AGENT = "chaos_agent", _("Chaos Agent")
        ALL_IN_ALICE = "all_in_alice", _("All-In Alice")
        HOMER = "homer", _("Homer (team-loyal)")

    strategy_type = models.CharField(
        _("strategy type"),
        max_length=30,
        choices=StrategyType.choices,
    )
    favorite_team = models.ForeignKey(
        "games.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homer_bots",
        help_text=_("Only for homer bots."),
    )

    def __str__(self):
        return f"{self.user.display_name} ({self.get_strategy_type_display()})"


class BotComment(AbstractBotComment):
    """NBA bot comment linked to a Game."""

    game = models.ForeignKey(
        "games.Game",
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
