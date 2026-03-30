from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from vinosports.core.models import BaseModel


class Conference(models.TextChoices):
    AFC = "AFC", "AFC"
    NFC = "NFC", "NFC"


class Division(models.TextChoices):
    AFC_EAST = "AFC_EAST", "AFC East"
    AFC_NORTH = "AFC_NORTH", "AFC North"
    AFC_SOUTH = "AFC_SOUTH", "AFC South"
    AFC_WEST = "AFC_WEST", "AFC West"
    NFC_EAST = "NFC_EAST", "NFC East"
    NFC_NORTH = "NFC_NORTH", "NFC North"
    NFC_SOUTH = "NFC_SOUTH", "NFC South"
    NFC_WEST = "NFC_WEST", "NFC West"


# Map BDL's (conference, division) pairs to our Division enum.
# BDL returns conference="AFC"/"NFC" and division="EAST"/"NORTH"/etc.
DIVISION_MAP = {
    ("AFC", "EAST"): Division.AFC_EAST,
    ("AFC", "NORTH"): Division.AFC_NORTH,
    ("AFC", "SOUTH"): Division.AFC_SOUTH,
    ("AFC", "WEST"): Division.AFC_WEST,
    ("NFC", "EAST"): Division.NFC_EAST,
    ("NFC", "NORTH"): Division.NFC_NORTH,
    ("NFC", "SOUTH"): Division.NFC_SOUTH,
    ("NFC", "WEST"): Division.NFC_WEST,
}


class GameStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    HALFTIME = "HALFTIME", "Halftime"
    FINAL = "FINAL", "Final"
    FINAL_OT = "FINAL_OT", "Final (OT)"
    POSTPONED = "POSTPONED", "Postponed"
    CANCELLED = "CANCELLED", "Cancelled"


class Team(BaseModel):
    external_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=100)  # "Kansas City Chiefs"
    short_name = models.CharField(max_length=100)  # "Chiefs"
    abbreviation = models.CharField(max_length=5)  # "KC"
    location = models.CharField(max_length=100, blank=True)  # "Kansas City"
    logo_url = models.URLField(blank=True)
    conference = models.CharField(max_length=3, choices=Conference.choices)
    division = models.CharField(max_length=10, choices=Division.choices)

    class Meta:
        ordering = ["short_name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse(
            "nfl_games:team_detail",
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
    kickoff = models.DateTimeField(null=True, blank=True)
    season = models.IntegerField()
    week = models.IntegerField(null=True, blank=True)
    postseason = models.BooleanField(default=False)
    venue = models.CharField(max_length=200, blank=True)

    # Quarter-by-quarter scores
    home_q1 = models.SmallIntegerField(null=True, blank=True)
    home_q2 = models.SmallIntegerField(null=True, blank=True)
    home_q3 = models.SmallIntegerField(null=True, blank=True)
    home_q4 = models.SmallIntegerField(null=True, blank=True)
    home_ot = models.SmallIntegerField(null=True, blank=True)
    away_q1 = models.SmallIntegerField(null=True, blank=True)
    away_q2 = models.SmallIntegerField(null=True, blank=True)
    away_q3 = models.SmallIntegerField(null=True, blank=True)
    away_q4 = models.SmallIntegerField(null=True, blank=True)
    away_ot = models.SmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-game_date", "-kickoff"]

    def __str__(self):
        return f"{self.away_team.abbreviation} @ {self.home_team.abbreviation} (Wk {self.week}, {self.game_date})"

    def get_absolute_url(self):
        return reverse("nfl_games:game_detail", kwargs={"id_hash": self.id_hash})

    @property
    def is_live(self):
        return self.status in (GameStatus.IN_PROGRESS, GameStatus.HALFTIME)

    @property
    def is_final(self):
        return self.status in (GameStatus.FINAL, GameStatus.FINAL_OT)

    @property
    def winner(self):
        if not self.is_final or self.home_score is None or self.away_score is None:
            return None
        if self.home_score == self.away_score:
            return None  # NFL ties are possible
        return self.home_team if self.home_score > self.away_score else self.away_team

    @property
    def is_tie(self):
        if not self.is_final or self.home_score is None or self.away_score is None:
            return False
        return self.home_score == self.away_score


class Standing(BaseModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="standings")
    season = models.IntegerField()
    conference = models.CharField(max_length=3, choices=Conference.choices)
    division = models.CharField(max_length=10, choices=Division.choices)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    ties = models.IntegerField(default=0)
    win_pct = models.FloatField(default=0.0)
    division_wins = models.IntegerField(default=0)
    division_losses = models.IntegerField(default=0)
    conference_wins = models.IntegerField(default=0)
    conference_losses = models.IntegerField(default=0)
    points_for = models.IntegerField(default=0)
    points_against = models.IntegerField(default=0)
    streak = models.CharField(max_length=10, blank=True)
    division_rank = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = [("team", "season")]
        ordering = ["division", "division_rank"]

    def __str__(self):
        return f"{self.team.abbreviation} {self.season} ({self.wins}-{self.losses}-{self.ties})"

    @property
    def point_differential(self):
        return self.points_for - self.points_against


class GameStats(BaseModel):
    game = models.OneToOneField(Game, on_delete=models.CASCADE, related_name="stats")
    h2h = models.JSONField(default=dict, blank=True)
    form = models.JSONField(default=dict, blank=True)
    injuries = models.JSONField(default=dict, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Stats for {self.game}"


class Player(BaseModel):
    external_id = models.IntegerField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    position = models.CharField(
        max_length=30, blank=True
    )  # "Quarterback", "Wide Receiver"
    position_abbreviation = models.CharField(max_length=10, blank=True)  # "QB", "WR"
    height = models.CharField(max_length=10, blank=True)
    weight = models.PositiveSmallIntegerField(null=True, blank=True)
    jersey_number = models.CharField(max_length=20, blank=True)
    college = models.CharField(max_length=100, blank=True)
    experience = models.PositiveSmallIntegerField(null=True, blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="players",
    )
    is_active = models.BooleanField(default=False)

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
        return reverse("nfl_games:player_detail", kwargs={"slug": self.slug})
