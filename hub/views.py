import logging
from decimal import Decimal

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from vinosports.betting.balance import log_transaction
from vinosports.betting.leaderboard import (
    BOARD_TYPES,
    get_leaderboard_entries,
    get_public_identity,
    get_user_rank,
)
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


# ---------------------------------------------------------------------------
# Global Standings
# ---------------------------------------------------------------------------


class StandingsView(TemplateView):
    template_name = "hub/standings.html"

    def _get_board_type(self):
        board_type = self.request.GET.get("type", "balance")
        return board_type if board_type in BOARD_TYPES else "balance"

    def get_template_names(self):
        if getattr(self.request, "htmx", False):
            return ["hub/partials/standings_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        board_type = self._get_board_type()
        ctx["leaderboard"] = get_leaderboard_entries(limit=None, board_type=board_type)
        ctx["user_rank"] = get_user_rank(
            self.request.user, ctx["leaderboard"], board_type=board_type
        )
        ctx["board_type"] = board_type
        ctx["board_types"] = BOARD_TYPES
        return ctx


# ---------------------------------------------------------------------------
# My Bets (cross-league)
# ---------------------------------------------------------------------------


class MyBetsView(LoginRequiredMixin, TemplateView):
    template_name = "hub/my_bets.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        from epl.betting.models import BetSlip as EplBetSlip
        from epl.betting.models import Parlay as EplParlay
        from nba.betting.models import BetSlip as NbaBetSlip
        from nba.betting.models import Parlay as NbaParlay

        epl_bets = EplBetSlip.objects.filter(user=user).select_related(
            "match__home_team", "match__away_team"
        )
        nba_bets = NbaBetSlip.objects.filter(user=user).select_related(
            "game__home_team", "game__away_team"
        )
        epl_parlays = EplParlay.objects.filter(user=user).prefetch_related(
            "legs__match__home_team", "legs__match__away_team"
        )
        nba_parlays = NbaParlay.objects.filter(user=user).prefetch_related(
            "legs__game__home_team", "legs__game__away_team"
        )

        # Aggregate totals
        epl_bet_totals = epl_bets.aggregate(
            total_staked=Sum("stake"), total_payout=Sum("payout")
        )
        nba_bet_totals = nba_bets.aggregate(
            total_staked=Sum("stake"), total_payout=Sum("payout")
        )
        epl_parlay_totals = epl_parlays.aggregate(
            total_staked=Sum("stake"), total_payout=Sum("payout")
        )
        nba_parlay_totals = nba_parlays.aggregate(
            total_staked=Sum("stake"), total_payout=Sum("payout")
        )

        total_staked = sum(
            t["total_staked"] or Decimal("0")
            for t in [
                epl_bet_totals,
                nba_bet_totals,
                epl_parlay_totals,
                nba_parlay_totals,
            ]
        )
        total_payout = sum(
            t["total_payout"] or Decimal("0")
            for t in [
                epl_bet_totals,
                nba_bet_totals,
                epl_parlay_totals,
                nba_parlay_totals,
            ]
        )

        balance = getattr(user, "balance", None)
        current_balance = balance.balance if balance else Decimal("1000.00")

        # Build unified activity feed: pending first, then by date
        activity = []
        for bet in epl_bets:
            activity.append(
                {"type": "bet", "league": "epl", "date": bet.created_at, "item": bet}
            )
        for bet in nba_bets:
            activity.append(
                {"type": "bet", "league": "nba", "date": bet.created_at, "item": bet}
            )
        for parlay in epl_parlays:
            activity.append(
                {
                    "type": "parlay",
                    "league": "epl",
                    "date": parlay.created_at,
                    "item": parlay,
                }
            )
        for parlay in nba_parlays:
            activity.append(
                {
                    "type": "parlay",
                    "league": "nba",
                    "date": parlay.created_at,
                    "item": parlay,
                }
            )
        # Pending first, then most recent
        activity.sort(
            key=lambda a: (
                0 if a["item"].status == "PENDING" else 1,
                -a["date"].timestamp(),
            )
        )

        ctx["total_staked"] = total_staked
        ctx["total_payout"] = total_payout
        ctx["net_pnl"] = total_payout - total_staked
        ctx["current_balance"] = current_balance
        ctx["activity"] = activity
        return ctx


# ---------------------------------------------------------------------------
# Challenges (cross-league)
# ---------------------------------------------------------------------------


def _ensure_challenge_enrollment(user):
    """Lazily enroll user into all active challenges they haven't joined."""
    from vinosports.challenges.models import Challenge, UserChallenge

    active_challenges = Challenge.objects.filter(
        status=Challenge.Status.ACTIVE
    ).select_related("template")

    existing_ids = set(
        UserChallenge.objects.filter(
            user=user, challenge__in=active_challenges
        ).values_list("challenge_id", flat=True)
    )

    new_ucs = []
    for challenge in active_challenges:
        if challenge.pk not in existing_ids:
            new_ucs.append(
                UserChallenge(
                    user=user,
                    challenge=challenge,
                    target=challenge.target,
                )
            )
    if new_ucs:
        UserChallenge.objects.bulk_create(new_ucs, ignore_conflicts=True)


def _get_hub_user_challenges(user, status_filter=None):
    """Return UserChallenge queryset for a user with optional status filter."""
    from vinosports.challenges.models import UserChallenge

    qs = UserChallenge.objects.filter(user=user).select_related("challenge__template")
    if status_filter:
        qs = qs.filter(status=status_filter)
    return qs


class ChallengesView(LoginRequiredMixin, TemplateView):
    template_name = "hub/challenges.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from vinosports.challenges.models import Challenge, UserChallenge

        user = self.request.user
        _ensure_challenge_enrollment(user)

        tab = self.request.GET.get("tab", "active")
        ctx["active_tab"] = tab

        if tab == "active":
            ctx["challenges"] = _get_hub_user_challenges(
                user, UserChallenge.Status.IN_PROGRESS
            )
        elif tab == "completed":
            ctx["challenges"] = _get_hub_user_challenges(
                user, UserChallenge.Status.COMPLETED
            )
        elif tab == "upcoming":
            ctx["upcoming_challenges"] = (
                Challenge.objects.filter(status=Challenge.Status.UPCOMING)
                .select_related("template")
                .order_by("starts_at")
            )
        else:
            ctx["challenges"] = _get_hub_user_challenges(
                user, UserChallenge.Status.IN_PROGRESS
            )

        return ctx


class ActiveChallengesHubPartial(LoginRequiredMixin, TemplateView):
    template_name = "hub/partials/challenge_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from vinosports.challenges.models import UserChallenge

        _ensure_challenge_enrollment(self.request.user)
        ctx["challenges"] = _get_hub_user_challenges(
            self.request.user, UserChallenge.Status.IN_PROGRESS
        )
        ctx["active_tab"] = "active"
        return ctx


class CompletedChallengesHubPartial(LoginRequiredMixin, TemplateView):
    template_name = "hub/partials/challenge_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from vinosports.challenges.models import UserChallenge

        ctx["challenges"] = _get_hub_user_challenges(
            self.request.user, UserChallenge.Status.COMPLETED
        )
        ctx["active_tab"] = "completed"
        return ctx


class UpcomingChallengesHubPartial(LoginRequiredMixin, TemplateView):
    template_name = "hub/partials/challenge_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from vinosports.challenges.models import Challenge

        ctx["upcoming_challenges"] = (
            Challenge.objects.filter(status=Challenge.Status.UPCOMING)
            .select_related("template")
            .order_by("starts_at")
        )
        ctx["active_tab"] = "upcoming"
        return ctx


# ---------------------------------------------------------------------------
# Admin Dashboard (cross-league)
# ---------------------------------------------------------------------------


class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


ADMIN_PAGE_SIZE = 5
ADMIN_MAX_OFFSET = 500


class AdminDashboardView(SuperuserRequiredMixin, TemplateView):
    template_name = "hub/admin_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        User = get_user_model()

        from epl.betting.models import BetSlip as EplBetSlip
        from epl.betting.models import Parlay as EplParlay
        from epl.discussions.models import Comment as EplComment
        from nba.betting.models import BetSlip as NbaBetSlip
        from nba.betting.models import Parlay as NbaParlay
        from nba.discussions.models import Comment as NbaComment

        ctx["total_users"] = User.objects.count()
        ctx["active_bets"] = (
            EplBetSlip.objects.filter(status="PENDING").count()
            + NbaBetSlip.objects.filter(status="PENDING").count()
        )
        ctx["active_parlays"] = (
            EplParlay.objects.filter(status="PENDING").count()
            + NbaParlay.objects.filter(status="PENDING").count()
        )
        ctx["total_comments"] = (
            EplComment.objects.filter(is_deleted=False).count()
            + NbaComment.objects.filter(is_deleted=False).count()
        )
        ctx["total_bets_all_time"] = (
            EplBetSlip.objects.count()
            + NbaBetSlip.objects.count()
            + EplParlay.objects.count()
            + NbaParlay.objects.count()
        )
        epl_in_play = (
            EplBetSlip.objects.filter(status="PENDING").aggregate(total=Sum("stake"))[
                "total"
            ]
            or 0
        )
        nba_in_play = (
            NbaBetSlip.objects.filter(status="PENDING").aggregate(total=Sum("stake"))[
                "total"
            ]
            or 0
        )
        ctx["total_in_play"] = epl_in_play + nba_in_play

        # Per-league breakdowns
        ctx["epl_bets"] = EplBetSlip.objects.count() + EplParlay.objects.count()
        ctx["nba_bets"] = NbaBetSlip.objects.count() + NbaParlay.objects.count()
        return ctx


def _admin_parse_offset(request):
    try:
        return min(ADMIN_MAX_OFFSET, max(0, int(request.GET.get("offset", 0))))
    except (TypeError, ValueError):
        return 0


def _admin_paginated_response(request, items, total, offset, list_tpl, page_tpl):
    from django.template.loader import render_to_string

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
    from django.http import HttpResponse

    return HttpResponse(html)


def _admin_merged_querysets(qs_a, qs_b, offset, page_size):
    from heapq import merge
    from operator import attrgetter

    limit = offset + page_size
    a_items = list(qs_a[:limit])
    b_items = list(qs_b[:limit])
    merged = list(merge(a_items, b_items, key=attrgetter("created_at"), reverse=True))
    return merged[offset : offset + page_size]


class AdminBetsPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        from epl.betting.models import BetSlip as EplBetSlip
        from epl.betting.models import Parlay as EplParlay
        from nba.betting.models import BetSlip as NbaBetSlip
        from nba.betting.models import Parlay as NbaParlay

        offset = _admin_parse_offset(request)

        # Merge all bets from both leagues
        epl_bets = EplBetSlip.objects.select_related(
            "user", "match__home_team", "match__away_team"
        ).order_by("-created_at")
        nba_bets = NbaBetSlip.objects.select_related(
            "user", "game__home_team", "game__away_team"
        ).order_by("-created_at")
        all_bets = _admin_merged_querysets(
            epl_bets, nba_bets, 0, offset + ADMIN_PAGE_SIZE * 2
        )

        # Merge all parlays from both leagues
        epl_parlays = (
            EplParlay.objects.select_related("user")
            .prefetch_related("legs__match__home_team", "legs__match__away_team")
            .order_by("-created_at")
        )
        nba_parlays = (
            NbaParlay.objects.select_related("user")
            .prefetch_related("legs__game__home_team", "legs__game__away_team")
            .order_by("-created_at")
        )
        all_parlays = _admin_merged_querysets(
            epl_parlays, nba_parlays, 0, offset + ADMIN_PAGE_SIZE * 2
        )

        # Final merge of bets + parlays
        from heapq import merge
        from operator import attrgetter

        merged = list(
            merge(all_bets, all_parlays, key=attrgetter("created_at"), reverse=True)
        )
        items = merged[offset : offset + ADMIN_PAGE_SIZE]
        total = (
            EplBetSlip.objects.count()
            + NbaBetSlip.objects.count()
            + EplParlay.objects.count()
            + NbaParlay.objects.count()
        )

        return _admin_paginated_response(
            request,
            items,
            total,
            offset,
            "hub/partials/admin_bets_list.html",
            "hub/partials/admin_bets_page.html",
        )


class AdminCommentsPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        from epl.discussions.models import Comment as EplComment
        from nba.discussions.models import Comment as NbaComment

        offset = _admin_parse_offset(request)
        epl_comments = (
            EplComment.objects.filter(is_deleted=False)
            .select_related("user", "match__home_team", "match__away_team")
            .order_by("-created_at")
        )
        nba_comments = (
            NbaComment.objects.filter(is_deleted=False)
            .select_related("user", "game__home_team", "game__away_team")
            .order_by("-created_at")
        )
        items = _admin_merged_querysets(
            epl_comments, nba_comments, offset, ADMIN_PAGE_SIZE
        )
        total = (
            EplComment.objects.filter(is_deleted=False).count()
            + NbaComment.objects.filter(is_deleted=False).count()
        )

        return _admin_paginated_response(
            request,
            items,
            total,
            offset,
            "hub/partials/admin_comments_list.html",
            "hub/partials/admin_comments_page.html",
        )


class AdminUsersPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        User = get_user_model()
        offset = _admin_parse_offset(request)
        qs = User.objects.filter(is_bot=False).order_by("-date_joined")
        items = list(qs[offset : offset + ADMIN_PAGE_SIZE])
        total = qs.count()

        return _admin_paginated_response(
            request,
            items,
            total,
            offset,
            "hub/partials/admin_users_list.html",
            "hub/partials/admin_users_page.html",
        )
