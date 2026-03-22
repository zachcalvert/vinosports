from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.bots.models import AbstractBotComment, AbstractBotProfile


class BotProfile(AbstractBotProfile):
    """EPL bot profile with football-specific strategy types."""

    class StrategyType(models.TextChoices):
        FRONTRUNNER = "frontrunner", _("Frontrunner")
        UNDERDOG = "underdog", _("Underdog")
        PARLAY = "parlay", _("Parlay")
        DRAW_SPECIALIST = "draw_specialist", _("Draw Specialist")
        VALUE_HUNTER = "value_hunter", _("Value Hunter")
        CHAOS_AGENT = "chaos_agent", _("Chaos Agent")
        ALL_IN_ALICE = "all_in_alice", _("All-In Alice")
        HOMER = "homer", _("Homer (team-loyal)")

    strategy_type = models.CharField(
        _("strategy type"),
        max_length=30,
        choices=StrategyType.choices,
    )
    team_tla = models.CharField(
        _("team TLA"),
        max_length=5,
        blank=True,
        help_text=_("Only for homer bots. Must match a Team.tla value."),
    )

    def __str__(self):
        return f"{self.user.display_name} ({self.get_strategy_type_display()})"


class BotComment(AbstractBotComment):
    """EPL bot comment linked to a Match."""

    match = models.ForeignKey(
        "matches.Match",
        on_delete=models.CASCADE,
        related_name="bot_comments",
        verbose_name=_("match"),
    )
    comment = models.OneToOneField(
        "epl_discussions.Comment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_comment_meta",
        verbose_name=_("posted comment"),
    )
    parent_comment = models.ForeignKey(
        "epl_discussions.Comment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bot_replies",
        verbose_name=_("replied to"),
    )

    class Meta(AbstractBotComment.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["user", "match", "trigger_type"],
                name="unique_epl_bot_comment_per_trigger",
            ),
        ]
        indexes = [
            models.Index(fields=["match", "trigger_type"]),
        ]

    def __str__(self):
        return f"{self.user.display_name} | {self.trigger_type} | {self.match}"
