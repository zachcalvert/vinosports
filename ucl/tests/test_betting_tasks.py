"""Tests for UCL bet settlement.

Key design rule: bets settle on the 90-minute scoreline only.
A 1-1 draw at full time means DRAW wins — regardless of what
happens in extra time or penalties.
"""

from decimal import Decimal

import pytest

from ucl.betting.models import BetSlip
from ucl.betting.tasks import settle_match_bets
from ucl.matches.models import Match
from vinosports.betting.models import BetStatus

from .factories import (
    BetSlipFactory,
    FinishedMatchFactory,
    MatchFactory,
    UserBalanceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


class TestSettleMatchBets:
    # ------------------------------------------------------------------
    # Basic 90-minute settlement
    # ------------------------------------------------------------------

    def test_home_win_bet_wins(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        match = FinishedMatchFactory(home_score=2, away_score=1)
        bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
            stake=Decimal("100.00"),
            odds_at_placement=Decimal("2.10"),
        )

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.WON
        assert bet.payout == Decimal("210.00")

    def test_away_win_bet_wins(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        match = FinishedMatchFactory(home_score=0, away_score=2)
        bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.AWAY_WIN,
            stake=Decimal("50.00"),
            odds_at_placement=Decimal("3.20"),
        )

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.WON
        assert bet.payout == Decimal("160.00")

    def test_draw_bet_wins(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        match = FinishedMatchFactory(home_score=1, away_score=1)
        bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.DRAW,
            stake=Decimal("40.00"),
            odds_at_placement=Decimal("3.40"),
        )

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.WON

    def test_losing_bet_gets_zero_payout(self):
        user = UserFactory()
        UserBalanceFactory(user=user)
        match = FinishedMatchFactory(home_score=3, away_score=0)
        bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.AWAY_WIN,
            stake=Decimal("100.00"),
            odds_at_placement=Decimal("4.00"),
        )

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.LOST
        assert bet.payout == 0

    def test_multiple_bets_settled_correctly(self):
        match = FinishedMatchFactory(home_score=1, away_score=0)
        winner = BetSlipFactory(match=match, selection=BetSlip.Selection.HOME_WIN)
        loser1 = BetSlipFactory(match=match, selection=BetSlip.Selection.AWAY_WIN)
        loser2 = BetSlipFactory(match=match, selection=BetSlip.Selection.DRAW)

        settle_match_bets(match.pk)

        winner.refresh_from_db()
        loser1.refresh_from_db()
        loser2.refresh_from_db()
        assert winner.status == BetStatus.WON
        assert loser1.status == BetStatus.LOST
        assert loser2.status == BetStatus.LOST

    # ------------------------------------------------------------------
    # The 90-min rule: ET and penalties do NOT change settlement
    # ------------------------------------------------------------------

    def test_draw_bet_wins_when_match_goes_to_extra_time(self):
        """1-1 at 90 min -> DRAW bet wins even if home won in ET."""
        user = UserFactory()
        UserBalanceFactory(user=user)
        match = FinishedMatchFactory(
            home_score=1,
            away_score=1,
            home_score_et=2,
            away_score_et=1,
        )
        draw_bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.DRAW,
            stake=Decimal("50.00"),
            odds_at_placement=Decimal("3.40"),
        )
        home_bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
            stake=Decimal("50.00"),
            odds_at_placement=Decimal("2.10"),
        )

        settle_match_bets(match.pk)

        draw_bet.refresh_from_db()
        home_bet.refresh_from_db()
        assert draw_bet.status == BetStatus.WON
        assert home_bet.status == BetStatus.LOST

    def test_draw_bet_wins_when_match_decided_by_penalties(self):
        """0-0 after 90 min -> DRAW bet wins even if away won on penalties."""
        user = UserFactory()
        UserBalanceFactory(user=user)
        match = FinishedMatchFactory(
            home_score=0,
            away_score=0,
            home_score_et=0,
            away_score_et=0,
            home_score_penalties=3,
            away_score_penalties=5,
        )
        draw_bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.DRAW,
            stake=Decimal("30.00"),
            odds_at_placement=Decimal("8.00"),
        )
        away_bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.AWAY_WIN,
            stake=Decimal("30.00"),
            odds_at_placement=Decimal("2.50"),
        )

        settle_match_bets(match.pk)

        draw_bet.refresh_from_db()
        away_bet.refresh_from_db()
        assert draw_bet.status == BetStatus.WON
        assert away_bet.status == BetStatus.LOST

    def test_home_win_bet_wins_at_90_regardless_of_knockout(self):
        """2-1 at 90 min -> HOME_WIN bet wins, settlement is always on 90-min score."""
        match = FinishedMatchFactory(home_score=2, away_score=1)
        home_bet = BetSlipFactory(
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
        )

        settle_match_bets(match.pk)

        home_bet.refresh_from_db()
        assert home_bet.status == BetStatus.WON

    # ------------------------------------------------------------------
    # Guard rails
    # ------------------------------------------------------------------

    def test_does_not_settle_unfinished_match(self):
        match = MatchFactory(status=Match.Status.IN_PLAY, home_score=1, away_score=0)
        bet = BetSlipFactory(match=match, selection=BetSlip.Selection.HOME_WIN)

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.PENDING

    def test_does_not_raise_for_missing_match(self):
        """Should log and return gracefully rather than raising."""
        settle_match_bets(999999)

    def test_does_not_resettle_already_settled_bets(self):
        match = FinishedMatchFactory(home_score=1, away_score=0)
        already_won = BetSlipFactory(
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
            status=BetStatus.WON,
            payout=Decimal("210.00"),
        )

        settle_match_bets(match.pk)

        already_won.refresh_from_db()
        assert already_won.status == BetStatus.WON
        assert already_won.payout == Decimal("210.00")
