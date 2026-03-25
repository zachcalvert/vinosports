from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.betting.models import AbstractBetSlip, AbstractParlay, AbstractParlayLeg


class BetSlip(AbstractBetSlip):
    """EPL bet slip — 1X2 market (Home Win / Draw / Away Win)."""

    class Selection(models.TextChoices):
        HOME_WIN = "HOME_WIN", _("Home Win")
        DRAW = "DRAW", _("Draw")
        AWAY_WIN = "AWAY_WIN", _("Away Win")

    match = models.ForeignKey(
        "epl_matches.Match",
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
    """EPL parlay — combined decimal odds."""

    combined_odds = models.DecimalField(
        _("combined odds"), max_digits=12, decimal_places=2
    )

    def __str__(self):
        return f"{self.user} — parlay #{self.id_hash} @ {self.combined_odds}x"


class ParlayLeg(AbstractParlayLeg):
    """EPL parlay leg — one selection within a parlay."""

    parlay = models.ForeignKey(
        Parlay,
        on_delete=models.CASCADE,
        related_name="legs",
        verbose_name=_("parlay"),
    )
    match = models.ForeignKey(
        "epl_matches.Match",
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
