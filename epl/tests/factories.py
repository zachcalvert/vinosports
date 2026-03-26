"""Model factories for EPL tests."""

from decimal import Decimal

import factory
from django.utils import timezone

from epl.betting.models import BetSlip, Parlay, ParlayLeg
from epl.discussions.models import Comment
from epl.matches.models import Match, Odds, Standing, Team
from vinosports.betting.models import UserBalance, UserStats
from vinosports.users.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"epluser{n}@test.com")
    display_name = factory.Sequence(lambda n: f"EplUser{n}")
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
    balance = Decimal("1000.00")


class UserStatsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserStats

    user = factory.SubFactory(UserFactory)


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    external_id = factory.Sequence(lambda n: 60 + n)
    name = factory.Sequence(lambda n: f"Team {n}")
    short_name = factory.Sequence(lambda n: f"Team{n}")
    tla = factory.Sequence(lambda n: f"T{n:02d}")


class MatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Match

    external_id = factory.Sequence(lambda n: 400000 + n)
    home_team = factory.SubFactory(TeamFactory)
    away_team = factory.SubFactory(TeamFactory)
    status = Match.Status.SCHEDULED
    matchday = 1
    kickoff = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=1))
    season = "2025"


class StandingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Standing

    team = factory.SubFactory(TeamFactory)
    season = "2025"
    position = factory.Sequence(lambda n: n + 1)
    played = 20
    won = 10
    drawn = 5
    lost = 5
    goals_for = 30
    goals_against = 20
    goal_difference = 10
    points = 35


class OddsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Odds

    match = factory.SubFactory(MatchFactory)
    bookmaker = "House"
    home_win = Decimal("2.10")
    draw = Decimal("3.40")
    away_win = Decimal("3.20")
    fetched_at = factory.LazyFunction(timezone.now)


class BetSlipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BetSlip

    user = factory.SubFactory(UserFactory)
    match = factory.SubFactory(MatchFactory)
    selection = BetSlip.Selection.HOME_WIN
    odds_at_placement = Decimal("2.10")
    stake = Decimal("50.00")


class ParlayFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Parlay

    user = factory.SubFactory(UserFactory)
    stake = Decimal("30.00")
    combined_odds = Decimal("5.00")


class ParlayLegFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ParlayLeg

    parlay = factory.SubFactory(ParlayFactory)
    match = factory.SubFactory(MatchFactory)
    selection = BetSlip.Selection.HOME_WIN
    odds_at_placement = Decimal("2.10")


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment

    user = factory.SubFactory(UserFactory)
    match = factory.SubFactory(MatchFactory)
    body = factory.Faker("sentence")
