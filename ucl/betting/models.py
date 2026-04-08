from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.betting.models import (
    AbstractBetSlip,
    AbstractFuturesBet,
    AbstractFuturesMarket,
    AbstractFuturesOutcome,
    AbstractParlay,
    AbstractParlayLeg,
)


class BetSlip(AbstractBetSlip):
    """UCL bet slip — 1X2 market (Home Win / Draw / Away Win).

    Bets settle on the 90-minute result only. In knockout second legs,
    a 1-1 draw after 90 minutes settles DRAW bets as winners, regardless
    of aggregate, extra time, or penalties.
    """

    class Selection(models.TextChoices):
        HOME_WIN = "HOME_WIN", _("Home Win")
        DRAW = "DRAW", _("Draw")
        AWAY_WIN = "AWAY_WIN", _("Away Win")

    match = models.ForeignKey(
        "ucl_matches.Match",
        on_delete=models.CASCADE,
        related_name="bets",
        verbose_name=_("match"),
    )
    selection = models.CharField(
        _("selection"),
        max_length=10,
        choices=Selection.choices,
    )
    odds_at_placement = models.DecimalField(
        _("odds at placement"), max_digits=6, decimal_places=2
    )

    def __str__(self):
        return f"{self.user} — {self.get_selection_display()} on {self.match} @ {self.odds_at_placement}"


class Parlay(AbstractParlay):
    """UCL parlay — combined decimal odds."""

    combined_odds = models.DecimalField(
        _("combined odds"), max_digits=12, decimal_places=2
    )

    def __str__(self):
        return f"{self.user} — parlay #{self.id_hash} @ {self.combined_odds}x"


class ParlayLeg(AbstractParlayLeg):
    """UCL parlay leg — one selection within a parlay."""

    parlay = models.ForeignKey(
        Parlay,
        on_delete=models.CASCADE,
        related_name="legs",
        verbose_name=_("parlay"),
    )
    match = models.ForeignKey(
        "ucl_matches.Match",
        on_delete=models.CASCADE,
        related_name="parlay_legs",
        verbose_name=_("match"),
    )
    selection = models.CharField(
        _("selection"),
        max_length=10,
        choices=BetSlip.Selection.choices,
    )
    odds_at_placement = models.DecimalField(
        _("odds at placement"), max_digits=6, decimal_places=2
    )

    class Meta(AbstractParlayLeg.Meta):
        unique_together = [("parlay", "match")]

    def __str__(self):
        return f"{self.parlay.id_hash} — {self.get_selection_display()} on {self.match} @ {self.odds_at_placement}"


class FuturesMarket(AbstractFuturesMarket):
    """UCL futures market — tournament winner, finalist, top 8 (auto-qualify for R16)."""

    class MarketType(models.TextChoices):
        WINNER = "WINNER", _("Tournament Winner")
        FINALIST = "FINALIST", _("Finalist")
        TOP_8 = "TOP_8", _("League Phase Top 8")

    market_type = models.CharField(
        _("market type"),
        max_length=15,
        choices=MarketType.choices,
    )

    class Meta(AbstractFuturesMarket.Meta):
        unique_together = [("season", "market_type")]
        verbose_name = "futures market"
        verbose_name_plural = "futures markets"


class FuturesOutcome(AbstractFuturesOutcome):
    """UCL futures outcome — one team's odds within a market."""

    market = models.ForeignKey(
        FuturesMarket,
        on_delete=models.CASCADE,
        related_name="outcomes",
        verbose_name=_("market"),
    )
    team = models.ForeignKey(
        "ucl_matches.Team",
        on_delete=models.CASCADE,
        related_name="futures_outcomes",
        verbose_name=_("team"),
    )
    odds = models.DecimalField(
        _("odds"),
        max_digits=8,
        decimal_places=2,
        help_text=_("Decimal odds (e.g., 2.50)"),
    )
    odds_updated_at = models.DateTimeField(_("odds updated at"), auto_now=True)

    class Meta(AbstractFuturesOutcome.Meta):
        unique_together = [("market", "team")]
        ordering = ["odds"]

    def __str__(self):
        return f"{self.team.name} @ {self.odds} ({self.market.name})"


class FuturesBet(AbstractFuturesBet):
    """UCL futures bet — a user's wager on a futures outcome."""

    outcome = models.ForeignKey(
        FuturesOutcome,
        on_delete=models.CASCADE,
        related_name="bets",
        verbose_name=_("outcome"),
    )
    odds_at_placement = models.DecimalField(
        _("odds at placement"),
        max_digits=8,
        decimal_places=2,
        help_text=_("Decimal odds locked at bet placement"),
    )

    def __str__(self):
        return f"{self.user} — {self.outcome.team.name} @ {self.odds_at_placement} ({self.outcome.market.name})"
