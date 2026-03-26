from heapq import merge
from operator import attrgetter

from django.contrib.auth import get_user_model, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import TemplateView

from nba.activity.models import ActivityEvent
from nba.betting.forms import CurrencyForm, DisplayNameForm
from nba.betting.models import BetSlip, Parlay
from nba.discussions.models import Comment
from nba.games.models import Game, GameStatus, Standing
from nba.website.theme import THEME_SESSION_KEY, get_theme, normalize_theme
from vinosports.betting.models import BalanceTransaction, UserBalance, UserStats

User = get_user_model()


class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        from nba.games.services import today_et

        today = today_et()
        games = (
            Game.objects.filter(game_date=today)
            .select_related("home_team", "away_team")
            .annotate(
                bet_count=Count("bets", distinct=True),
                comment_count=Count("comments", distinct=True),
            )
            .order_by("tip_off")
        )

        live = [
            g
            for g in games
            if g.status in (GameStatus.IN_PROGRESS, GameStatus.HALFTIME)
        ]
        upcoming = [g for g in games if g.status == GameStatus.SCHEDULED]
        final = [g for g in games if g.status == GameStatus.FINAL]

        # Build a lookup of team standings for records & seeds
        team_ids = set()
        for g in games:
            team_ids.add(g.home_team_id)
            team_ids.add(g.away_team_id)
        standings_qs = Standing.objects.filter(
            team_id__in=team_ids, season=today.year
        ).select_related("team")
        standings_by_team = {s.team_id: s for s in standings_qs}

        return render(
            request,
            "nba_website/dashboard.html",
            {
                "live_games": live,
                "upcoming_games": upcoming,
                "final_games": final,
                "today": today,
                "standings_by_team": standings_by_team,
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
        return render(request, "nba_website/account.html", ctx)


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


# ---------------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------------

ADMIN_PAGE_SIZE = 5
ADMIN_MAX_OFFSET = 500


class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class AdminDashboardView(SuperuserRequiredMixin, TemplateView):
    template_name = "nba_website/admin_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["total_users"] = User.objects.count()
        ctx["active_bets"] = BetSlip.objects.filter(status="PENDING").count()
        ctx["active_parlays"] = Parlay.objects.filter(status="PENDING").count()
        ctx["total_comments"] = Comment.objects.filter(is_deleted=False).count()
        ctx["total_bets_all_time"] = BetSlip.objects.count() + Parlay.objects.count()
        ctx["total_in_play"] = (
            BetSlip.objects.filter(status="PENDING").aggregate(total=Sum("stake"))[
                "total"
            ]
            or 0
        )
        ctx["queued_events"] = ActivityEvent.objects.filter(
            broadcast_at__isnull=True
        ).count()
        return ctx


def _parse_offset(request):
    try:
        return min(ADMIN_MAX_OFFSET, max(0, int(request.GET.get("offset", 0))))
    except (TypeError, ValueError):
        return 0


def _paginated_response(request, items, total, offset, list_tpl, page_tpl):
    has_more = (offset + ADMIN_PAGE_SIZE) < total
    ctx = {
        "items": items,
        "has_more": has_more,
        "next_offset": offset + ADMIN_PAGE_SIZE,
        "request": request,
    }
    if offset > 0:
        html = render_to_string(page_tpl, ctx, request=request)
    else:
        html = render_to_string(list_tpl, ctx, request=request)
    return HttpResponse(html)


def _merged_querysets(qs_a, qs_b, offset, page_size):
    """Merge two querysets ordered by -created_at using heapq, with offset pagination."""
    limit = offset + page_size
    a_items = list(qs_a[:limit])
    b_items = list(qs_b[:limit])
    merged = list(merge(a_items, b_items, key=attrgetter("created_at"), reverse=True))
    return merged[offset : offset + page_size]


class AdminBetsPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        offset = _parse_offset(request)
        bets_qs = BetSlip.objects.select_related(
            "user", "game__home_team", "game__away_team"
        ).order_by("-created_at")
        parlays_qs = (
            Parlay.objects.select_related("user")
            .prefetch_related("legs__game__home_team", "legs__game__away_team")
            .order_by("-created_at")
        )
        items = _merged_querysets(bets_qs, parlays_qs, offset, ADMIN_PAGE_SIZE)
        total = BetSlip.objects.count() + Parlay.objects.count()
        return _paginated_response(
            request,
            items,
            total,
            offset,
            "nba_website/partials/admin_bets_list.html",
            "nba_website/partials/admin_bets_page.html",
        )


class AdminCommentsPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        offset = _parse_offset(request)
        qs = (
            Comment.objects.filter(is_deleted=False)
            .select_related("user", "game__home_team", "game__away_team")
            .order_by("-created_at")
        )
        items = list(qs[offset : offset + ADMIN_PAGE_SIZE])
        total = qs.count()
        return _paginated_response(
            request,
            items,
            total,
            offset,
            "nba_website/partials/admin_comments_list.html",
            "nba_website/partials/admin_comments_page.html",
        )


class AdminUsersPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        offset = _parse_offset(request)
        qs = User.objects.filter(is_bot=False).order_by("-date_joined")
        items = list(qs[offset : offset + ADMIN_PAGE_SIZE])
        total = qs.count()
        return _paginated_response(
            request,
            items,
            total,
            offset,
            "nba_website/partials/admin_users_list.html",
            "nba_website/partials/admin_users_page.html",
        )


class AdminActivityQueuePartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        offset = _parse_offset(request)
        qs = ActivityEvent.objects.filter(broadcast_at__isnull=True).order_by(
            "created_at"
        )
        items = list(qs[offset : offset + ADMIN_PAGE_SIZE])
        total = qs.count()
        return _paginated_response(
            request,
            items,
            total,
            offset,
            "nba_website/partials/admin_activity_queue_list.html",
            "nba_website/partials/admin_activity_queue_page.html",
        )
