"""Model factories for NBA tests."""

from decimal import Decimal

import factory
from django.utils import timezone

from nba.activity.models import ActivityEvent
from nba.betting.models import BetSlip, Parlay, ParlayLeg
from nba.discussions.models import Comment
from nba.games.models import Conference, Game, GameStatus, Odds, Player, Standing, Team
from vinosports.betting.models import UserBalance
from vinosports.bots.models import BotProfile, ScheduleTemplate, StrategyType
from vinosports.users.models import User

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@test.com")
    display_name = factory.Sequence(lambda n: f"User{n}")
    is_bot = False

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        if not create:
            return
        self.set_password(extracted or "testpass123")
        self.save(update_fields=["password"])


class BotUserFactory(UserFactory):
    display_name = factory.Sequence(lambda n: f"Bot{n}")
    is_bot = True


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------


class UserBalanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserBalance

    user = factory.SubFactory(UserFactory)
    balance = Decimal("1000.00")


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    external_id = factory.Sequence(lambda n: 1610612700 + n)
    name = factory.Sequence(lambda n: f"Team {n}")
    short_name = factory.Sequence(lambda n: f"City Team{n}")
    abbreviation = factory.Sequence(lambda n: f"T{n:02d}")
    conference = Conference.EAST
    division = "Atlantic"


class PlayerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Player

    external_id = factory.Sequence(lambda n: 50000 + n)
    first_name = factory.Sequence(lambda n: f"First{n}")
    last_name = factory.Sequence(lambda n: f"Last{n}")
    position = "G"
    height = "6-3"
    weight = 200
    jersey_number = factory.Sequence(lambda n: str(n % 100))
    college = "Test University"
    country = "USA"
    draft_year = 2020
    draft_round = 1
    draft_number = 10
    team = factory.SubFactory(TeamFactory)
    headshot_url = factory.LazyAttribute(
        lambda o: f"https://cdn.nba.com/headshots/nba/latest/1040x760/{o.external_id}.png"
    )


class GameFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Game

    external_id = factory.Sequence(lambda n: 20250000 + n)
    home_team = factory.SubFactory(TeamFactory)
    away_team = factory.SubFactory(TeamFactory)
    status = GameStatus.SCHEDULED
    game_date = factory.LazyFunction(lambda: timezone.localdate())
    season = 2026
    arena = "Test Arena"


class StandingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Standing

    team = factory.SubFactory(TeamFactory)
    season = 2026
    conference = Conference.EAST
    wins = 40
    losses = 20
    win_pct = 0.667
    games_behind = 0.0
    conference_rank = 3
    home_record = "25-5"
    away_record = "15-15"


class OddsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Odds

    game = factory.SubFactory(GameFactory)
    bookmaker = "House"
    home_moneyline = -150
    away_moneyline = 130
    spread_line = -3.5
    spread_home = -110
    spread_away = -110
    total_line = 222.5
    over_odds = -110
    under_odds = -110
    fetched_at = factory.LazyFunction(timezone.now)


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


# ---------------------------------------------------------------------------
# Bots
# ---------------------------------------------------------------------------


class ScheduleTemplateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ScheduleTemplate

    name = factory.Sequence(lambda n: f"Template {n}")
    slug = factory.Sequence(lambda n: f"template-{n}")
    windows = factory.LazyFunction(
        lambda: [
            {
                "days": [0, 1, 2, 3, 4, 5, 6],
                "hours": list(range(24)),
                "bet_probability": 0.8,
                "comment_probability": 0.8,
                "max_bets": 5,
                "max_comments": 3,
            }
        ]
    )


class BotProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BotProfile

    user = factory.SubFactory(BotUserFactory)
    strategy_type = StrategyType.FRONTRUNNER
    is_active = True
    risk_multiplier = 1.0
    max_daily_bets = 5
    persona_prompt = "You are a confident NBA betting personality."


# ---------------------------------------------------------------------------
# Discussions
# ---------------------------------------------------------------------------


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment

    user = factory.SubFactory(UserFactory)
    game = factory.SubFactory(GameFactory)
    body = factory.Faker("sentence")


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------


class ActivityEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ActivityEvent

    event_type = ActivityEvent.EventType.BOT_BET
    message = factory.Faker("sentence")
