"""League-aware ParlayBuilder — single entry point for creating parlays across all leagues.

Usage:
    from vinosports.betting.parlay_builder import ParlayBuilder

    parlay = (
        ParlayBuilder("epl")
        .add_leg(match_id, "HOME_WIN")
        .add_leg(match_id_2, "DRAW")
        .add_leg(match_id_3, "AWAY_WIN")
        .place(user, stake=Decimal("10.00"))
    )

    # Or preview without placing (for featured parlays):
    preview = (
        ParlayBuilder("nba")
        .add_leg(game_id, "HOME", market="MONEYLINE")
        .add_leg(game_id_2, "AWAY", market="MONEYLINE")
        .preview(stake=Decimal("10.00"))
    )
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from vinosports.betting.balance import log_transaction
from vinosports.betting.constants import (
    PARLAY_MAX_LEGS,
    PARLAY_MAX_PAYOUT,
    PARLAY_MIN_LEGS,
)
from vinosports.betting.models import BalanceTransaction, UserBalance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ParlayError(Exception):
    """Base error for parlay builder failures."""


class ParlayValidationError(ParlayError):
    """One or more validation checks failed."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class InsufficientBalanceError(ParlayError):
    pass


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LegData:
    """League-agnostic input for a single parlay leg."""

    event_id: int
    selection: str
    odds: Decimal | None = None  # decimal odds; None → adapter resolves
    extras: dict = field(default_factory=dict)


@dataclass
class ResolvedLeg:
    """A leg after validation and odds resolution."""

    leg: LegData
    event: object  # Match or Game model instance
    decimal_odds: Decimal


@dataclass
class ParlayPreview:
    """Result of preview() — parlay details without placement."""

    legs: list[ResolvedLeg]
    combined_odds: Decimal
    potential_payout: Decimal
    league: str


# ---------------------------------------------------------------------------
# League adapter ABC
# ---------------------------------------------------------------------------


class LeagueAdapter(ABC):
    """Each league implements this to handle sport-specific parlay logic.

    All odds passed to/from the builder are in **decimal** format.
    Adapters convert to/from native format (e.g. American) only at the
    model boundary.
    """

    @abstractmethod
    def fetch_events(self, event_ids: list[int]) -> dict[int, object]:
        """Bulk-fetch match/game objects. Returns {pk: model instance}."""

    @abstractmethod
    def is_bettable(self, event: object) -> bool:
        """Is this event open for betting?"""

    @abstractmethod
    def resolve_odds(self, event: object, selection: str, extras: dict) -> Decimal:
        """Look up best available odds for a selection. Returns decimal odds.

        Raises ParlayValidationError if no odds are available.
        """

    @abstractmethod
    def create_parlay(
        self,
        user,
        stake: Decimal,
        combined_decimal_odds: Decimal,
        max_payout: Decimal,
    ):
        """Create and save the league's concrete Parlay model. Returns the instance."""

    @abstractmethod
    def build_leg(self, parlay, event: object, leg: LegData, decimal_odds: Decimal):
        """Return an **unsaved** ParlayLeg instance (for bulk_create)."""

    @abstractmethod
    def get_leg_model(self):
        """Return the concrete ParlayLeg model class (for bulk_create)."""


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

_registry: dict[str, type[LeagueAdapter]] = {}


def register_adapter(league: str, adapter_cls: type[LeagueAdapter]):
    _registry[league] = adapter_cls


def get_adapter(league: str) -> LeagueAdapter:
    if league not in _registry:
        raise ParlayError(f"No parlay adapter registered for league '{league}'")
    return _registry[league]()


# ---------------------------------------------------------------------------
# ParlayBuilder
# ---------------------------------------------------------------------------


