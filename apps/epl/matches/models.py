from datetime import timedelta

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel


class Team(BaseModel):
    external_id = models.IntegerField(_("external ID"), unique=True)
    name = models.CharField(_("name"), max_length=100)
    short_name = models.CharField(_("short name"), max_length=50, blank=True)
    tla = models.CharField(_("TLA"), max_length=3, blank=True)
    crest_url = models.URLField(_("crest URL"), blank=True)
    venue = models.CharField(_("venue"), max_length=200, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Match(BaseModel):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", _("Scheduled")
        TIMED = "TIMED", _("Timed")
        IN_PLAY = "IN_PLAY", _("In Play")
        PAUSED = "PAUSED", _("Paused")
        FINISHED = "FINISHED", _("Finished")
        POSTPONED = "POSTPONED", _("Postponed")
        CANCELLED = "CANCELLED", _("Cancelled")

    external_id = models.IntegerField(_("external ID"), unique=True)
    home_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="home_matches",
        verbose_name=_("home team"),
    )
    away_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="away_matches",
        verbose_name=_("away team"),
    )
    home_score = models.IntegerField(_("home score"), null=True, blank=True)
    away_score = models.IntegerField(_("away score"), null=True, blank=True)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    matchday = models.IntegerField(_("matchday"))
    kickoff = models.DateTimeField(_("kickoff"))
    season = models.CharField(_("season"), max_length=10, help_text=_("e.g. 2025"))
    slug = models.SlugField(_("slug"), max_length=50, unique=True, blank=True)

    class Meta:
        ordering = ["kickoff"]
        verbose_name_plural = "matches"

    def __str__(self):
        score = f" {self.home_score}-{self.away_score}" if self.home_score is not None else ""
        return f"{self.home_team.short_name or self.home_team.name} vs {self.away_team.short_name or self.away_team.name}{score}"

    def generate_slug(self):
        home = slugify(self.home_team.tla or self.home_team.short_name or "xxx")
        away = slugify(self.away_team.tla or self.away_team.short_name or "xxx")
        kickoff = self.kickoff
        if isinstance(kickoff, str):
            from django.utils.dateparse import parse_datetime
            kickoff = parse_datetime(kickoff) or kickoff
        date_str = kickoff.strftime("%Y-%m-%d") if hasattr(kickoff, "strftime") else kickoff[:10]
        base = f"{home}-{away}-{date_str}"
        slug = base
        counter = 2
        while Match.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.generate_slug()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("matches:match_detail", kwargs={"slug": self.slug})


class Standing(BaseModel):
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="standings",
        verbose_name=_("team"),
    )
    season = models.CharField(_("season"), max_length=10)
    position = models.IntegerField(_("position"))
    played = models.IntegerField(_("played"), default=0)
    won = models.IntegerField(_("won"), default=0)
    drawn = models.IntegerField(_("drawn"), default=0)
    lost = models.IntegerField(_("lost"), default=0)
    goals_for = models.IntegerField(_("goals for"), default=0)
    goals_against = models.IntegerField(_("goals against"), default=0)
    goal_difference = models.IntegerField(_("goal difference"), default=0)
    points = models.IntegerField(_("points"), default=0)

    class Meta:
        ordering = ["position"]
        unique_together = [("team", "season")]

    def __str__(self):
        return f"{self.position}. {self.team.name} ({self.points} pts)"


class MatchStats(models.Model):
    """Cached hype data: H2H history and recent form for each team."""

    match = models.OneToOneField(
        Match,
        on_delete=models.CASCADE,
        related_name="hype_stats",
        verbose_name=_("match"),
    )
    h2h_json = models.JSONField(_("H2H matches"), default=list)
    h2h_summary_json = models.JSONField(_("H2H summary"), default=dict)
    home_form_json = models.JSONField(_("home team form"), default=list)
    away_form_json = models.JSONField(_("away team form"), default=list)
    fetched_at = models.DateTimeField(_("fetched at"), null=True, blank=True)
    last_attempt_at = models.DateTimeField(_("last attempt at"), null=True, blank=True)

    class Meta:
        verbose_name = "match stats"
        verbose_name_plural = "match stats"

    def __str__(self):
        return f"Stats for {self.match}"

    def is_stale(self):
        if not self.fetched_at:
            if self.last_attempt_at:
                return (timezone.now() - self.last_attempt_at) > timedelta(minutes=15)
            return True
        return (timezone.now() - self.fetched_at) > timedelta(hours=24)


class MatchNotes(BaseModel):
    """Admin-authored match notes injected into bot comment prompts."""

    match = models.OneToOneField(
        Match,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name=_("match"),
    )
    body = models.TextField(
        _("notes"),
        blank=True,
        help_text=_("Free-form match observations for bot context"),
    )

    class Meta:
        verbose_name = "match notes"
        verbose_name_plural = "match notes"

    def __str__(self):
        return f"Notes for {self.match}"


class Odds(BaseModel):
    """EPL 1X2 odds (home win / draw / away win) in decimal format."""

    match = models.ForeignKey(
        Match,
        on_delete=models.CASCADE,
        related_name="odds",
        verbose_name=_("match"),
    )
    bookmaker = models.CharField(_("bookmaker"), max_length=100)
    home_win = models.DecimalField(_("home win"), max_digits=6, decimal_places=2)
    draw = models.DecimalField(_("draw"), max_digits=6, decimal_places=2)
    away_win = models.DecimalField(_("away win"), max_digits=6, decimal_places=2)
    fetched_at = models.DateTimeField(_("fetched at"))

    class Meta:
        ordering = ["-fetched_at"]
        unique_together = [("match", "bookmaker")]
        verbose_name_plural = "odds"

    def __str__(self):
        return f"{self.bookmaker}: {self.match} ({self.home_win}/{self.draw}/{self.away_win})"
