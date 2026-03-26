"""Tests for epl.betting.tasks — bet and parlay settlement."""

from decimal import Decimal

import pytest

from epl.betting.models import BetSlip
from epl.betting.tasks import settle_match_bets, settle_parlay_legs
from epl.matches.models import Match
from vinosports.betting.models import BetStatus, UserBalance

from .factories import (
    BetSlipFactory,
    MatchFactory,
    ParlayFactory,
    ParlayLegFactory,
    UserBalanceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


class TestSettleMatchBets:
    def test_home_win_settles_correctly(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("950.00"))
        match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=1)
        bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement=Decimal("2.10"),
            stake=Decimal("50.00"),
        )

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.WON
        assert bet.payout == Decimal("105.00")

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("1055.00")

    def test_losing_bet(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("950.00"))
        match = MatchFactory(status=Match.Status.FINISHED, home_score=0, away_score=1)
        bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
            stake=Decimal("50.00"),
        )

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.LOST
        assert bet.payout == Decimal("0")

    def test_draw_result(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("950.00"))
        match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=1)
        bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.DRAW,
            odds_at_placement=Decimal("3.40"),
            stake=Decimal("50.00"),
        )

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.WON
        assert bet.payout == Decimal("170.00")

    def test_cancelled_match_voids_bets(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("950.00"))
        match = MatchFactory(status=Match.Status.CANCELLED)
        bet = BetSlipFactory(user=user, match=match, stake=Decimal("50.00"))

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.VOID
        assert bet.payout == Decimal("50.00")

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("1000.00")

    def test_no_settlement_for_scheduled_match(self):
        match = MatchFactory(status=Match.Status.SCHEDULED)
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("950.00"))
        bet = BetSlipFactory(user=user, match=match, stake=Decimal("50.00"))

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.PENDING

    def test_missing_match_handled(self):
        settle_match_bets(999999)  # should not raise


class TestSettleParlayLegs:
    def test_winning_leg_marked_won(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=0)
        parlay = ParlayFactory()
        leg = ParlayLegFactory(
            parlay=parlay,
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
        )

        settle_parlay_legs(match, winning_selection=BetSlip.Selection.HOME_WIN)

        leg.refresh_from_db()
        assert leg.status == BetStatus.WON

    def test_losing_leg_marked_lost(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=0, away_score=1)
        parlay = ParlayFactory()
        leg = ParlayLegFactory(
            parlay=parlay,
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
        )

        settle_parlay_legs(match, winning_selection=BetSlip.Selection.AWAY_WIN)

        leg.refresh_from_db()
        assert leg.status == BetStatus.LOST

    def test_void_when_no_winning_selection(self):
        match = MatchFactory(status=Match.Status.CANCELLED)
        parlay = ParlayFactory()
        leg = ParlayLegFactory(parlay=parlay, match=match)

        settle_parlay_legs(match, winning_selection=None)

        leg.refresh_from_db()
        assert leg.status == BetStatus.VOID

    def test_parlay_won_when_all_legs_won(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("970.00"))
        parlay = ParlayFactory(
            user=user, stake=Decimal("30.00"), combined_odds=Decimal("5.00")
        )

        m1 = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=0)
        m2 = MatchFactory(status=Match.Status.FINISHED, home_score=3, away_score=1)

        ParlayLegFactory(
            parlay=parlay,
            match=m1,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement=Decimal("2.00"),
        )
        ParlayLegFactory(
            parlay=parlay,
            match=m2,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement=Decimal("2.50"),
        )

        settle_parlay_legs(m1, winning_selection=BetSlip.Selection.HOME_WIN)
        settle_parlay_legs(m2, winning_selection=BetSlip.Selection.HOME_WIN)

        parlay.refresh_from_db()
        assert parlay.status == BetStatus.WON
        assert parlay.payout > Decimal("0")

    def test_parlay_lost_when_any_leg_lost(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("970.00"))
        parlay = ParlayFactory(user=user, stake=Decimal("30.00"))

        m1 = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=0)
        m2 = MatchFactory(status=Match.Status.FINISHED, home_score=0, away_score=1)

        ParlayLegFactory(
            parlay=parlay,
            match=m1,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement=Decimal("2.00"),
        )
        ParlayLegFactory(
            parlay=parlay,
            match=m2,
            selection=BetSlip.Selection.HOME_WIN,  # loses
            odds_at_placement=Decimal("2.50"),
        )

        settle_parlay_legs(m1, winning_selection=BetSlip.Selection.HOME_WIN)
        settle_parlay_legs(m2, winning_selection=BetSlip.Selection.AWAY_WIN)

        parlay.refresh_from_db()
        assert parlay.status == BetStatus.LOST
        assert parlay.payout == Decimal("0")
