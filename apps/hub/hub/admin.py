from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from vinosports.betting.models import UserBalance

from .models import SiteSettings

User = get_user_model()


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
            {"fields": ("display_name", "currency", "is_bot", "slug", "id_hash")},
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
