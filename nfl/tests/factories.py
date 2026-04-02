"""Model factories for NFL tests."""

from decimal import Decimal

import factory
from django.contrib.auth import get_user_model

from nfl.betting.models import BetSlip, Odds, Parlay, ParlayLeg
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
from vinosports.betting.models import UserBalance

User = get_user_model()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"nfluser{n}@test.com")
    display_name = factory.Sequence(lambda n: f"NFLUser{n}")
    is_bot = False

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        if not create:
            return
        self.set_password(extracted or "testpass123")
        self.save(update_fields=["password"])


class UserBalanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserBalance

    user = factory.SubFactory(UserFactory)
    balance = Decimal("100000.00")


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


# ---------------------------------------------------------------------------
# Betting
# ---------------------------------------------------------------------------


class BetSlipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BetSlip

    user = factory.SubFactory(UserFactory)
    game = factory.SubFactory(GameFactory)
    market = BetSlip.Market.MONEYLINE
    selection = BetSlip.Selection.HOME
    odds_at_placement = -150
    stake = Decimal("50.00")


class ParlayFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Parlay

    user = factory.SubFactory(UserFactory)
    stake = Decimal("30.00")
    combined_odds = 600


class ParlayLegFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ParlayLeg

    parlay = factory.SubFactory(ParlayFactory)
    game = factory.SubFactory(GameFactory)
    market = BetSlip.Market.MONEYLINE
    selection = BetSlip.Selection.HOME
    odds_at_placement = -150


class OddsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Odds

    game = factory.SubFactory(GameFactory)
    bookmaker = "House"
    home_moneyline = -150
    away_moneyline = 130
    spread_line = -3.0
    spread_home = -110
    spread_away = -110
    total_line = 44.5
    over_odds = -110
    under_odds = -110
    fetched_at = factory.LazyFunction(
        lambda: __import__("django.utils.timezone", fromlist=["now"]).now()
    )
