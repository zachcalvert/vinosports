"""Model factories for NFL tests."""

import factory

from nfl.games.models import (
    Conference,
    Division,
    Game,
    GameStatus,
    Player,
    Standing,
    Team,
)
from nfl.games.services import today_et

# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    external_id = factory.Sequence(lambda n: 100 + n)
    name = factory.Sequence(lambda n: f"City Team{n}")
    short_name = factory.Sequence(lambda n: f"Team{n}")
    abbreviation = factory.Sequence(lambda n: f"T{n:02d}")
    location = factory.Sequence(lambda n: f"City{n}")
    conference = Conference.AFC
    division = Division.AFC_EAST


class PlayerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Player

    external_id = factory.Sequence(lambda n: 50000 + n)
    first_name = factory.Sequence(lambda n: f"First{n}")
    last_name = factory.Sequence(lambda n: f"Last{n}")
    position = "Quarterback"
    position_abbreviation = "QB"
    jersey_number = factory.Sequence(lambda n: str(n % 100))
    college = "Test University"
    team = factory.SubFactory(TeamFactory)
    is_active = True


class GameFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Game

    external_id = factory.Sequence(lambda n: 20250000 + n)
    home_team = factory.SubFactory(TeamFactory)
    away_team = factory.SubFactory(TeamFactory)
    status = GameStatus.SCHEDULED
    game_date = factory.LazyFunction(today_et)
    season = 2025
    week = 1


class StandingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Standing

    team = factory.SubFactory(TeamFactory)
    season = 2025
    conference = Conference.AFC
    division = Division.AFC_EAST
    wins = 10
    losses = 7
    ties = 0
    win_pct = 0.588
    division_rank = 2
