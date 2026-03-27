"""Tests for epl/betting/tasks.py — settlement, odds generation, parlay evaluation."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from epl.betting.models import BetSlip
from epl.betting.tasks import generate_odds, settle_match_bets, settle_parlay_legs
from epl.matches.models import Match
from vinosports.betting.models import (
    BetStatus,
    UserBalance,
)

from .factories import (
    BetSlipFactory,
    MatchFactory,
    OddsFactory,
    ParlayFactory,
    ParlayLegFactory,
    UserBalanceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# settle_match_bets
# ---------------------------------------------------------------------------


class TestSettleMatchBets:
    def test_winning_bet_gets_payout(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
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
        assert bet.payout == Decimal("50.00") * Decimal("2.10")

        bal = UserBalance.objects.get(user=user)
        assert bal.balance == Decimal("1000.00") + bet.payout

    def test_losing_bet_no_payout(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.FINISHED, home_score=0, away_score=1)
        bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement=Decimal("2.10"),
            stake=Decimal("50.00"),
        )

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.LOST
        assert bet.payout == Decimal("0")

    def test_draw_result(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
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

    def test_cancelled_match_voids_bets(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.CANCELLED)
        bet = BetSlipFactory(user=user, match=match, stake=Decimal("50.00"))

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.VOID
        assert bet.payout == Decimal("50.00")

        bal = UserBalance.objects.get(user=user)
        assert bal.balance == Decimal("1050.00")

    def test_postponed_match_voids_bets(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.POSTPONED)
        bet = BetSlipFactory(user=user, match=match, stake=Decimal("50.00"))

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.VOID

    def test_no_pending_bets_is_noop(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=1)
        # Should not raise
        settle_match_bets(match.pk)

    def test_match_not_found(self):
        # Should not raise
        settle_match_bets(999999)

    def test_match_not_finished_skipped(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.IN_PLAY)
        bet = BetSlipFactory(user=user, match=match, stake=Decimal("50.00"))

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.PENDING

    def test_match_no_scores_skipped(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match = MatchFactory(
            status=Match.Status.FINISHED, home_score=None, away_score=None
        )
        bet = BetSlipFactory(user=user, match=match, stake=Decimal("50.00"))

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.PENDING

    def test_away_win_result(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.FINISHED, home_score=0, away_score=3)
        bet = BetSlipFactory(
            user=user,
            match=match,
            selection=BetSlip.Selection.AWAY_WIN,
            odds_at_placement=Decimal("3.20"),
            stake=Decimal("50.00"),
        )

        settle_match_bets(match.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.WON

    def test_multiple_bets_settled(self):
        user1 = UserFactory()
        user2 = UserFactory()
        UserBalanceFactory(user=user1, balance=Decimal("1000.00"))
        UserBalanceFactory(user=user2, balance=Decimal("1000.00"))
        match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=0)
        bet1 = BetSlipFactory(
            user=user1,
            match=match,
            selection=BetSlip.Selection.HOME_WIN,
            stake=Decimal("50.00"),
        )
        bet2 = BetSlipFactory(
            user=user2,
            match=match,
            selection=BetSlip.Selection.AWAY_WIN,
            stake=Decimal("50.00"),
        )

        settle_match_bets(match.pk)

        bet1.refresh_from_db()
        bet2.refresh_from_db()
        assert bet1.status == BetStatus.WON
        assert bet2.status == BetStatus.LOST


# ---------------------------------------------------------------------------
# settle_parlay_legs
# ---------------------------------------------------------------------------


class TestSettleParlayLegs:
    def test_winning_leg_marked_won(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match = MatchFactory()
        parlay = ParlayFactory(user=user)
        leg = ParlayLegFactory(
            parlay=parlay, match=match, selection=BetSlip.Selection.HOME_WIN
        )

        settle_parlay_legs(match, BetSlip.Selection.HOME_WIN)

        leg.refresh_from_db()
        assert leg.status == BetStatus.WON

    def test_losing_leg_marked_lost(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match = MatchFactory()
        parlay = ParlayFactory(user=user)
        leg = ParlayLegFactory(
            parlay=parlay, match=match, selection=BetSlip.Selection.HOME_WIN
        )

        settle_parlay_legs(match, BetSlip.Selection.AWAY_WIN)

        leg.refresh_from_db()
        assert leg.status == BetStatus.LOST

    def test_void_when_winning_selection_none(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match = MatchFactory()
        parlay = ParlayFactory(user=user)
        leg = ParlayLegFactory(parlay=parlay, match=match)

        settle_parlay_legs(match, winning_selection=None)

        leg.refresh_from_db()
        assert leg.status == BetStatus.VOID

    def test_no_pending_legs_is_noop(self):
        match = MatchFactory()
        # No legs to settle — should not raise
        settle_parlay_legs(match, BetSlip.Selection.HOME_WIN)

    def test_parlay_lost_when_leg_lost(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match1 = MatchFactory()
        match2 = MatchFactory()
        parlay = ParlayFactory(user=user, stake=Decimal("30.00"))
        ParlayLegFactory(
            parlay=parlay, match=match1, selection=BetSlip.Selection.HOME_WIN
        )
        ParlayLegFactory(
            parlay=parlay, match=match2, selection=BetSlip.Selection.HOME_WIN
        )

        # Settle match1 as away win — leg1 loses
        settle_parlay_legs(match1, BetSlip.Selection.AWAY_WIN)

        parlay.refresh_from_db()
        assert parlay.status == BetStatus.LOST
        assert parlay.payout == Decimal("0")

    def test_parlay_won_when_all_legs_won(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match1 = MatchFactory()
        match2 = MatchFactory()
        parlay = ParlayFactory(
            user=user, stake=Decimal("30.00"), combined_odds=Decimal("5.00")
        )
        ParlayLegFactory(
            parlay=parlay,
            match=match1,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement=Decimal("2.10"),
        )
        ParlayLegFactory(
            parlay=parlay,
            match=match2,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement=Decimal("2.50"),
        )

        settle_parlay_legs(match1, BetSlip.Selection.HOME_WIN)
        settle_parlay_legs(match2, BetSlip.Selection.HOME_WIN)

        parlay.refresh_from_db()
        assert parlay.status == BetStatus.WON
        assert parlay.payout > Decimal("0")

    def test_parlay_stays_pending_with_unsettled_legs(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match1 = MatchFactory()
        match2 = MatchFactory()
        parlay = ParlayFactory(user=user)
        ParlayLegFactory(
            parlay=parlay, match=match1, selection=BetSlip.Selection.HOME_WIN
        )
        ParlayLegFactory(
            parlay=parlay, match=match2, selection=BetSlip.Selection.HOME_WIN
        )

        # Settle only match1
        settle_parlay_legs(match1, BetSlip.Selection.HOME_WIN)

        parlay.refresh_from_db()
        assert parlay.status == BetStatus.PENDING

    def test_all_void_legs_refund_stake(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("1000.00"))
        match1 = MatchFactory()
        match2 = MatchFactory()
        parlay = ParlayFactory(user=user, stake=Decimal("30.00"))
        ParlayLegFactory(parlay=parlay, match=match1)
        ParlayLegFactory(parlay=parlay, match=match2)

        settle_parlay_legs(match1, winning_selection=None)
        settle_parlay_legs(match2, winning_selection=None)

        parlay.refresh_from_db()
        assert parlay.status == BetStatus.VOID
        assert parlay.payout == Decimal("30.00")

        bal = UserBalance.objects.get(user=user)
        assert bal.balance == Decimal("1030.00")


# ---------------------------------------------------------------------------
# generate_odds task
# ---------------------------------------------------------------------------


class TestGenerateOddsTask:
    @patch("epl.betting.tasks.generate_all_upcoming_odds")
    def test_creates_new_odds(self, mock_generate):
        match = MatchFactory(season="2025")
        mock_generate.return_value = [
            {
                "match": match,
                "home_win": Decimal("2.10"),
                "draw": Decimal("3.40"),
                "away_win": Decimal("3.20"),
            }
        ]

        with patch("epl.activity.services.queue_activity_event"):
            generate_odds()

        from epl.matches.models import Odds

        assert Odds.objects.filter(match=match, bookmaker="House").exists()

    @patch("epl.betting.tasks.generate_all_upcoming_odds")
    def test_updates_existing_odds(self, mock_generate):
        match = MatchFactory(season="2025")
        existing = OddsFactory(
            match=match,
            bookmaker="House",
            home_win=Decimal("2.10"),
            draw=Decimal("3.40"),
            away_win=Decimal("3.20"),
        )
        mock_generate.return_value = [
            {
                "match": match,
                "home_win": Decimal("2.50"),
                "draw": Decimal("3.00"),
                "away_win": Decimal("2.80"),
            }
        ]

        generate_odds()

        existing.refresh_from_db()
        assert existing.home_win == Decimal("2.50")

    @patch("epl.betting.tasks.generate_all_upcoming_odds")
    def test_skips_unchanged_odds(self, mock_generate):
        match = MatchFactory(season="2025")
        OddsFactory(
            match=match,
            bookmaker="House",
            home_win=Decimal("2.10"),
            draw=Decimal("3.40"),
            away_win=Decimal("3.20"),
        )
        mock_generate.return_value = [
            {
                "match": match,
                "home_win": Decimal("2.10"),
                "draw": Decimal("3.40"),
                "away_win": Decimal("3.20"),
            }
        ]

        from epl.matches.models import Odds

        count_before = Odds.objects.count()
        generate_odds()
        assert Odds.objects.count() == count_before

    @patch("epl.betting.tasks.generate_all_upcoming_odds", return_value=[])
    def test_empty_results_no_error(self, mock_generate):
        generate_odds()

    @patch("epl.betting.tasks.generate_all_upcoming_odds")
    def test_queues_activity_event_on_create(self, mock_generate):
        match = MatchFactory(season="2025")
        mock_generate.return_value = [
            {
                "match": match,
                "home_win": Decimal("2.10"),
                "draw": Decimal("3.40"),
                "away_win": Decimal("3.20"),
            }
        ]

        with patch("epl.activity.services.queue_activity_event") as mock_queue:
            generate_odds()

        mock_queue.assert_called_once()
