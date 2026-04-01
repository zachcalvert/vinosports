from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel


class Conference(models.TextChoices):
    EAST = "EAST", "Eastern"
    WEST = "WEST", "Western"


class GameStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    HALFTIME = "HALFTIME", "Halftime"
    FINAL = "FINAL", "Final"
    POSTPONED = "POSTPONED", "Postponed"
    CANCELLED = "CANCELLED", "Cancelled"


class Team(BaseModel):
    external_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=5)
    logo_url = models.URLField(blank=True)
    team_logo = models.ImageField(upload_to="nba/logos/", blank=True)
    conference = models.CharField(max_length=4, choices=Conference.choices)
    division = models.CharField(max_length=50)

    class Meta:
        ordering = ["short_name"]

    def __str__(self):
        return self.short_name

    @property
    def logo(self):
        """Return the best available logo: uploaded image first, then URL."""
        if self.team_logo:
            return self.team_logo.url
        return self.logo_url

    def get_absolute_url(self):
        return reverse(
            "nba_games:team_detail",
            kwargs={"abbreviation": self.abbreviation.lower()},
        )


class Game(BaseModel):
    external_id = models.IntegerField(unique=True)
    home_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="home_games"
    )
    away_team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="away_games"
    )
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=GameStatus.choices, default=GameStatus.SCHEDULED
    )
    game_date = models.DateField()
    tip_off = models.DateTimeField(null=True, blank=True)
    season = models.IntegerField()
    arena = models.CharField(max_length=200, blank=True)
    postseason = models.BooleanField(default=False)

    class Meta:
        ordering = ["-game_date", "-tip_off"]

    def __str__(self):
        return f"{self.away_team.abbreviation} @ {self.home_team.abbreviation} ({self.game_date})"

    def get_absolute_url(self):
        return reverse("nba_games:game_detail", kwargs={"id_hash": self.id_hash})

    @property
    def is_live(self):
        return self.status in (GameStatus.IN_PROGRESS, GameStatus.HALFTIME)

    @property
    def is_final(self):
        return self.status == GameStatus.FINAL

    @property
    def winner(self):
        if not self.is_final or self.home_score is None or self.away_score is None:
            return None
        return self.home_team if self.home_score > self.away_score else self.away_team


class Standing(BaseModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="standings")
    season = models.IntegerField()
    conference = models.CharField(max_length=4, choices=Conference.choices)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    win_pct = models.FloatField(default=0.0)
    games_behind = models.FloatField(default=0.0)
    streak = models.CharField(max_length=10, blank=True)
    home_record = models.CharField(max_length=10, blank=True)
    away_record = models.CharField(max_length=10, blank=True)
    conference_rank = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = [("team", "season")]
        ordering = ["conference", "conference_rank"]

    def __str__(self):
        return f"{self.team.abbreviation} {self.season} ({self.wins}-{self.losses})"


class GameStats(BaseModel):
    game = models.OneToOneField(Game, on_delete=models.CASCADE, related_name="stats")
    h2h = models.JSONField(default=dict, blank=True)
    form = models.JSONField(default=dict, blank=True)
    injuries = models.JSONField(default=dict, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Stats for {self.game}"


class Player(BaseModel):
    """NBA player — synced from BallDontLie /players endpoint."""

    external_id = models.IntegerField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    position = models.CharField(max_length=10, blank=True)
    height = models.CharField(max_length=10, blank=True)  # "6-9"
    weight = models.PositiveSmallIntegerField(null=True, blank=True)  # pounds
    jersey_number = models.CharField(max_length=20, blank=True)
    college = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    draft_year = models.PositiveSmallIntegerField(null=True, blank=True)
    draft_round = models.PositiveSmallIntegerField(null=True, blank=True)
    draft_number = models.PositiveSmallIntegerField(null=True, blank=True)
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="players",
    )
    is_active = models.BooleanField(default=False)
    headshot_url = models.URLField(blank=True)  # NBA CDN

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def slug(self):
        name_part = slugify(f"{self.first_name} {self.last_name}") or "player"
        return f"{name_part}-{self.id_hash}"

    def get_absolute_url(self):
        return reverse("nba_games:player_detail", kwargs={"slug": self.slug})


class PlayerBoxScore(BaseModel):
    """Per-player stats for a single game (box score line)."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="box_scores")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="box_scores")
    player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="box_scores",
    )

    # Player identity (denormalized — kept for backwards compatibility)
    player_external_id = models.IntegerField()
    player_name = models.CharField(max_length=100)
    player_position = models.CharField(max_length=10, blank=True)

    # Stats
    minutes = models.CharField(max_length=10, blank=True)
    points = models.SmallIntegerField(default=0)
    fgm = models.SmallIntegerField(default=0)
    fga = models.SmallIntegerField(default=0)
    fg3m = models.SmallIntegerField(default=0)
    fg3a = models.SmallIntegerField(default=0)
    ftm = models.SmallIntegerField(default=0)
    fta = models.SmallIntegerField(default=0)
    oreb = models.SmallIntegerField(default=0)
    dreb = models.SmallIntegerField(default=0)
    reb = models.SmallIntegerField(default=0)
    ast = models.SmallIntegerField(default=0)
    stl = models.SmallIntegerField(default=0)
    blk = models.SmallIntegerField(default=0)
    turnovers = models.SmallIntegerField(default=0)
    pf = models.SmallIntegerField(default=0)
    plus_minus = models.SmallIntegerField(default=0)
    starter = models.BooleanField(default=False)

    class Meta:
        unique_together = [("game", "player_external_id")]
        ordering = ["-starter", "-points"]

    def __str__(self):
        return f"{self.player_name} — {self.points}pts ({self.game})"


class Odds(BaseModel):
    """NBA odds — moneyline, spread, and totals in American format."""

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="odds",
        verbose_name=_("game"),
    )
    bookmaker = models.CharField(_("bookmaker"), max_length=100)
    home_moneyline = models.IntegerField(_("home moneyline"), null=True, blank=True)
    away_moneyline = models.IntegerField(_("away moneyline"), null=True, blank=True)
    spread_line = models.FloatField(_("spread line"), null=True, blank=True)
    spread_home = models.IntegerField(_("spread home odds"), null=True, blank=True)
    spread_away = models.IntegerField(_("spread away odds"), null=True, blank=True)
    total_line = models.FloatField(_("total line"), null=True, blank=True)
    over_odds = models.IntegerField(_("over odds"), null=True, blank=True)
    under_odds = models.IntegerField(_("under odds"), null=True, blank=True)
    fetched_at = models.DateTimeField(_("fetched at"))

    class Meta:
        ordering = ["-fetched_at"]
        unique_together = [("game", "bookmaker")]
        verbose_name_plural = "odds"

    def __str__(self):
        return f"{self.bookmaker}: {self.game}"
