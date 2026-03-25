import logging
from decimal import Decimal

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from vinosports.betting.balance import log_transaction
from vinosports.betting.leaderboard import get_public_identity, get_user_rank
from vinosports.betting.models import (
    Badge,
    BalanceTransaction,
    UserBadge,
    UserBalance,
    UserStats,
)
from vinosports.bots.models import BotProfile

from .forms import CurrencyForm, DisplayNameForm, LoginForm, SignupForm
from .models import SiteSettings
from .promo import evaluate_promo_code

logger = logging.getLogger(__name__)


class HomeView(TemplateView):
    template_name = "hub/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["bot_profiles"] = (
            BotProfile.objects.filter(is_active=True)
            .select_related("user")
            .order_by("user__date_joined")
        )
        return ctx


class BotProfileView(TemplateView):
    """Public profile page for bot users — persona, stats, and badges."""

    template_name = "hub/bot_profile.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        User = get_user_model()
        profile_user = get_object_or_404(User, slug=self.kwargs["slug"], is_bot=True)

        # Identity
        ctx["profile_user"] = profile_user
        ctx["display_identity"] = get_public_identity(profile_user)

        # Bot profile
        try:
            ctx["bot_profile"] = profile_user.bot_profile
        except BotProfile.DoesNotExist:
            pass

        # Stats
        try:
            ctx["stats"] = profile_user.stats
        except UserStats.DoesNotExist:
            ctx["stats"] = None

        # Balance & rank
        try:
            ctx["balance"] = profile_user.balance.balance
        except UserBalance.DoesNotExist:
            ctx["balance"] = Decimal("1000.00")

        ctx["user_rank"] = get_user_rank(profile_user)

        # Badge grid — all badges with earned date (or None if locked)
        earned_map = {
            ub.badge_id: ub.earned_at
            for ub in UserBadge.objects.filter(user=profile_user).select_related(
                "badge"
            )
        }
        all_badges = []
        for badge in Badge.objects.all():
            badge.earned = earned_map.get(badge.pk)
            all_badges.append(badge)
        ctx["all_badges"] = all_badges

        return ctx


class SignupView(View):
    def _registration_closed(self):
        site = SiteSettings.load()
        if site.max_users == 0:
            return False
        User = get_user_model()
        return User.objects.count() >= site.max_users

    def _closed_context(self):
        site = SiteSettings.load()
        return {
            "registration_closed": True,
            "closed_message": site.registration_closed_message,
        }

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("hub:home")
        if self._registration_closed():
            return render(request, "hub/signup.html", self._closed_context())
        return render(request, "hub/signup.html", {"form": SignupForm()})

    def post(self, request):
        if self._registration_closed():
            return render(request, "hub/signup.html", self._closed_context())

        form = SignupForm(request.POST)
        if not form.is_valid():
            return render(request, "hub/signup.html", {"form": form})

        User = get_user_model()
        with transaction.atomic():
            site = SiteSettings.load_for_update()
            if site.max_users and User.objects.count() >= site.max_users:
                return render(request, "hub/signup.html", self._closed_context())
            promo_code = form.cleaned_data.get("promo_code", "")
            user = User.objects.create_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                promo_code=promo_code,
            )
            balance = UserBalance.objects.create(user=user)
            BalanceTransaction.objects.create(
                user=user,
                amount=balance.balance,
                balance_after=balance.balance,
                transaction_type=BalanceTransaction.Type.SIGNUP,
                description="Initial signup bonus",
            )

        # Evaluate promo code outside the atomic block (network call)
        if promo_code:
            bonus = evaluate_promo_code(promo_code)
            if bonus > 0:
                with transaction.atomic():
                    bal = UserBalance.objects.select_for_update().get(user=user)
                    log_transaction(
                        bal,
                        Decimal(str(bonus)),
                        BalanceTransaction.Type.PROMO_CODE,
                        f"Promo code bonus: {promo_code}",
                    )

        login(request, user)
        return redirect("hub:home")


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("hub:home")
        return render(request, "hub/login.html", {"form": LoginForm()})

    def post(self, request):
        form = LoginForm(request.POST)
        if not form.is_valid():
            return render(request, "hub/login.html", {"form": form})

        user = authenticate(
            request,
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )
        if user is None:
            form.add_error(None, "Invalid email or password.")
            return render(request, "hub/login.html", {"form": form})

        login(request, user)
        return redirect("hub:home")


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("hub:home")


# ---------------------------------------------------------------------------
# Account management
# ---------------------------------------------------------------------------


def _account_context(
    user,
    display_name_form=None,
    currency_form=None,
    save_success=False,
    currency_save_success=False,
):
    try:
        balance = user.balance.balance
    except UserBalance.DoesNotExist:
        balance = None

    masked_email = user.email.split("@")[0][:3] + "***@" + user.email.split("@")[1]

    return {
        "display_name_form": display_name_form or DisplayNameForm(instance=user),
        "currency_form": currency_form or CurrencyForm(instance=user),
        "balance": balance,
        "account_masked_email": masked_email,
        "save_success": save_success,
        "currency_save_success": currency_save_success,
    }


class AccountView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "hub/account.html", _account_context(request.user))

    def post(self, request):
        form = DisplayNameForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            fresh_form = DisplayNameForm(instance=request.user)
            return render(
                request,
                "hub/account.html",
                _account_context(
                    request.user, display_name_form=fresh_form, save_success=True
                ),
            )
        return render(
            request,
            "hub/account.html",
            _account_context(request.user, display_name_form=form),
        )


class CurrencyUpdateView(LoginRequiredMixin, View):
    def post(self, request):
        form = CurrencyForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return render(
                request,
                "hub/account.html",
                _account_context(
                    request.user,
                    currency_form=CurrencyForm(instance=request.user),
                    currency_save_success=True,
                ),
            )
        return redirect("hub:account")
