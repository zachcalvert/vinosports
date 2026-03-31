from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View

from nfl.games.models import Game, GameStatus, Standing
from nfl.games.views import _nfl_current_season, _nfl_current_week
from nfl.website.theme import THEME_SESSION_KEY, get_theme, normalize_theme
from vinosports.betting.models import BalanceTransaction, UserBalance, UserStats


class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        season = _nfl_current_season()
        current_week = _nfl_current_week(season)

        from django.db.models import Count

        games = (
            Game.objects.filter(season=season, week=current_week)
            .select_related("home_team", "away_team")
            .annotate(
                bet_count=Count("bets", distinct=True),
                comment_count=Count("comments", distinct=True),
            )
            .order_by("kickoff", "game_date")
        )

        live = [
            g
            for g in games
            if g.status in (GameStatus.IN_PROGRESS, GameStatus.HALFTIME)
        ]
        upcoming = [g for g in games if g.status == GameStatus.SCHEDULED]
        final = [
            g for g in games if g.status in (GameStatus.FINAL, GameStatus.FINAL_OT)
        ]

        # Build standings lookup for records
        team_ids = set()
        for g in games:
            team_ids.add(g.home_team_id)
            team_ids.add(g.away_team_id)
        standings_qs = Standing.objects.filter(
            team_id__in=team_ids, season=season
        ).select_related("team")
        standings_by_team = {s.team_id: s for s in standings_qs}

        # Odds lookup (most recent per game)
        odds_by_game = {}
        for g in games:
            first_odds = g.odds.all()[:1]
            if first_odds:
                odds_by_game[g.id] = first_odds[0]

        from vinosports.betting.featured import FeaturedParlay

        featured_parlays = (
            FeaturedParlay.objects.filter(
                league="nfl", status=FeaturedParlay.Status.ACTIVE
            )
            .select_related("sponsor", "sponsor__bot_profile")
            .prefetch_related("legs")
            .order_by("-created_at")[:2]
        )

        return render(
            request,
            "nfl_website/dashboard.html",
            {
                "live_games": live,
                "upcoming_games": upcoming,
                "final_games": final,
                "current_week": current_week,
                "season": season,
                "standings_by_team": standings_by_team,
                "odds_by_game": odds_by_game,
                "featured_parlays": featured_parlays,
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
        return render(request, "nfl_website/account.html", ctx)


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
    }
