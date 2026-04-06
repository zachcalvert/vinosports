from decimal import Decimal

import factory
from django.utils import timezone
from tests.factories import UserBalanceFactory, UserFactory  # noqa: F401 — re-exported

from worldcup.betting.models import BetSlip, Parlay, ParlayLeg
from worldcup.matches.models import (
    Confederation,
    Group,
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
    stage_type = Stage.StageType.GROUP
    order = factory.Sequence(lambda n: n)


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    external_id = factory.Sequence(lambda n: 9000 + n)
    name = factory.Sequence(lambda n: f"Team {n}")
    short_name = factory.LazyAttribute(lambda o: o.name[:20])
    tla = factory.Sequence(lambda n: f"T{n:02d}"[:3])
    confederation = Confederation.UEFA


class GroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Group

    letter = factory.Sequence(lambda n: chr(ord("A") + (n % 12)))


class MatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Match

    external_id = factory.Sequence(lambda n: 500000 + n)
    home_team = factory.SubFactory(TeamFactory)
    away_team = factory.SubFactory(TeamFactory)
    stage = factory.SubFactory(StageFactory)
    group = None
    kickoff = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=7))
    status = Match.Status.SCHEDULED
    season = "2026"


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

    group = factory.SubFactory(GroupFactory)
    team = factory.SubFactory(TeamFactory)
    position = factory.Sequence(lambda n: (n % 4) + 1)


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
