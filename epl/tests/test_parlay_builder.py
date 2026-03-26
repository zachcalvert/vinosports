"""Tests for ParlayBuilder with the EPL adapter."""

from decimal import Decimal

import pytest

from epl.betting.models import Parlay, ParlayLeg
from epl.matches.models import Match
from vinosports.betting.models import BalanceTransaction, BetStatus, UserBalance
from vinosports.betting.parlay_builder import (
    InsufficientBalanceError,
    ParlayBuilder,
    ParlayValidationError,
)

from .factories import MatchFactory, OddsFactory, UserBalanceFactory, UserFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestParlayBuilderValidation:
    def test_too_few_legs(self):
        builder = ParlayBuilder("epl")
        match = MatchFactory()
        builder.add_leg(match.pk, "HOME_WIN")

        errors = builder.validate()
        assert any("at least" in e for e in errors)

    def test_too_many_legs(self):
        builder = ParlayBuilder("epl")
        for _ in range(11):
            match = MatchFactory()
            builder.add_leg(match.pk, "HOME_WIN")

        errors = builder.validate()
        assert any("at most" in e for e in errors)

    def test_duplicate_event_rejected(self):
        match = MatchFactory()
        builder = ParlayBuilder("epl")
        builder.add_leg(match.pk, "HOME_WIN")
        builder.add_leg(match.pk, "DRAW")

        errors = builder.validate()
        assert any("Duplicate" in e for e in errors)

    def test_valid_legs_pass(self):
        builder = ParlayBuilder("epl")
        for _ in range(3):
            match = MatchFactory()
            builder.add_leg(match.pk, "HOME_WIN")

        assert builder.validate() == []

    def test_nonexistent_event_raises(self):
        builder = ParlayBuilder("epl")
        builder.add_leg(999999, "HOME_WIN")
        builder.add_leg(999998, "DRAW")

        with pytest.raises(ParlayValidationError, match="not found"):
            builder.preview()

    def test_unbettable_event_raises(self):
        m1 = MatchFactory(status=Match.Status.FINISHED)
        m2 = MatchFactory()
        OddsFactory(match=m2)

        builder = ParlayBuilder("epl")
        builder.add_leg(m1.pk, "HOME_WIN")
        builder.add_leg(m2.pk, "DRAW")

        with pytest.raises(ParlayValidationError, match="not open"):
            builder.preview()

    def test_invalid_selection_raises(self):
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1)
        OddsFactory(match=m2)

        builder = ParlayBuilder("epl")
        builder.add_leg(m1.pk, "HOME_WIN")
        builder.add_leg(m2.pk, "INVALID")

        with pytest.raises(ParlayValidationError, match="Invalid EPL selection"):
            builder.preview()

    def test_no_odds_available_raises(self):
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1)
        # No odds for m2

        builder = ParlayBuilder("epl")
        builder.add_leg(m1.pk, "HOME_WIN")
        builder.add_leg(m2.pk, "DRAW")

        with pytest.raises(ParlayValidationError, match="No odds"):
            builder.preview()


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class TestParlayBuilderPreview:
    def test_preview_computes_combined_odds(self):
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, draw=Decimal("3.00"))

        preview = (
            ParlayBuilder("epl")
            .add_leg(m1.pk, "HOME_WIN")
            .add_leg(m2.pk, "DRAW")
            .preview(stake=Decimal("10.00"))
        )

        assert preview.combined_odds == Decimal("6.00")
        assert preview.potential_payout == Decimal("60.00")
        assert preview.league == "epl"
        assert len(preview.legs) == 2

    def test_preview_uses_best_odds_across_bookmakers(self):
        match = MatchFactory()
        OddsFactory(match=match, home_win=Decimal("2.00"))
        OddsFactory(match=match, home_win=Decimal("1.80"), bookmaker="Alt")

        m2 = MatchFactory()
        OddsFactory(match=m2, away_win=Decimal("3.00"))

        preview = (
            ParlayBuilder("epl")
            .add_leg(match.pk, "HOME_WIN")
            .add_leg(m2.pk, "AWAY_WIN")
            .preview(stake=Decimal("10.00"))
        )

        # Min(home_win) = 1.80 * 3.00 = 5.40
        assert preview.combined_odds == Decimal("5.40")

    def test_preview_caps_potential_payout(self):
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("100.00"))
        OddsFactory(match=m2, away_win=Decimal("100.00"))

        preview = (
            ParlayBuilder("epl")
            .add_leg(m1.pk, "HOME_WIN")
            .add_leg(m2.pk, "AWAY_WIN")
            .preview(stake=Decimal("100.00"))
        )

        # 100 * 10000 = 1,000,000 but capped at 50,000
        assert preview.potential_payout == Decimal("50000.00")

    def test_preview_has_no_side_effects(self):
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, draw=Decimal("3.00"))

        builder = ParlayBuilder("epl")
        builder.add_leg(m1.pk, "HOME_WIN")
        builder.add_leg(m2.pk, "DRAW")
        builder.preview(stake=Decimal("10.00"))

        assert Parlay.objects.count() == 0
        assert ParlayLeg.objects.count() == 0

    def test_preview_with_explicit_odds_skips_resolution(self):
        m1 = MatchFactory()
        m2 = MatchFactory()
        # No odds in DB — explicit odds provided

        preview = (
            ParlayBuilder("epl")
            .add_leg(m1.pk, "HOME_WIN", odds=Decimal("2.50"))
            .add_leg(m2.pk, "DRAW", odds=Decimal("4.00"))
            .preview(stake=Decimal("10.00"))
        )

        assert preview.combined_odds == Decimal("10.00")
        assert preview.potential_payout == Decimal("100.00")


