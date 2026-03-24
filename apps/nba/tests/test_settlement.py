"""Tests for bet settlement logic — outcome evaluation, odds conversion, and full settlement."""

from decimal import Decimal

import pytest
from betting.models import BetSlip
from betting.settlement import (
    _evaluate_bet_outcome,
    american_to_decimal,
    calculate_payout,
    decimal_to_american,
    grant_bailout,
    recalculate_parlay_odds,
    settle_game_bets,
)
from games.models import GameStatus

from tests.factories import (
    BetSlipFactory,
    GameFactory,
    ParlayFactory,
    ParlayLegFactory,
    UserBalanceFactory,
    UserFactory,
)
from vinosports.betting.models import (
    Bankruptcy,
    BetStatus,
    UserBalance,
)

# ---------------------------------------------------------------------------
# Odds conversion helpers
# ---------------------------------------------------------------------------


class TestAmericanToDecimal:
    def test_positive_odds(self):
        assert american_to_decimal(200) == Decimal("3")  # +200 → 3.0

    def test_negative_odds(self):
        result = american_to_decimal(-150)
        expected = Decimal(100) / Decimal(150) + 1  # ≈ 1.667
        assert result == expected

    def test_even_odds(self):
        assert american_to_decimal(100) == Decimal("2")


class TestDecimalToAmerican:
    def test_decimal_gte_2(self):
        assert decimal_to_american(Decimal("3.0")) == 200

    def test_decimal_lt_2(self):
        result = decimal_to_american(Decimal("1.5"))
        assert result == -200  # -100 / (1.5 - 1) = -200


class TestCalculatePayout:
    def test_positive_odds(self):
        result = calculate_payout(Decimal("100.00"), 200)
        assert result == Decimal("300.00")

    def test_negative_odds(self):
        result = calculate_payout(Decimal("150.00"), -150)
        # decimal = 100/150 + 1 = 1.667; 150 * 1.667 = 250.00
        assert result == Decimal("250.00")


class TestRecalculateParleyOdds:
    def test_two_legs(self):
        leg1 = type("Leg", (), {"odds_at_placement": -150})()
        leg2 = type("Leg", (), {"odds_at_placement": 200})()
        result = recalculate_parlay_odds([leg1, leg2])
        # Combined decimal: (100/150+1) * (200/100+1) = 1.667 * 3.0 = 5.0
        assert result == 400  # (5.0 - 1) * 100 = 400


# ---------------------------------------------------------------------------
# _evaluate_bet_outcome — pure logic (no DB)
# ---------------------------------------------------------------------------


class TestEvaluateBetOutcome:
    """Uses a mock game object to avoid DB hits."""

    def _game(self, home=100, away=95):
        from unittest.mock import MagicMock

        g = MagicMock()
        g.home_score = home
        g.away_score = away
        return g

    # Moneyline
    def test_moneyline_home_wins(self):
        result = _evaluate_bet_outcome("MONEYLINE", "HOME", None, self._game(110, 95))
        assert result == BetStatus.WON

    def test_moneyline_home_loses(self):
        result = _evaluate_bet_outcome("MONEYLINE", "HOME", None, self._game(90, 110))
        assert result == BetStatus.LOST

    def test_moneyline_away_wins(self):
        result = _evaluate_bet_outcome("MONEYLINE", "AWAY", None, self._game(90, 110))
        assert result == BetStatus.WON

    def test_moneyline_tie_is_void(self):
        result = _evaluate_bet_outcome("MONEYLINE", "HOME", None, self._game(100, 100))
        assert result == BetStatus.VOID

    # Spread
    def test_spread_home_covers(self):
        # Home -3.5, scores 110 vs 105: 110 + (-3.5) = 106.5 > 105 → WON
        result = _evaluate_bet_outcome("SPREAD", "HOME", -3.5, self._game(110, 105))
        assert result == BetStatus.WON

    def test_spread_home_fails_to_cover(self):
        # Home -7.5, scores 110 vs 105: 110 + (-7.5) = 102.5 < 105 → LOST
        result = _evaluate_bet_outcome("SPREAD", "HOME", -7.5, self._game(110, 105))
        assert result == BetStatus.LOST

    def test_spread_push_is_void(self):
        # Home -5, scores 110 vs 105: 110 + (-5) = 105 - 105 = 0 → VOID
        result = _evaluate_bet_outcome("SPREAD", "HOME", -5.0, self._game(110, 105))
        assert result == BetStatus.VOID

    def test_spread_away(self):
        # Away +3.5, home scores 110, away 108: 108 + 3.5 = 111.5 > 110 → WON
        result = _evaluate_bet_outcome("SPREAD", "AWAY", 3.5, self._game(110, 108))
        assert result == BetStatus.WON

    # Total
    def test_total_over_wins(self):
        # Line 210.5, total = 110+105 = 215 > 210.5 → WON
        result = _evaluate_bet_outcome("TOTAL", "OVER", 210.5, self._game(110, 105))
        assert result == BetStatus.WON

    def test_total_over_loses(self):
        # Line 220.5, total = 215 < 220.5 → LOST
        result = _evaluate_bet_outcome("TOTAL", "OVER", 220.5, self._game(110, 105))
        assert result == BetStatus.LOST

    def test_total_under_wins(self):
        result = _evaluate_bet_outcome("TOTAL", "UNDER", 220.5, self._game(110, 105))
        assert result == BetStatus.WON

    def test_total_push_is_void(self):
        # Line = exact total → VOID
        result = _evaluate_bet_outcome("TOTAL", "OVER", 215.0, self._game(110, 105))
        assert result == BetStatus.VOID

    def test_unknown_market_raises(self):
        with pytest.raises(ValueError, match="Unknown market"):
            _evaluate_bet_outcome("MYSTERY", "HOME", None, self._game())


