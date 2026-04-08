from decimal import Decimal

import factory
from django.utils import timezone
from tests.factories import UserBalanceFactory, UserFactory  # noqa: F401 — re-exported

from ucl.betting.models import BetSlip, Parlay, ParlayLeg
from ucl.discussions.models import Comment
from ucl.matches.models import (
    Match,
    Odds,
    Stage,
    Standing,
    Team,
)


class StageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Stage
        django_get_or_create = ("stage_type",)

    name = factory.LazyAttribute(lambda o: o.stage_type.replace("_", " ").title())
    stage_type = Stage.StageType.LEAGUE_PHASE
    order = factory.Sequence(lambda n: n)


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    external_id = factory.Sequence(lambda n: 9000 + n)
    name = factory.Sequence(lambda n: f"Club {n}")
    short_name = factory.LazyAttribute(lambda o: o.name[:20])
    tla = factory.Sequence(lambda n: f"C{n:02d}"[:3])
    country = "England"
    domestic_league = "Premier League"


class MatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Match

    external_id = factory.Sequence(lambda n: 600000 + n)
    home_team = factory.SubFactory(TeamFactory)
    away_team = factory.SubFactory(TeamFactory)
    stage = factory.SubFactory(StageFactory)
    kickoff = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=7))
    status = Match.Status.SCHEDULED
    season = "2025"


class FinishedMatchFactory(MatchFactory):
    status = Match.Status.FINISHED
    kickoff = factory.LazyFunction(lambda: timezone.now() - timezone.timedelta(hours=2))
    home_score = 1
    away_score = 0


class OddsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Odds

    match = factory.SubFactory(MatchFactory)
    bookmaker = "House"
    home_win = Decimal("2.10")
    draw = Decimal("3.40")
    away_win = Decimal("3.20")
    fetched_at = factory.LazyFunction(timezone.now)


class StandingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Standing

    team = factory.SubFactory(TeamFactory)
    season = "2025"
    position = factory.Sequence(lambda n: (n % 36) + 1)


class BetSlipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BetSlip

    user = factory.SubFactory(UserFactory)
    match = factory.SubFactory(MatchFactory)
    selection = BetSlip.Selection.HOME_WIN
    stake = Decimal("100.00")
    odds_at_placement = Decimal("2.10")


class ParlayFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Parlay

    user = factory.SubFactory(UserFactory)
    stake = Decimal("50.00")
    combined_odds = Decimal("6.30")


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
    body = factory.Sequence(lambda n: f"Comment body {n}")
    parent = None
    is_deleted = False