class ParlayBuilder:
    """Fluent builder for constructing and placing parlays."""

    def __init__(self, league: str):
        self.league = league
        self.adapter = get_adapter(league)
        self._legs: list[LegData] = []

    def add_leg(
        self,
        event_id: int,
        selection: str,
        odds: Decimal | None = None,
        **extras,
    ) -> ParlayBuilder:
        """Add a leg to the parlay.

        Args:
            event_id: PK of the match/game.
            selection: e.g. "HOME_WIN", "HOME", "OVER".
            odds: Decimal odds. If None, adapter fetches best available.
            **extras: League-specific fields (market, line, etc.).
        """
        self._legs.append(LegData(event_id, selection, odds, extras))
        return self

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Check structural validity. Returns list of error strings (empty = valid)."""
        errors: list[str] = []

        if len(self._legs) < PARLAY_MIN_LEGS:
            errors.append(f"Parlay requires at least {PARLAY_MIN_LEGS} legs.")
        if len(self._legs) > PARLAY_MAX_LEGS:
            errors.append(f"Parlay allows at most {PARLAY_MAX_LEGS} legs.")

        seen_events = set()
        for leg in self._legs:
            if leg.event_id in seen_events:
                errors.append(f"Duplicate event {leg.event_id} in parlay.")
            seen_events.add(leg.event_id)

        return errors

    # ------------------------------------------------------------------
    # Internal: resolve all legs
    # ------------------------------------------------------------------

    def _resolve_legs(self) -> list[ResolvedLeg]:
        """Validate events and resolve odds for all legs.

        Raises ParlayValidationError on any issue.
        """
        errors = self.validate()
        if errors:
            raise ParlayValidationError(errors)

        event_ids = [leg.event_id for leg in self._legs]
        events = self.adapter.fetch_events(event_ids)

        resolved: list[ResolvedLeg] = []
        for leg in self._legs:
            event = events.get(leg.event_id)
            if event is None:
                errors.append(f"Event {leg.event_id} not found.")
                continue

            if not self.adapter.is_bettable(event):
                errors.append(f"Event {leg.event_id} is not open for betting.")
                continue

            if leg.odds is not None:
                decimal_odds = leg.odds
            else:
                decimal_odds = self.adapter.resolve_odds(
                    event, leg.selection, leg.extras
                )

            resolved.append(
                ResolvedLeg(leg=leg, event=event, decimal_odds=decimal_odds)
            )

        if errors:
            raise ParlayValidationError(errors)

        return resolved

    @staticmethod
    def _compute_combined_odds(resolved: list[ResolvedLeg]) -> Decimal:
        combined = Decimal("1")
        for r in resolved:
            combined *= r.decimal_odds
        return combined.quantize(Decimal("0.01"))

    # ------------------------------------------------------------------
    # Preview (no side effects)
    # ------------------------------------------------------------------

    def preview(self, stake: Decimal = Decimal("10.00")) -> ParlayPreview:
        """Compute combined odds and potential payout without placing.

        Useful for featured/promoted parlays.
        """
        resolved = self._resolve_legs()
        combined = self._compute_combined_odds(resolved)
        potential_payout = min(stake * combined, PARLAY_MAX_PAYOUT)

        return ParlayPreview(
            legs=resolved,
            combined_odds=combined,
            potential_payout=potential_payout.quantize(Decimal("0.01")),
            league=self.league,
        )

    # ------------------------------------------------------------------
    # Place (atomic: validate → deduct balance → create models)
    # ------------------------------------------------------------------

    def place(self, user, stake: Decimal):
        """Place the parlay. Returns the created Parlay model instance.

        Raises:
            ParlayValidationError: Invalid legs.
            InsufficientBalanceError: User can't afford the stake.
            ParlayError: Other failures.
        """
        resolved = self._resolve_legs()
        combined = self._compute_combined_odds(resolved)
        max_payout = min(stake * combined, PARLAY_MAX_PAYOUT).quantize(Decimal("0.01"))

        try:
            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(user=user)
                if balance.balance < stake:
                    raise InsufficientBalanceError(
                        f"Balance {balance.balance} < stake {stake}"
                    )

                log_transaction(
                    balance,
                    -stake,
                    BalanceTransaction.Type.PARLAY_PLACEMENT,
                    f"Parlay with {len(resolved)} legs",
                )

                parlay = self.adapter.create_parlay(user, stake, combined, max_payout)

                LegModel = self.adapter.get_leg_model()
                LegModel.objects.bulk_create(
                    [
                        self.adapter.build_leg(parlay, r.event, r.leg, r.decimal_odds)
                        for r in resolved
                    ]
                )

                logger.info(
                    "Parlay placed: user=%s league=%s legs=%d combined=%s stake=%s",
                    user,
                    self.league,
                    len(resolved),
                    combined,
                    stake,
                )

                return parlay

        except UserBalance.DoesNotExist:
            raise ParlayError(f"No balance record for user {user}")
