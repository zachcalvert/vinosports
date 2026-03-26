"""Tests for ParlayBuilder with the NBA adapter."""

from decimal import Decimal

import pytest

from nba.betting.models import BetSlip, Parlay, ParlayLeg
from nba.betting.settlement import american_to_decimal, decimal_to_american
from nba.games.models import GameStatus
from vinosports.betting.models import BalanceTransaction, BetStatus, UserBalance
from vinosports.betting.parlay_builder import (
    InsufficientBalanceError,
    ParlayBuilder,
    ParlayValidationError,
)

from .factories import GameFactory, OddsFactory, UserBalanceFactory, UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestNBAParlayBuilderValidation:
    def test_too_few_legs(self):
        game = GameFactory()
        builder = ParlayBuilder("nba")
        builder.add_leg(game.pk, "HOME", market="MONEYLINE")

        errors = builder.validate()
        assert any("at least" in e for e in errors)

    def test_duplicate_event_rejected(self):
        game = GameFactory()
        builder = ParlayBuilder("nba")
        builder.add_leg(game.pk, "HOME", market="MONEYLINE")
        builder.add_leg(game.pk, "AWAY", market="MONEYLINE")

        errors = builder.validate()
        assert any("Duplicate" in e for e in errors)

    def test_unbettable_game_raises(self):
        g1 = GameFactory(status=GameStatus.FINAL)
        g2 = GameFactory()
        OddsFactory(game=g2)

        builder = ParlayBuilder("nba")
        builder.add_leg(g1.pk, "HOME", market="MONEYLINE")
        builder.add_leg(g2.pk, "AWAY", market="MONEYLINE")

        with pytest.raises(ParlayValidationError, match="not open"):
            builder.preview()

    def test_missing_market_raises(self):
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1)
        OddsFactory(game=g2)

        builder = ParlayBuilder("nba")
        builder.add_leg(g1.pk, "HOME")  # no market
        builder.add_leg(g2.pk, "AWAY", market="MONEYLINE")

        with pytest.raises(ParlayValidationError, match="market"):
            builder.preview()

    def test_invalid_market_selection_raises(self):
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1)
        OddsFactory(game=g2)

        builder = ParlayBuilder("nba")
        builder.add_leg(g1.pk, "HOME", market="MONEYLINE")
        builder.add_leg(g2.pk, "BOGUS", market="MONEYLINE")

        with pytest.raises(ParlayValidationError, match="Invalid NBA"):
            builder.preview()


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class TestNBAParlayBuilderPreview:
    def test_preview_moneyline_combined_odds(self):
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, home_moneyline=-150)
        OddsFactory(game=g2, away_moneyline=200)

        preview = (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", market="MONEYLINE")
            .add_leg(g2.pk, "AWAY", market="MONEYLINE")
            .preview(stake=Decimal("10.00"))
        )

        # -150 → 1.667, +200 → 3.0, combined ≈ 5.00
        expected_combined = (
            american_to_decimal(-150) * american_to_decimal(200)
        ).quantize(Decimal("0.01"))
        assert preview.combined_odds == expected_combined
        assert preview.league == "nba"
        assert len(preview.legs) == 2

    def test_preview_spread_and_total_markets(self):
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, spread_home=-110, spread_line=-3.5)
        OddsFactory(game=g2, over_odds=-105, total_line=222.5)

        preview = (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", market="SPREAD")
            .add_leg(g2.pk, "OVER", market="TOTAL")
            .preview(stake=Decimal("10.00"))
        )

        assert len(preview.legs) == 2
        assert preview.combined_odds > Decimal("1.00")

    def test_preview_no_side_effects(self):
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, home_moneyline=-150)
        OddsFactory(game=g2, away_moneyline=130)

        (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", market="MONEYLINE")
            .add_leg(g2.pk, "AWAY", market="MONEYLINE")
            .preview(stake=Decimal("10.00"))
        )

        assert Parlay.objects.count() == 0
        assert ParlayLeg.objects.count() == 0

    def test_preview_with_explicit_odds(self):
        g1 = GameFactory()
        g2 = GameFactory()

        preview = (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", odds=Decimal("1.50"), market="MONEYLINE")
            .add_leg(g2.pk, "AWAY", odds=Decimal("3.00"), market="MONEYLINE")
            .preview(stake=Decimal("10.00"))
        )

        assert preview.combined_odds == Decimal("4.50")

    def test_preview_uses_best_odds_across_bookmakers(self):
        game = GameFactory()
        OddsFactory(game=game, home_moneyline=-150, bookmaker="Book1")
        OddsFactory(game=game, home_moneyline=-120, bookmaker="Book2")  # better

        g2 = GameFactory()
        OddsFactory(game=g2, away_moneyline=130)

        preview = (
            ParlayBuilder("nba")
            .add_leg(game.pk, "HOME", market="MONEYLINE")
            .add_leg(g2.pk, "AWAY", market="MONEYLINE")
            .preview(stake=Decimal("10.00"))
        )

        # Max(home_moneyline) = -120 → decimal 1.833...
        leg_odds = preview.legs[0].decimal_odds
        expected = american_to_decimal(-120)
        assert leg_odds == expected


