from decimal import Decimal

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count

from vinosports.betting.balance import log_transaction
from vinosports.betting.models import BalanceTransaction, UserBalance
from vinosports.rewards.models import Reward, RewardDistribution, RewardRule

from .models import SiteSettings

User = get_user_model()

admin.site.unregister(Group)


class UserBalanceInline(admin.TabularInline):
    model = UserBalance
    extra = 0
    readonly_fields = ("balance",)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "display_name", "is_staff", "is_bot", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_bot", "is_active")
    search_fields = ("email", "display_name")
    ordering = ("-date_joined",)
    inlines = [UserBalanceInline]

    # Replace username-based fieldsets with email-based ones
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Profile",
            {
                "fields": (
                    "display_name",
                    "currency",
                    "is_bot",
                    "profile_image",
                    "slug",
                    "id_hash",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ("slug", "id_hash", "date_joined", "last_login")

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "max_users")

    def has_add_permission(self, request):
        # Only allow one SiteSettings instance
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# --- Rewards Admin ---


class RewardAdminForm(forms.ModelForm):
    distribute_to = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("email"),
        required=False,
        widget=admin.widgets.FilteredSelectMultiple("users", is_stacked=False),
        help_text="Select users to distribute this reward to on save.",
    )

    class Meta:
        model = Reward
        fields = ("name", "amount", "description")


class RewardDistributionInline(admin.TabularInline):
    model = RewardDistribution
    extra = 0
    readonly_fields = ("user", "seen", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    form = RewardAdminForm
    list_display = ("name", "amount", "recipient_count", "created_by", "created_at")
    readonly_fields = ("created_by", "created_at")
    inlines = [RewardDistributionInline]
    actions = ["distribute_to_all_users"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_recipient_count=Count("distributions"))
        )

    def recipient_count(self, obj):
        return obj._recipient_count

    recipient_count.admin_order_field = "_recipient_count"
    recipient_count.short_description = "Recipients"

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

        users = form.cleaned_data.get("distribute_to")
        if users:
            with transaction.atomic():
                obj.distribute_to_users(users)

    @admin.action(description="Distribute selected rewards to all active users")
    def distribute_to_all_users(self, request, queryset):
        active_users = list(User.objects.filter(is_active=True, is_bot=False))
        for reward in queryset:
            reward.distribute_to_users(active_users)
        self.message_user(
            request,
            f"Distributed {queryset.count()} reward(s) to {len(active_users)} users.",
        )


@admin.register(RewardDistribution)
class RewardDistributionAdmin(admin.ModelAdmin):
    list_display = ("reward", "user", "seen", "created_at")
    list_filter = ("seen", "reward")
    readonly_fields = ("reward", "user", "created_at")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            with transaction.atomic():
                balance, _ = UserBalance.objects.select_for_update().get_or_create(
                    user=obj.user, defaults={"balance": Decimal("100000.00")}
                )
                log_transaction(
                    balance,
                    obj.reward.amount,
                    BalanceTransaction.Type.REWARD,
                    f"Reward: {obj.reward.name}",
                )


@admin.register(RewardRule)
class RewardRuleAdmin(admin.ModelAdmin):
    list_display = (
        "rule_type",
        "threshold",
        "reward",
        "is_active",
        "distribution_count",
    )
    list_editable = ("is_active",)
    list_filter = ("rule_type", "is_active")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_distribution_count=Count("reward__distributions"))
        )

    def distribution_count(self, obj):
        return obj._distribution_count

    distribution_count.admin_order_field = "_distribution_count"
    distribution_count.short_description = "Times awarded"
