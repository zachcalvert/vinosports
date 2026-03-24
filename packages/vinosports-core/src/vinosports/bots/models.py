from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel

# ---------------------------------------------------------------------------
# Abstract base classes (still used by league BotComment models)
# ---------------------------------------------------------------------------


class AbstractBotProfile(BaseModel):
    """Abstract bot profile — persona, avatar, and activation state.

    Kept for backwards compatibility. The concrete BotProfile below is the
    canonical model used by all league apps.
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
            "Personality-only system prompt sent to the LLM. "
            "Do NOT include team references — team context is injected at runtime."
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


# ---------------------------------------------------------------------------
# Concrete models — global, shared across all leagues
# ---------------------------------------------------------------------------


class StrategyType(models.TextChoices):
    """Unified betting strategy types across all leagues."""

    FRONTRUNNER = "frontrunner", _("Frontrunner")
    UNDERDOG = "underdog", _("Underdog")
    SPREAD_SHARK = "spread_shark", _("Spread Shark")
    PARLAY = "parlay", _("Parlay")
    TOTAL_GURU = "total_guru", _("Total Guru")
    DRAW_SPECIALIST = "draw_specialist", _("Draw Specialist")
    VALUE_HUNTER = "value_hunter", _("Value Hunter")
    CHAOS_AGENT = "chaos_agent", _("Chaos Agent")
    ALL_IN_ALICE = "all_in_alice", _("All-In Alice")
    HOMER = "homer", _("Homer")
    ANTI_HOMER = "anti_homer", _("Anti-Homer")


class ScheduleTemplate(AbstractScheduleTemplate):
    """Global schedule template — shared across all leagues."""

    class Meta(AbstractScheduleTemplate.Meta):
        abstract = False


class BotProfile(AbstractBotProfile):
    """Global bot profile — one per bot, active across leagues.

    Persona prompts describe personality only. Team context is injected
    at comment-generation time by each league's tasks, reading from the
    team abbreviation fields below.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bot_profile",
        limit_choices_to={"is_bot": True},
        verbose_name=_("bot user"),
    )

    # --- Betting behaviour (cross-league) ---
    strategy_type = models.CharField(
        _("strategy type"),
        max_length=30,
        choices=StrategyType.choices,
    )
    risk_multiplier = models.FloatField(
        _("risk multiplier"),
        default=1.0,
        help_text=_("Multiplier applied to base stake percentage."),
    )
    max_daily_bets = models.PositiveIntegerField(
        _("max daily bets"),
        default=5,
        help_text=_("Maximum bets this bot can place per day across all leagues."),
    )
    schedule_template = models.ForeignKey(
        ScheduleTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bots",
        verbose_name=_("schedule template"),
    )

    # --- League activation flags ---
    active_in_epl = models.BooleanField(_("active in EPL"), default=True)
    active_in_nba = models.BooleanField(_("active in NBA"), default=True)
    active_in_nfl = models.BooleanField(_("active in NFL"), default=False)

    # --- League-specific team affiliations (CharFields, no cross-app FKs) ---
    epl_team_tla = models.CharField(
        _("EPL team TLA"),
        max_length=5,
        blank=True,
        help_text=_("Three-letter abbreviation of favourite EPL team (e.g. CHE, ARS)."),
    )
    nba_team_abbr = models.CharField(
        _("NBA team abbreviation"),
        max_length=5,
        blank=True,
        help_text=_("Abbreviation of favourite NBA team (e.g. GSW, OKC)."),
    )

    class Meta(AbstractBotProfile.Meta):
        abstract = False

    def __str__(self):
        return f"{self.user.display_name} ({self.get_strategy_type_display()})"