# ---------------------------------------------------------------------------
# Place
# ---------------------------------------------------------------------------


class TestNBAParlayBuilderPlace:
    def test_place_creates_parlay_and_legs(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        g1 = GameFactory()
        g2 = GameFactory()
        g3 = GameFactory()
        OddsFactory(game=g1, home_moneyline=-150)
        OddsFactory(game=g2, away_moneyline=200)
        OddsFactory(game=g3, home_moneyline=-110)

        parlay = (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", market="MONEYLINE")
            .add_leg(g2.pk, "AWAY", market="MONEYLINE")
            .add_leg(g3.pk, "HOME", market="MONEYLINE")
            .place(user, stake=Decimal("20.00"))
        )

        assert parlay.pk is not None
        assert parlay.user == user
        assert parlay.stake == Decimal("20.00")
        assert parlay.status == BetStatus.PENDING
        assert parlay.legs.count() == 3
        # combined_odds stored as American integer
        assert isinstance(parlay.combined_odds, int)

    def test_place_deducts_balance(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, home_moneyline=-150)
        OddsFactory(game=g2, away_moneyline=130)

        (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", market="MONEYLINE")
            .add_leg(g2.pk, "AWAY", market="MONEYLINE")
            .place(user, stake=Decimal("20.00"))
        )

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("480.00")

    def test_place_creates_transaction(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, home_moneyline=-150)
        OddsFactory(game=g2, away_moneyline=130)

        (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", market="MONEYLINE")
            .add_leg(g2.pk, "AWAY", market="MONEYLINE")
            .place(user, stake=Decimal("20.00"))
        )

        txn = BalanceTransaction.objects.get(user=user)
        assert txn.amount == Decimal("-20.00")
        assert txn.transaction_type == BalanceTransaction.Type.PARLAY_PLACEMENT

    def test_place_insufficient_balance_raises(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("5.00"))
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, home_moneyline=-150)
        OddsFactory(game=g2, away_moneyline=130)

        with pytest.raises(InsufficientBalanceError):
            (
                ParlayBuilder("nba")
                .add_leg(g1.pk, "HOME", market="MONEYLINE")
                .add_leg(g2.pk, "AWAY", market="MONEYLINE")
                .place(user, stake=Decimal("20.00"))
            )

    def test_place_insufficient_balance_rolls_back(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("5.00"))
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, home_moneyline=-150)
        OddsFactory(game=g2, away_moneyline=130)

        with pytest.raises(InsufficientBalanceError):
            (
                ParlayBuilder("nba")
                .add_leg(g1.pk, "HOME", market="MONEYLINE")
                .add_leg(g2.pk, "AWAY", market="MONEYLINE")
                .place(user, stake=Decimal("20.00"))
            )

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("5.00")
        assert Parlay.objects.count() == 0

    def test_place_leg_fields_correct(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, home_moneyline=-150)
        OddsFactory(game=g2, over_odds=-110, total_line=222.5)

        parlay = (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", market="MONEYLINE")
            .add_leg(g2.pk, "OVER", market="TOTAL")
            .place(user, stake=Decimal("10.00"))
        )

        legs = list(parlay.legs.order_by("created_at"))

        assert legs[0].game == g1
        assert legs[0].market == BetSlip.Market.MONEYLINE
        assert legs[0].selection == "HOME"
        # American → decimal → American can lose ±1 due to rounding
        assert abs(legs[0].odds_at_placement - (-150)) <= 1
        assert legs[0].line is None
        assert legs[0].status == BetStatus.PENDING

        assert legs[1].game == g2
        assert legs[1].market == BetSlip.Market.TOTAL
        assert legs[1].selection == "OVER"
        assert abs(legs[1].odds_at_placement - (-110)) <= 1
        assert legs[1].line == 222.5

    def test_place_with_spread_market(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, spread_home=-110, spread_line=-3.5)
        OddsFactory(game=g2, spread_away=-110, spread_line=3.5)

        parlay = (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", market="SPREAD")
            .add_leg(g2.pk, "AWAY", market="SPREAD")
            .place(user, stake=Decimal("10.00"))
        )

        legs = list(parlay.legs.order_by("created_at"))
        assert legs[0].market == BetSlip.Market.SPREAD
        assert legs[0].line == -3.5
        assert legs[1].line == 3.5

    def test_place_combined_odds_stored_as_american(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        g1 = GameFactory()
        g2 = GameFactory()
        OddsFactory(game=g1, home_moneyline=-150)
        OddsFactory(game=g2, away_moneyline=200)

        parlay = (
            ParlayBuilder("nba")
            .add_leg(g1.pk, "HOME", market="MONEYLINE")
            .add_leg(g2.pk, "AWAY", market="MONEYLINE")
            .place(user, stake=Decimal("10.00"))
        )

        # combined decimal = 1.667 * 3.0 = 5.0 → American = +400
        combined_decimal = american_to_decimal(-150) * american_to_decimal(200)
        expected_american = decimal_to_american(
            combined_decimal.quantize(Decimal("0.01"))
        )
        assert parlay.combined_odds == expected_american
