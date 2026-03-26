from django.contrib import admin

from epl.betting.models import BetSlip, Parlay, ParlayLeg
from epl.matches.models import Odds
from vinosports.betting.featured import FeaturedParlay, FeaturedParlayLeg
from vinosports.betting.models import Badge, UserBadge, UserBalance
from vinosports.challenges.models import Challenge, ChallengeTemplate, UserChallenge


@admin.register(Odds)
class OddsAdmin(admin.ModelAdmin):
    list_display = ["match", "bookmaker", "home_win", "draw", "away_win", "fetched_at"]
    list_filter = ["bookmaker"]
    search_fields = ["match__home_team__name", "match__away_team__name"]
    raw_id_fields = ["match"]


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


# --- Featured Parlays (shared core model, registered here to avoid duplication) ---


class FeaturedParlayLegInline(admin.TabularInline):
    model = FeaturedParlayLeg
    extra = 0
    readonly_fields = ["event_label", "selection_label", "odds_snapshot"]
    can_delete = False


@admin.register(ChallengeTemplate)
class ChallengeTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "challenge_type",
        "criteria_type",
        "reward_amount",
        "is_active",
    ]
    list_filter = ["challenge_type", "criteria_type", "is_active"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ("title",)}


class UserChallengeInline(admin.TabularInline):
    model = UserChallenge
    extra = 0
    readonly_fields = [
        "user",
        "progress",
        "target",
        "status",
        "completed_at",
        "reward_credited",
    ]
    can_delete = False


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ["template", "status", "starts_at", "ends_at", "matchday"]
    list_filter = ["status", "template__challenge_type"]
    search_fields = ["template__title"]
    raw_id_fields = ["template"]
    inlines = [UserChallengeInline]


@admin.register(UserChallenge)
class UserChallengeAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "challenge",
        "progress",
        "target",
        "status",
        "reward_credited",
    ]
    list_filter = ["status", "reward_credited"]
    search_fields = ["user__email", "challenge__template__title"]
    raw_id_fields = ["user", "challenge"]


# --- Featured Parlays (shared core model, registered here to avoid duplication) ---


@admin.register(FeaturedParlay)
class FeaturedParlayAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "league",
        "sponsor",
        "status",
        "combined_odds",
        "expires_at",
        "created_at",
    ]
    list_filter = ["league", "status"]
    search_fields = ["title", "sponsor__display_name"]
    raw_id_fields = ["sponsor"]
    inlines = [FeaturedParlayLegInline]
    readonly_fields = ["id_hash", "combined_odds", "potential_payout"]