# ---------------------------------------------------------------------------
# Place
# ---------------------------------------------------------------------------


class TestParlayBuilderPlace:
    def test_place_creates_parlay_and_legs(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        m1 = MatchFactory()
        m2 = MatchFactory()
        m3 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, draw=Decimal("3.00"))
        OddsFactory(match=m3, away_win=Decimal("2.50"))

        parlay = (
            ParlayBuilder("epl")
            .add_leg(m1.pk, "HOME_WIN")
            .add_leg(m2.pk, "DRAW")
            .add_leg(m3.pk, "AWAY_WIN")
            .place(user, stake=Decimal("20.00"))
        )

        assert parlay.pk is not None
        assert parlay.user == user
        assert parlay.stake == Decimal("20.00")
        assert parlay.combined_odds == Decimal("15.00")
        assert parlay.status == BetStatus.PENDING
        assert parlay.legs.count() == 3

    def test_place_deducts_balance(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, draw=Decimal("3.00"))

        ParlayBuilder("epl").add_leg(m1.pk, "HOME_WIN").add_leg(m2.pk, "DRAW").place(
            user, stake=Decimal("20.00")
        )

        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("480.00")

    def test_place_creates_transaction_record(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, draw=Decimal("3.00"))

        ParlayBuilder("epl").add_leg(m1.pk, "HOME_WIN").add_leg(m2.pk, "DRAW").place(
            user, stake=Decimal("20.00")
        )

        txn = BalanceTransaction.objects.get(user=user)
        assert txn.amount == Decimal("-20.00")
        assert txn.transaction_type == BalanceTransaction.Type.PARLAY_PLACEMENT

    def test_place_sets_max_payout(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, draw=Decimal("3.00"))

        parlay = (
            ParlayBuilder("epl")
            .add_leg(m1.pk, "HOME_WIN")
            .add_leg(m2.pk, "DRAW")
            .place(user, stake=Decimal("20.00"))
        )

        # 20 * 6.00 = 120.00
        assert parlay.max_payout == Decimal("120.00")

    def test_place_caps_max_payout(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("10000.00"))
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("100.00"))
        OddsFactory(match=m2, away_win=Decimal("100.00"))

        parlay = (
            ParlayBuilder("epl")
            .add_leg(m1.pk, "HOME_WIN")
            .add_leg(m2.pk, "AWAY_WIN")
            .place(user, stake=Decimal("100.00"))
        )

        assert parlay.max_payout == Decimal("50000.00")

    def test_place_insufficient_balance_raises(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("5.00"))
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, draw=Decimal("3.00"))

        with pytest.raises(InsufficientBalanceError):
            (
                ParlayBuilder("epl")
                .add_leg(m1.pk, "HOME_WIN")
                .add_leg(m2.pk, "DRAW")
                .place(user, stake=Decimal("20.00"))
            )

    def test_place_insufficient_balance_no_side_effects(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("5.00"))
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, draw=Decimal("3.00"))

        with pytest.raises(InsufficientBalanceError):
            (
                ParlayBuilder("epl")
                .add_leg(m1.pk, "HOME_WIN")
                .add_leg(m2.pk, "DRAW")
                .place(user, stake=Decimal("20.00"))
            )

        # Balance untouched, no models created
        balance = UserBalance.objects.get(user=user)
        assert balance.balance == Decimal("5.00")
        assert Parlay.objects.count() == 0

    def test_place_with_explicit_odds(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        m1 = MatchFactory()
        m2 = MatchFactory()

        parlay = (
            ParlayBuilder("epl")
            .add_leg(m1.pk, "HOME_WIN", odds=Decimal("2.50"))
            .add_leg(m2.pk, "DRAW", odds=Decimal("4.00"))
            .place(user, stake=Decimal("10.00"))
        )

        assert parlay.combined_odds == Decimal("10.00")
        assert parlay.legs.count() == 2

    def test_place_leg_fields_correct(self):
        user = UserFactory()
        UserBalanceFactory(user=user, balance=Decimal("500.00"))
        m1 = MatchFactory()
        m2 = MatchFactory()
        OddsFactory(match=m1, home_win=Decimal("2.00"))
        OddsFactory(match=m2, draw=Decimal("3.00"))

        parlay = (
            ParlayBuilder("epl")
            .add_leg(m1.pk, "HOME_WIN")
            .add_leg(m2.pk, "DRAW")
            .place(user, stake=Decimal("10.00"))
        )

        legs = list(parlay.legs.order_by("created_at"))
        assert legs[0].match == m1
        assert legs[0].selection == "HOME_WIN"
        assert legs[0].odds_at_placement == Decimal("2.00")
        assert legs[0].status == BetStatus.PENDING

        assert legs[1].match == m2
        assert legs[1].selection == "DRAW"
        assert legs[1].odds_at_placement == Decimal("3.00")

    def test_fluent_api_chaining(self):
        builder = ParlayBuilder("epl")
        m1 = MatchFactory()
        m2 = MatchFactory()

        result = builder.add_leg(m1.pk, "HOME_WIN").add_leg(m2.pk, "DRAW")
        assert result is builder
