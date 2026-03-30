from decimal import Decimal

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
    """NBA bet slip — moneyline, spread, and total markets with American odds."""

    class Market(models.TextChoices):
        MONEYLINE = "MONEYLINE", _("Moneyline")
        SPREAD = "SPREAD", _("Spread")
        TOTAL = "TOTAL", _("Total")

    class Selection(models.TextChoices):
        HOME = "HOME", _("Home")
        AWAY = "AWAY", _("Away")
        OVER = "OVER", _("Over")
        UNDER = "UNDER", _("Under")

    game = models.ForeignKey(
        "nba_games.Game",
        on_delete=models.CASCADE,
        related_name="bets",
        verbose_name=_("game"),
    )
    market = models.CharField(
        _("market"),
        max_length=10,
        choices=Market.choices,
    )
    selection = models.CharField(
        _("selection"),
        max_length=10,
        choices=Selection.choices,
    )
    odds_at_placement = models.IntegerField(
        _("odds at placement"),
        help_text=_("American odds (e.g., -110, +150)"),
    )
    line = models.FloatField(
        _("line"),
        null=True,
        blank=True,
        help_text=_("Spread or total line (e.g., -3.5 or 224.5)"),
    )

    def __str__(self):
        return f"{self.user} — {self.get_market_display()} {self.get_selection_display()} on {self.game} @ {self.odds_at_placement}"

    def calculate_payout(self):
        odds = self.odds_at_placement
        if odds > 0:
            return self.stake * Decimal(odds) / 100 + self.stake
        else:
            return self.stake * Decimal(100) / Decimal(abs(odds)) + self.stake


class Parlay(AbstractParlay):
    """NBA parlay — combined American odds."""

    combined_odds = models.IntegerField(
        _("combined odds"),
        help_text=_("Combined American odds"),
    )

    def __str__(self):
        return f"{self.user} — parlay #{self.id_hash} @ {self.combined_odds}"


class ParlayLeg(AbstractParlayLeg):
    """NBA parlay leg."""

    parlay = models.ForeignKey(
        Parlay,
        on_delete=models.CASCADE,
        related_name="legs",
        verbose_name=_("parlay"),
    )
    game = models.ForeignKey(
        "nba_games.Game",
        on_delete=models.CASCADE,
        related_name="parlay_legs",
        verbose_name=_("game"),
    )
    market = models.CharField(
        _("market"),
        max_length=10,
        choices=BetSlip.Market.choices,
    )
    selection = models.CharField(
        _("selection"),
        max_length=10,
        choices=BetSlip.Selection.choices,
    )
    odds_at_placement = models.IntegerField(_("odds at placement"))
    line = models.FloatField(_("line"), null=True, blank=True)

    class Meta(AbstractParlayLeg.Meta):
        unique_together = [("parlay", "game")]

    def __str__(self):
        return f"{self.parlay.id_hash} — {self.get_market_display()} {self.get_selection_display()} on {self.game}"


class FuturesMarket(AbstractFuturesMarket):
    """NBA futures market — champion, conference winner."""

    class MarketType(models.TextChoices):
        CHAMPION = "CHAMPION", _("NBA Champion")
        CONFERENCE = "CONFERENCE", _("Conference Winner")

    market_type = models.CharField(
        _("market type"),
        max_length=12,
        choices=MarketType.choices,
    )
    conference = models.CharField(
        _("conference"),
        max_length=4,
        blank=True,
        default="",
        help_text=_("Only for CONFERENCE market type (EAST or WEST)"),
    )

    class Meta(AbstractFuturesMarket.Meta):
        unique_together = [("season", "market_type", "conference")]
        verbose_name = "futures market"
        verbose_name_plural = "futures markets"


class FuturesOutcome(AbstractFuturesOutcome):
    """NBA futures outcome — one team's odds within a market."""

    market = models.ForeignKey(
        FuturesMarket,
        on_delete=models.CASCADE,
        related_name="outcomes",
        verbose_name=_("market"),
    )
    team = models.ForeignKey(
        "nba_games.Team",
        on_delete=models.CASCADE,
        related_name="futures_outcomes",
        verbose_name=_("team"),
    )
    odds = models.IntegerField(
        _("odds"),
        help_text=_("American odds (e.g., +350, -150)"),
    )
    odds_updated_at = models.DateTimeField(_("odds updated at"), auto_now=True)

    class Meta(AbstractFuturesOutcome.Meta):
        unique_together = [("market", "team")]
        ordering = ["odds"]

    def __str__(self):
        sign = "+" if self.odds > 0 else ""
        return f"{self.team.name} {sign}{self.odds} ({self.market.name})"

    def calculate_payout(self, stake):
        """Calculate potential payout from American odds."""
        if self.odds > 0:
            return stake * Decimal(self.odds) / 100 + stake
        else:
            return stake * Decimal(100) / Decimal(abs(self.odds)) + stake


class FuturesBet(AbstractFuturesBet):
    """NBA futures bet — a user's wager on a futures outcome."""

    outcome = models.ForeignKey(
        FuturesOutcome,
        on_delete=models.CASCADE,
        related_name="bets",
        verbose_name=_("outcome"),
    )
    odds_at_placement = models.IntegerField(
        _("odds at placement"),
        help_text=_("American odds locked at bet placement"),
    )

    def __str__(self):
        sign = "+" if self.odds_at_placement > 0 else ""
        return f"{self.user} — {self.outcome.team.name} {sign}{self.odds_at_placement} ({self.outcome.market.name})"

    def calculate_payout(self):
        """Calculate potential payout from locked American odds."""
        odds = self.odds_at_placement
        if odds > 0:
            return self.stake * Decimal(odds) / 100 + self.stake
        else:
            return self.stake * Decimal(100) / Decimal(abs(odds)) + self.stake
