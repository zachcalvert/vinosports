from django.contrib import admin

from worldcup.betting.models import (
    BetSlip,
    FuturesBet,
    FuturesMarket,
    FuturesOutcome,
    Parlay,
    ParlayLeg,
)


@admin.register(BetSlip)
class BetSlipAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "match",
        "selection",
        "odds_at_placement",
        "stake",
        "status",
        "payout",
    ]
    list_filter = ["status", "selection"]
    search_fields = ["user__email"]
    raw_id_fields = ["user", "match"]


class ParlayLegInline(admin.TabularInline):
    model = ParlayLeg
    extra = 0
    readonly_fields = ["match", "selection", "odds_at_placement", "status"]
    can_delete = False


@admin.register(Parlay)
class ParlayAdmin(admin.ModelAdmin):
    list_display = ["user", "stake", "combined_odds", "status", "payout", "created_at"]
    list_filter = ["status"]
    search_fields = ["user__email", "id_hash"]
    raw_id_fields = ["user"]
    inlines = [ParlayLegInline]
    readonly_fields = ["id_hash", "combined_odds", "max_payout", "payout"]


class FuturesOutcomeInline(admin.TabularInline):
    model = FuturesOutcome
    extra = 0
    fields = ["team", "odds", "is_active", "is_winner"]
    readonly_fields = ["odds"]


@admin.register(FuturesMarket)
class FuturesMarketAdmin(admin.ModelAdmin):
    list_display = ["name", "market_type", "group", "season", "status", "settled_at"]
    list_filter = ["status", "market_type"]
    search_fields = ["name"]
    inlines = [FuturesOutcomeInline]
    readonly_fields = ["id_hash", "settled_at"]


@admin.register(FuturesOutcome)
class FuturesOutcomeAdmin(admin.ModelAdmin):
    list_display = ["team", "market", "odds", "is_active", "is_winner"]
    list_filter = ["market", "is_active", "is_winner"]
    search_fields = ["team__name"]
    raw_id_fields = ["team"]


@admin.register(FuturesBet)
class FuturesBetAdmin(admin.ModelAdmin):
    list_display = ["user", "outcome", "odds_at_placement", "stake", "status", "payout"]
    list_filter = ["status"]
    search_fields = ["user__email", "outcome__team__name"]
    raw_id_fields = ["user", "outcome"]
