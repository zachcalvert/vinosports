from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel


class ChallengeTemplate(BaseModel):
    """Reusable blueprint for a challenge, rotated to avoid repetition."""

    class ChallengeType(models.TextChoices):
        DAILY = "DAILY", _("Daily")
        WEEKLY = "WEEKLY", _("Weekly")
        SPECIAL = "SPECIAL", _("Special Event")

    class CriteriaType(models.TextChoices):
        BET_COUNT = "BET_COUNT", _("Place N bets")
        BET_ON_UNDERDOG = "BET_ON_UNDERDOG", _("Bet on underdog")
        WIN_COUNT = "WIN_COUNT", _("Win N bets")
        WIN_STREAK = "WIN_STREAK", _("Win N in a row")
        PARLAY_PLACED = "PARLAY_PLACED", _("Place a parlay")
        PARLAY_WON = "PARLAY_WON", _("Win a parlay")
        TOTAL_STAKED = "TOTAL_STAKED", _("Stake N+ credits")
        BET_ALL_MATCHES = "BET_ALL_MATCHES", _("Bet on every match")
        CORRECT_PREDICTIONS = "CORRECT_PREDICTIONS", _("Predict N+ correct")

    slug = models.SlugField(max_length=50, unique=True)
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=500)
    icon = models.CharField(max_length=50, help_text=_("Phosphor icon name"))
    challenge_type = models.CharField(max_length=10, choices=ChallengeType.choices)
    criteria_type = models.CharField(max_length=25, choices=CriteriaType.choices)
    criteria_params = models.JSONField(
        default=dict,
        help_text=_('e.g. {"target": 3, "odds_min": "3.00"}'),
    )
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2)
    badge = models.ForeignKey(
        "betting.Badge",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text=_("Optional badge awarded on completion"),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["challenge_type", "title"]

    def __str__(self):
        return f"{self.title} ({self.get_challenge_type_display()})"


class Challenge(BaseModel):
    """A time-bound instance of a template, same for all users."""

    class Status(models.TextChoices):
        UPCOMING = "UPCOMING", _("Upcoming")
        ACTIVE = "ACTIVE", _("Active")
        EXPIRED = "EXPIRED", _("Expired")

    template = models.ForeignKey(
        ChallengeTemplate, on_delete=models.CASCADE, related_name="instances"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.UPCOMING
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    matchday = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-starts_at"]
        indexes = [
            models.Index(fields=["status", "starts_at"]),
        ]

    def __str__(self):
        return f"{self.template.title} ({self.get_status_display()})"

    @property
    def target(self):
        return self.template.criteria_params.get("target", 1)


class UserChallenge(BaseModel):
    """Per-user progress tracking for a challenge."""

    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", _("In Progress")
        COMPLETED = "COMPLETED", _("Completed")
        FAILED = "FAILED", _("Failed")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_challenges",
    )
    challenge = models.ForeignKey(
        Challenge, on_delete=models.CASCADE, related_name="user_challenges"
    )
    progress = models.IntegerField(default=0)
    target = models.IntegerField(
        help_text=_("Denormalized from challenge criteria for display")
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    reward_credited = models.BooleanField(default=False)

    class Meta:
        unique_together = [("user", "challenge")]
        ordering = ["-challenge__starts_at"]

    def __str__(self):
        return (
            f"{self.user} — {self.challenge.template.title} "
            f"({self.progress}/{self.target})"
        )

    @property
    def progress_percent(self):
        if self.target <= 0:
            return 0
        return min(int((self.progress / self.target) * 100), 100)
