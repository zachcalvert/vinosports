from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinosports.core.models import BaseModel

from .constants import PARLAY_MAX_PAYOUT

# ---------------------------------------------------------------------------
# Concrete models — identical across all leagues
# ---------------------------------------------------------------------------


class UserBalance(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="balance",
        verbose_name=_("user"),
    )
    balance = models.DecimalField(
        _("balance"), max_digits=14, decimal_places=2, default=100000.00
    )

    def __str__(self):
        return f"{self.user}: {self.balance}"


class BalanceTransaction(BaseModel):
    class Type(models.TextChoices):
        SIGNUP = "SIGNUP", _("Signup bonus")
        BET_PLACEMENT = "BET_PLACEMENT", _("Bet placed")
        BET_WIN = "BET_WIN", _("Bet won")
        BET_VOID = "BET_VOID", _("Bet voided")
        PARLAY_PLACEMENT = "PARLAY_PLACEMENT", _("Parlay placed")
        PARLAY_WIN = "PARLAY_WIN", _("Parlay won")
        PARLAY_VOID = "PARLAY_VOID", _("Parlay voided")
        CHALLENGE_REWARD = "CHALLENGE_REWARD", _("Challenge reward")
        REWARD = "REWARD", _("Reward")
        BAILOUT = "BAILOUT", _("Bailout")
        PROMO_CODE = "PROMO_CODE", _("Promo code bonus")
        ADMIN_RESET = "ADMIN_RESET", _("Admin reset")
        FUTURES_PLACEMENT = "FUTURES_PLACEMENT", _("Futures bet placed")
        FUTURES_WIN = "FUTURES_WIN", _("Futures bet won")
        FUTURES_VOID = "FUTURES_VOID", _("Futures bet voided")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="balance_transactions",
        verbose_name=_("user"),
    )
    amount = models.DecimalField(_("amount"), max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(
        _("balance after"), max_digits=14, decimal_places=2
    )
    transaction_type = models.CharField(_("type"), max_length=20, choices=Type.choices)
    description = models.CharField(
        _("description"), max_length=200, blank=True, default=""
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        sign = "+" if self.amount >= 0 else ""
        return (
            f"{self.user}: {sign}{self.amount} ({self.get_transaction_type_display()})"
        )


class UserStats(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stats",
        verbose_name=_("user"),
    )
    total_bets = models.PositiveIntegerField(_("total bets"), default=0)
    total_wins = models.PositiveIntegerField(_("total wins"), default=0)
    total_losses = models.PositiveIntegerField(_("total losses"), default=0)
    total_staked = models.DecimalField(
        _("total staked"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    total_payout = models.DecimalField(
        _("total payout"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    net_profit = models.DecimalField(
        _("net profit"), max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    current_streak = models.IntegerField(
        _("current streak"),
        default=0,
        help_text=_("Positive = win streak, negative = loss streak"),
    )
    best_streak = models.PositiveIntegerField(_("best win streak"), default=0)

    class Meta:
        verbose_name_plural = "user stats"

    def __str__(self):
        profit = Decimal(str(self.net_profit))
        sign = "+" if profit >= 0 else ""
        return f"{self.user}: {self.total_wins}W-{self.total_losses}L ({sign}{profit})"

    @property
    def win_rate(self):
        if self.total_bets == 0:
            return Decimal("0.00")
        return (Decimal(self.total_wins) / Decimal(self.total_bets) * 100).quantize(
            Decimal("0.1")
        )


class Badge(BaseModel):
    class Rarity(models.TextChoices):
        COMMON = "common", _("Common")
        UNCOMMON = "uncommon", _("Uncommon")
        RARE = "rare", _("Rare")
        EPIC = "epic", _("Epic")

    slug = models.SlugField(_("slug"), max_length=50, unique=True)
    name = models.CharField(_("name"), max_length=100)
    description = models.CharField(_("description"), max_length=255)
    icon = models.CharField(
        _("icon"),
        max_length=50,
        help_text=_("Phosphor icon name"),
    )
    rarity = models.CharField(
        _("rarity"),
        max_length=10,
        choices=Rarity.choices,
        default=Rarity.COMMON,
    )

    class Meta:
        ordering = ["rarity", "name"]

    def __str__(self):
        return f"{self.icon} {self.name} ({self.rarity})"


class UserBadge(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="badges",
        verbose_name=_("user"),
    )
    badge = models.ForeignKey(
        Badge,
        on_delete=models.CASCADE,
        related_name="user_badges",
        verbose_name=_("badge"),
    )
    earned_at = models.DateTimeField(_("earned at"), auto_now_add=True)

    class Meta:
        ordering = ["-earned_at"]
        unique_together = [("user", "badge")]

    def __str__(self):
        return f"{self.user} — {self.badge.name}"


class Bankruptcy(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bankruptcies",
        verbose_name=_("user"),
    )
    balance_at_bankruptcy = models.DecimalField(
        _("balance at bankruptcy"),
        max_digits=14,
        decimal_places=2,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "bankruptcies"

    def __str__(self):
        return f"{self.user} — bankruptcy #{self.pk} ({self.balance_at_bankruptcy} cr)"


class Bailout(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bailouts",
        verbose_name=_("user"),
    )
    bankruptcy = models.OneToOneField(
        Bankruptcy,
        on_delete=models.CASCADE,
        related_name="bailout",
        verbose_name=_("bankruptcy"),
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=14,
        decimal_places=2,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} — bailout of {self.amount} cr"


# ---------------------------------------------------------------------------
# Abstract models — league projects create concrete versions
# ---------------------------------------------------------------------------


class BetStatus(models.TextChoices):
    """Shared bet status choices used by BetSlip, Parlay, and ParlayLeg."""

    PENDING = "PENDING", _("Pending")
    WON = "WON", _("Won")
    LOST = "LOST", _("Lost")
    VOID = "VOID", _("Void")


class AbstractBetSlip(BaseModel):
    """Abstract base for a single bet.

    League projects must add:
    - A ForeignKey to their match/game model
    - Selection choices and field
    - Odds representation field(s)
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_bets",
        verbose_name=_("user"),
    )
    stake = models.DecimalField(_("stake"), max_digits=14, decimal_places=2)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=BetStatus.choices,
        default=BetStatus.PENDING,
    )
    payout = models.DecimalField(
        _("payout"), max_digits=14, decimal_places=2, null=True, blank=True
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class AbstractParlay(BaseModel):
    """Abstract base for a parlay (accumulator) bet.

    League projects must add combined_odds field(s) appropriate to their
    odds format (decimal for EPL, American for NBA, etc.).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_parlays",
        verbose_name=_("user"),
    )
    stake = models.DecimalField(_("stake"), max_digits=14, decimal_places=2)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=BetStatus.choices,
        default=BetStatus.PENDING,
    )
    payout = models.DecimalField(
        _("payout"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    max_payout = models.DecimalField(
        _("max payout"), max_digits=14, decimal_places=2, default=PARLAY_MAX_PAYOUT
    )
    featured_parlay = models.ForeignKey(
        "betting.FeaturedParlay",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_placed_parlays",
        verbose_name=_("featured parlay"),
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class AbstractParlayLeg(BaseModel):
    """Abstract base for a single leg of a parlay.

    League projects must add:
    - A ForeignKey to their Parlay model
    - A ForeignKey to their match/game model
    - Selection choices and field
    - Odds representation field(s)
    """

    status = models.CharField(
        _("status"),
        max_length=10,
        choices=BetStatus.choices,
        default=BetStatus.PENDING,
    )

    class Meta:
        abstract = True
        ordering = ["created_at"]


class FuturesMarketStatus(models.TextChoices):
    """Status choices for futures markets."""

    OPEN = "OPEN", _("Open")
    SUSPENDED = "SUSPENDED", _("Suspended")
    SETTLED = "SETTLED", _("Settled")
    CANCELLED = "CANCELLED", _("Cancelled")


class AbstractFuturesMarket(BaseModel):
    """Abstract base for a futures market (e.g., "NBA Champion 2025-26").

    League projects must add:
    - A market_type field with league-specific choices
    """

    name = models.CharField(_("name"), max_length=200)
    season = models.CharField(_("season"), max_length=10)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=FuturesMarketStatus.choices,
        default=FuturesMarketStatus.OPEN,
    )
    settled_at = models.DateTimeField(_("settled at"), null=True, blank=True)
    description = models.TextField(_("description"), blank=True, default="")

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.season})"


class AbstractFuturesOutcome(BaseModel):
    """Abstract base for a single outcome within a futures market.

    League projects must add:
    - A ForeignKey to their FuturesMarket model
    - A ForeignKey to their Team model
    - Odds representation field(s) in native format
    - An odds_updated_at DateTimeField
    """

    is_winner = models.BooleanField(_("is winner"), default=False)
    is_active = models.BooleanField(
        _("is active"),
        default=True,
        help_text=_("Deactivate if team is eliminated"),
    )

    class Meta:
        abstract = True


class AbstractFuturesBet(BaseModel):
    """Abstract base for a futures bet.

    League projects must add:
    - A ForeignKey to their FuturesOutcome model
    - Odds at placement field(s) in native format
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_futures_bets",
        verbose_name=_("user"),
    )
    stake = models.DecimalField(_("stake"), max_digits=14, decimal_places=2)
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=BetStatus.choices,
        default=BetStatus.PENDING,
    )
    payout = models.DecimalField(
        _("payout"), max_digits=14, decimal_places=2, null=True, blank=True
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]


# Import concrete models so Django discovers them in this app.
from vinosports.betting.featured import (  # noqa: E402, F401
    FeaturedParlay,
    FeaturedParlayLeg,
)
