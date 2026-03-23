from betting.forms import CurrencyForm, DisplayNameForm
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View
from games.models import Game, GameStatus

from vinosports.betting.models import BalanceTransaction, UserBalance, UserStats
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


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("/")

    def get(self, request):
        logout(request)
        return redirect("/")


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
