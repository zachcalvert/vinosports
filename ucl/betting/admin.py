from django.contrib import admin

from .models import (
    BetSlip,
    FuturesBet,
    FuturesMarket,
    FuturesOutcome,
    Parlay,
    ParlayLeg,
)


class ParlayLegInline(admin.TabularInline):
    model = ParlayLeg
    extra = 0
    raw_id_fields = ["match"]


@admin.register(BetSlip)
class BetSlipAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "match",
        "selection",
        "stake",
        "odds_at_placement",
        "status",
        "created_at",
    ]
    list_filter = ["status", "selection"]
    raw_id_fields = ["user", "match"]


@admin.register(Parlay)
class ParlayAdmin(admin.ModelAdmin):
    list_display = ["user", "combined_odds", "stake", "status", "created_at"]
    list_filter = ["status"]
    raw_id_fields = ["user"]
    inlines = [ParlayLegInline]


@admin.register(FuturesMarket)
class FuturesMarketAdmin(admin.ModelAdmin):
    list_display = ["name", "market_type", "season", "status"]
    list_filter = ["market_type", "status"]


@admin.register(FuturesOutcome)
class FuturesOutcomeAdmin(admin.ModelAdmin):
    list_display = ["team", "market", "odds", "odds_updated_at"]
    list_filter = ["market__market_type"]
    raw_id_fields = ["team"]


@admin.register(FuturesBet)
class FuturesBetAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "outcome",
        "stake",
        "odds_at_placement",
        "status",
        "created_at",
    ]
    list_filter = ["status"]
    raw_id_fields = ["user", "outcome"]
