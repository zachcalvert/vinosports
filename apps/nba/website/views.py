from betting.forms import CurrencyForm, DisplayNameForm
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from games.models import Game, GameStatus

from vinosports.betting.models import BalanceTransaction, UserBalance, UserStats
from website.forms import LoginForm, SignupForm
from website.theme import THEME_SESSION_KEY, get_theme, normalize_theme

User = get_user_model()


class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        from django.utils import timezone

        today = timezone.localdate()
        games = (
            Game.objects.filter(game_date=today)
            .select_related("home_team", "away_team")
            .order_by("tip_off")
        )

        live = [
            g
            for g in games
            if g.status in (GameStatus.IN_PROGRESS, GameStatus.HALFTIME)
        ]
        upcoming = [g for g in games if g.status == GameStatus.SCHEDULED]
        final = [g for g in games if g.status == GameStatus.FINAL]

        return render(
            request,
            "website/dashboard.html",
            {
                "live_games": live,
                "upcoming_games": upcoming,
                "final_games": final,
                "today": today,
            },
        )


class SignupView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("/")
        return render(request, "website/signup.html", {"form": SignupForm()})

    def post(self, request):
        form = SignupForm(request.POST)
        if not form.is_valid():
            return render(request, "website/signup.html", {"form": form})

        with transaction.atomic():
            user = User.objects.create_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
            UserBalance.objects.create(user=user)
            UserStats.objects.create(user=user)

        login(request, user)
        return redirect("/")


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("/")
        return render(request, "website/login.html", {"form": LoginForm()})

    def post(self, request):
        form = LoginForm(request.POST)
        if not form.is_valid():
            return render(request, "website/login.html", {"form": form})

        user = authenticate(
            request,
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )
        if user is None:
            form.add_error(None, "Invalid email or password.")
            return render(request, "website/login.html", {"form": form})

        login(request, user)
        next_url = request.GET.get("next", "/")
        if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}
        ):
            next_url = "/"
        return redirect(next_url)


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("/login/")

    def get(self, request):
        logout(request)
        return redirect("/login/")


class AccountView(LoginRequiredMixin, View):
    def get(self, request):
        ctx = _account_context(request.user)
        return render(request, "website/account.html", ctx)


class ThemeToggleView(View):
    def post(self, request):
        new_theme = request.POST.get("theme", "")
        current = get_theme(request)
        target = (
            normalize_theme(new_theme)
            if new_theme
            else ("light" if current == "dark" else "dark")
        )
        request.session[THEME_SESSION_KEY] = target

        referer = request.META.get("HTTP_REFERER", "/")
        return redirect(referer)


def _account_context(user):
    try:
        balance = UserBalance.objects.get(user=user)
    except UserBalance.DoesNotExist:
        balance = None

    try:
        stats = UserStats.objects.get(user=user)
    except UserStats.DoesNotExist:
        stats = None

    transactions = BalanceTransaction.objects.filter(user=user).order_by("-created_at")[
        :20
    ]

    return {
        "balance": balance,
        "stats": stats,
        "transactions": transactions,
        "display_name_form": DisplayNameForm(instance=user),
        "currency_form": CurrencyForm(instance=user),
    }
