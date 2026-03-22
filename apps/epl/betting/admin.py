from django.contrib import admin

from betting.models import BetSlip, Parlay, ParlayLeg
from matches.models import Odds
from vinosports.betting.models import Badge, UserBadge, UserBalance


@admin.register(Odds)
class OddsAdmin(admin.ModelAdmin):
    list_display = ["match", "bookmaker", "home_win", "draw", "away_win", "fetched_at"]
    list_filter = ["bookmaker"]
    search_fields = ["match__home_team__name", "match__away_team__name"]
    raw_id_fields = ["match"]


@admin.register(BetSlip)
class BetSlipAdmin(admin.ModelAdmin):
    list_display = ["user", "match", "selection", "odds_at_placement", "stake", "status", "payout"]
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


class UserBadgeInline(admin.TabularInline):
    model = UserBadge
    extra = 0
    readonly_fields = ["badge", "earned_at"]
    can_delete = False


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ["user", "badge", "earned_at"]
    list_filter = ["badge__rarity", "badge"]
    search_fields = ["user__email", "badge__name"]
    raw_id_fields = ["user"]
