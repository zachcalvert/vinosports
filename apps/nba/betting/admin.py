from django.contrib import admin

from betting.models import BetSlip, Parlay, ParlayLeg
from vinosports.betting.models import Badge, UserBadge, UserBalance


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


@admin.register(UserBalance)
class UserBalanceAdmin(admin.ModelAdmin):
    list_display = ["user", "balance"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ["icon", "name", "slug", "rarity"]
    list_filter = ["rarity"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ["user", "badge", "earned_at"]
    list_filter = ["badge__rarity", "badge"]
    search_fields = ["user__email", "badge__name"]
    raw_id_fields = ["user"]
