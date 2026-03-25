from django.contrib import admin

from nba.betting.models import BetSlip, Parlay, ParlayLeg


@admin.register(BetSlip)
class BetSlipAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "game",
        "market",
        "selection",
        "odds_at_placement",
        "stake",
        "status",
        "payout",
    ]
    list_filter = ["status", "market", "selection"]
    search_fields = ["user__email"]
    raw_id_fields = ["user", "game"]


class ParlayLegInline(admin.TabularInline):
    model = ParlayLeg
    extra = 0
    readonly_fields = ["game", "market", "selection", "odds_at_placement", "status"]
    can_delete = False


@admin.register(Parlay)
class ParlayAdmin(admin.ModelAdmin):
    list_display = ["user", "stake", "combined_odds", "status", "payout", "created_at"]
    list_filter = ["status"]
    search_fields = ["user__email", "id_hash"]
    raw_id_fields = ["user"]
    inlines = [ParlayLegInline]
    readonly_fields = ["id_hash", "combined_odds", "max_payout", "payout"]
