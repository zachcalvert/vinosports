from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel


class AbstractBotProfile(BaseModel):
    """Abstract bot profile — persona, avatar, and activation state.

    League projects must add:
    - strategy_type field with sport-specific choices
    - Any sport-specific fields (e.g., team_tla, favorite_team)
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_bot_profile",
        limit_choices_to={"is_bot": True},
        verbose_name=_("bot user"),
    )
    persona_prompt = models.TextField(
        _("persona prompt"),
        help_text=_(
            "Full system prompt sent to the LLM. Edit to tweak personality and voice."
        ),
    )
    avatar_icon = models.CharField(
        _("avatar icon"),
        max_length=30,
        default="robot",
        help_text=_("Lucide icon name."),
    )
    avatar_bg = models.CharField(
        _("avatar background"),
        max_length=10,
        default="#374151",
        help_text=_("Hex colour for the avatar background."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Inactive bots are skipped by all tasks."),
    )

    class Meta:
        abstract = True
        verbose_name = _("bot profile")
        verbose_name_plural = _("bot profiles")


class AbstractScheduleTemplate(BaseModel):
    """Abstract schedule template — defines when a bot is active and what it does.

    The `windows` field is a JSON list of activity windows:
    [
      {
        "days": [0,1,2,3,4,5,6],     # 0=Mon..6=Sun
        "hours": [8, 9, 17, 18],     # hours when bot is "online"
        "bet_probability": 0.4,       # 0.0-1.0 chance of betting per hourly tick
        "comment_probability": 0.7,   # 0.0-1.0 chance of commenting per hourly tick
        "max_bets": 2,                # cap per window activation
        "max_comments": 1             # cap per window activation
      }
    ]
    """

    name = models.CharField(_("name"), max_length=100)
    slug = models.SlugField(_("slug"), unique=True)
    description = models.TextField(_("description"), blank=True)
    windows = models.JSONField(
        _("activity windows"),
        help_text=_(
            "JSON list of activity windows defining schedule and probabilities."
        ),
    )
    active_from = models.DateField(
        _("active from"),
        null=True,
        blank=True,
        help_text=_("Optional start date. Template is inactive before this date."),
    )
    active_to = models.DateField(
        _("active to"),
        null=True,
        blank=True,
        help_text=_("Optional end date. Template is inactive after this date."),
    )

    class Meta:
        abstract = True
        verbose_name = _("schedule template")
        verbose_name_plural = _("schedule templates")

    def __str__(self):
        return self.name


class AbstractBotComment(BaseModel):
    """Abstract bot comment tracker for dedup and debugging.

    League projects must add:
    - A ForeignKey to their match/game model
    - A OneToOneField to their concrete Comment model
    - A ForeignKey to their concrete Comment model for parent_comment
    """

    class TriggerType(models.TextChoices):
        PRE_MATCH = "PRE_MATCH", _("Pre-match hype")
        POST_BET = "POST_BET", _("Post-bet reaction")
        POST_MATCH = "POST_MATCH", _("Post-match reaction")
        REPLY = "REPLY", _("Reply to comment")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_bot_comments",
        limit_choices_to={"is_bot": True},
        verbose_name=_("bot user"),
    )
    trigger_type = models.CharField(
        _("trigger type"),
        max_length=20,
        choices=TriggerType.choices,
    )
    prompt_used = models.TextField(_("prompt used"), blank=True)
    raw_response = models.TextField(_("raw response"), blank=True)
    filtered = models.BooleanField(
        _("filtered out"),
        default=False,
        help_text=_("True if the post-hoc filter rejected this comment."),
    )
    error = models.TextField(_("error"), blank=True)

    class Meta:
        abstract = True
        verbose_name = _("bot comment")
        verbose_name_plural = _("bot comments")