# ---------------------------------------------------------------------------
# settle_game_bets — integration (DB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSettleGameBets:
    def _final_game(self, home_score=110, away_score=95):
        return GameFactory(
            status=GameStatus.FINAL,
            home_score=home_score,
            away_score=away_score,
        )

    def test_settle_winning_moneyline_bet(self):
        game = self._final_game(110, 95)
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("950.00"))
        bet = BetSlipFactory(
            user=user,
            game=game,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            odds_at_placement=-150,
            stake=Decimal("50.00"),
        )

        result = settle_game_bets(game.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.WON
        assert bet.payout is not None
        assert bet.payout > bet.stake
        assert result["won"] == 1

    def test_settle_losing_bet(self):
        game = self._final_game(90, 110)
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("950.00"))
        bet = BetSlipFactory(
            user=user,
            game=game,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            odds_at_placement=-150,
            stake=Decimal("50.00"),
        )

        result = settle_game_bets(game.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.LOST
        assert result["lost"] == 1

    def test_settle_void_bet(self):
        game = self._final_game(100, 100)
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("950.00"))
        bet = BetSlipFactory(
            user=user,
            game=game,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            odds_at_placement=-150,
            stake=Decimal("50.00"),
        )

        result = settle_game_bets(game.pk)

        bet.refresh_from_db()
        assert bet.status == BetStatus.VOID
        assert result["void"] == 1

    def test_raises_for_non_final_game(self):
        game = GameFactory(status=GameStatus.SCHEDULED)
        with pytest.raises(ValueError, match="not FINAL"):
            settle_game_bets(game.pk)

    def test_idempotent(self):
        game = self._final_game(110, 95)
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("950.00"))
        BetSlipFactory(
            user=user,
            game=game,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            stake=Decimal("50.00"),
        )

        result1 = settle_game_bets(game.pk)
        result2 = settle_game_bets(game.pk)
        assert result1["settled"] == 1
        assert result2["settled"] == 0

    def test_bankruptcy_detection(self):
        game = self._final_game(90, 110)
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("0.30"))
        BetSlipFactory(
            user=user,
            game=game,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            stake=Decimal("50.00"),
        )

        settle_game_bets(game.pk)

        assert Bankruptcy.objects.filter(user=user).exists()

    def test_parlay_all_won(self):
        """A 2-leg parlay where both legs win should pay out."""
        game1 = self._final_game(110, 95)
        game2 = self._final_game(105, 100)

        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("970.00"))
        parlay = ParlayFactory(user=user, stake=Decimal("30.00"), combined_odds=300)

        ParlayLegFactory(
            parlay=parlay,
            game=game1,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            odds_at_placement=-150,
        )
        ParlayLegFactory(
            parlay=parlay,
            game=game2,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            odds_at_placement=-120,
        )

        settle_game_bets(game1.pk)
        settle_game_bets(game2.pk)

        parlay.refresh_from_db()
        assert parlay.status == BetStatus.WON
        assert parlay.payout is not None

    def test_parlay_one_lost(self):
        """A parlay with one lost leg should be LOST."""
        game1 = self._final_game(110, 95)
        game2 = self._final_game(90, 110)  # home loses

        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("970.00"))
        parlay = ParlayFactory(user=user, stake=Decimal("30.00"), combined_odds=300)

        ParlayLegFactory(
            parlay=parlay,
            game=game1,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            odds_at_placement=-150,
        )
        ParlayLegFactory(
            parlay=parlay,
            game=game2,
            market=BetSlip.Market.MONEYLINE,
            selection=BetSlip.Selection.HOME,
            odds_at_placement=-120,
        )

        settle_game_bets(game1.pk)
        settle_game_bets(game2.pk)

        parlay.refresh_from_db()
        assert parlay.status == BetStatus.LOST


# ---------------------------------------------------------------------------
# grant_bailout
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGrantBailout:
    def test_bailout_credits_balance(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("0.00"))
        Bankruptcy.objects.create(user=user, balance_at_bankruptcy=Decimal("0.00"))

        bailout = grant_bailout(user, Decimal("500.00"))

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("500.00")
        assert bailout.amount == Decimal("500.00")

    def test_bailout_raises_if_not_bankrupt(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))

        with pytest.raises(ValueError, match="not bankrupt"):
            grant_bailout(user)
