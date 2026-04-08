from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel


class Team(BaseModel):
    external_id = models.IntegerField(_("external ID"), unique=True)
    name = models.CharField(_("name"), max_length=100)
    short_name = models.CharField(_("short name"), max_length=50, blank=True)
    tla = models.CharField(_("TLA"), max_length=5, blank=True)
    crest_url = models.URLField(_("crest URL"), blank=True)
    crest_image = models.ImageField(
        _("crest image"), upload_to="ucl/crests/", blank=True
    )
    country = models.CharField(
        _("country"), max_length=50, blank=True, help_text=_("Country of origin")
    )
    domestic_league = models.CharField(
        _("domestic league"),
        max_length=50,
        blank=True,
        help_text=_("e.g. Premier League, La Liga"),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def crest(self):
        if self.crest_image:
            return self.crest_image.url
        return self.crest_url


class Stage(BaseModel):
    class StageType(models.TextChoices):
        LEAGUE_PHASE = "LEAGUE_PHASE", _("League Phase")
        KNOCKOUT_PLAYOFF = "KNOCKOUT_PLAYOFF", _("Knockout Playoffs")
        ROUND_OF_16 = "ROUND_OF_16", _("Round of 16")
        QUARTER = "QUARTER", _("Quarter-finals")
        SEMI = "SEMI", _("Semi-finals")
        FINAL = "FINAL", _("Final")

    name = models.CharField(_("name"), max_length=50)
    stage_type = models.CharField(
        _("stage type"),
        max_length=20,
        choices=StageType.choices,
        unique=True,
    )
    order = models.IntegerField(
        _("display order"), help_text=_("Lower = earlier in tournament")
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class Match(BaseModel):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", _("Scheduled")
        TIMED = "TIMED", _("Timed")
        IN_PLAY = "IN_PLAY", _("In Play")
        PAUSED = "PAUSED", _("Paused")
        EXTRA_TIME = "EXTRA_TIME", _("Extra Time")
        PENALTY_SHOOTOUT = "PENALTY_SHOOTOUT", _("Penalty Shootout")
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
    stage = models.ForeignKey(
        Stage,
        on_delete=models.CASCADE,
        related_name="matches",
        verbose_name=_("stage"),
    )
    matchday = models.IntegerField(
        _("matchday"),
        null=True,
        blank=True,
        help_text=_("1-8 for league phase, null for knockouts"),
    )
    leg = models.IntegerField(
        _("leg"),
        null=True,
        blank=True,
        help_text=_("1 or 2 for knockout ties, null for league phase and final"),
    )
    tie_id = models.CharField(
        _("tie ID"),
        max_length=20,
        blank=True,
        help_text=_("Links two legs of same knockout tie, e.g. KP-1, R16-3, QF-2"),
    )
    # 90-minute scores
    home_score = models.IntegerField(_("home score"), null=True, blank=True)
    away_score = models.IntegerField(_("away score"), null=True, blank=True)
    # Extra time scores (cumulative, including 90-min) — second leg only
    home_score_et = models.IntegerField(_("home score (ET)"), null=True, blank=True)
    away_score_et = models.IntegerField(_("away score (ET)"), null=True, blank=True)
    # Penalty shootout scores — second leg only
    home_score_penalties = models.IntegerField(
        _("home penalties"), null=True, blank=True
    )
    away_score_penalties = models.IntegerField(
        _("away penalties"), null=True, blank=True
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    kickoff = models.DateTimeField(_("kickoff"))
    venue_name = models.CharField(_("venue"), max_length=200, blank=True)
    venue_city = models.CharField(_("city"), max_length=100, blank=True)
    season = models.CharField(
        _("season"), max_length=10, default="2025", help_text=_("e.g. 2025 for 2025-26")
    )
    slug = models.SlugField(_("slug"), max_length=60, unique=True, blank=True)

    class Meta:
        ordering = ["kickoff"]
        verbose_name_plural = "matches"

    def __str__(self):
        score = (
            f" {self.home_score}-{self.away_score}"
            if self.home_score is not None
            else ""
        )
        return f"{self.home_team.tla or self.home_team.short_name} vs {self.away_team.tla or self.away_team.short_name}{score}"

    @property
    def is_knockout(self):
        return self.stage.stage_type != Stage.StageType.LEAGUE_PHASE

    @property
    def is_second_leg(self):
        return self.leg == 2

    @property
    def winner(self):
        """Return the winning Team, or None if not yet decided."""
        if self.status != self.Status.FINISHED:
            return None
        # Check penalties first (second leg only)
        if (
            self.home_score_penalties is not None
            and self.away_score_penalties is not None
        ):
            if self.home_score_penalties > self.away_score_penalties:
                return self.home_team
            return self.away_team
        # Check extra time (second leg only)
        if self.home_score_et is not None and self.away_score_et is not None:
            if self.home_score_et > self.away_score_et:
                return self.home_team
            if self.away_score_et > self.home_score_et:
                return self.away_team
        # Check 90-minute result
        if self.home_score is not None and self.away_score is not None:
            if self.home_score > self.away_score:
                return self.home_team
            if self.away_score > self.home_score:
                return self.away_team
        return None

    def generate_slug(self):
        home = slugify(self.home_team.tla or self.home_team.short_name or "xxx")
        away = slugify(self.away_team.tla or self.away_team.short_name or "xxx")
        kickoff = self.kickoff
        if isinstance(kickoff, str):
            from django.utils.dateparse import parse_datetime

            kickoff = parse_datetime(kickoff) or kickoff
        date_str = (
            kickoff.strftime("%Y-%m-%d")
            if hasattr(kickoff, "strftime")
            else kickoff[:10]
        )
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
        return reverse("ucl_matches:match_detail", kwargs={"slug": self.slug})


class Standing(BaseModel):
    """League phase standing — single 36-team table (no groups)."""

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
    qualification_note = models.CharField(
        _("qualification note"),
        max_length=100,
        blank=True,
        help_text=_("e.g. Round of 16, Knockout playoffs, Eliminated"),
    )

    class Meta:
        ordering = ["position"]
        unique_together = [("team", "season")]

    def __str__(self):
        return f"{self.position}. {self.team.name} ({self.points} pts)"


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
    """UCL 1X2 odds (home win / draw / away win) in decimal format."""

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
