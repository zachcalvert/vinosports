import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from vinosports.activity.models import Notification
from vinosports.betting.balance import log_transaction
from vinosports.betting.leaderboard import (
    BOARD_TYPES,
    get_leaderboard_entries,
    get_public_identity,
    get_user_balance_with_deltas,
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

from .forms import (
    CurrencyForm,
    DisplayNameForm,
    LoginForm,
    ProfileImageForm,
    SignupForm,
)
from .models import SiteSettings
from .promo import evaluate_promo_code

logger = logging.getLogger(__name__)


class HomeView(TemplateView):
    template_name = "hub/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        bot_profiles = (
            BotProfile.objects.filter(is_active=True)
            .select_related("user")
            .order_by("user__date_joined")
        )
        ctx["bot_profiles"] = bot_profiles
        ctx["hero_bots"] = (
            bot_profiles.exclude(user__profile_image="")
            .exclude(user__profile_image__isnull=True)
            .order_by("?")[:4]
        )
        from vinosports.betting.featured import FeaturedParlay

        ctx["featured_parlays"] = (
            FeaturedParlay.objects.filter(status=FeaturedParlay.Status.ACTIVE)
            .select_related("sponsor", "sponsor__bot_profile")
            .prefetch_related("legs")
            .order_by("-created_at")[:4]
        )

        # ── Authenticated user dashboard ──
        user = self.request.user
        if user.is_authenticated:
            # Balance with 24h/7d deltas
            ub = get_user_balance_with_deltas(user)
            if ub:
                ctx["dash_balance"] = ub.balance
                ctx["dash_change_24h"] = ub.change_24h
                ctx["dash_change_7d"] = ub.change_7d

            # Aggregated stats
            try:
                stats = user.stats
                ctx["dash_win_rate"] = stats.win_rate
                ctx["dash_current_streak"] = stats.current_streak
                ctx["dash_net_profit"] = stats.net_profit
                ctx["dash_total_bets"] = stats.total_bets
                ctx["dash_record"] = f"{stats.total_wins}W\u2013{stats.total_losses}L"
            except UserStats.DoesNotExist:
                ctx["dash_total_bets"] = 0

            # Pending bets across both leagues
            from epl.betting.models import BetSlip as EplBetSlip
            from epl.betting.models import FuturesBet as EplFuturesBet
            from epl.betting.models import Parlay as EplParlay
            from nba.betting.models import BetSlip as NbaBetSlip
            from nba.betting.models import FuturesBet as NbaFuturesBet
            from nba.betting.models import Parlay as NbaParlay

            pending_agg = {"count": Count("id"), "stake": Sum("stake")}
            pending_filter = {"user": user, "status": "PENDING"}
            totals = [
                model.objects.filter(**pending_filter).aggregate(**pending_agg)
                for model in (
                    EplBetSlip,
                    NbaBetSlip,
                    EplParlay,
                    NbaParlay,
                    EplFuturesBet,
                    NbaFuturesBet,
                )
            ]
            ctx["dash_pending_count"] = sum(t["count"] or 0 for t in totals)
            ctx["dash_at_stake"] = sum(t["stake"] or 0 for t in totals)

            # Leaderboard rank
            rank_entry = get_user_rank(user, board_type="balance")
            if rank_entry:
                ctx["dash_rank"] = rank_entry.rank

        return ctx


def _get_biggest_wins(user, limit=3):
    """Return top N biggest wins across all leagues, sorted by profit descending."""
    from epl.betting.models import BetSlip as EplBetSlip
    from epl.betting.models import Parlay as EplParlay
    from nba.betting.models import BetSlip as NbaBetSlip
    from nba.betting.models import Parlay as NbaParlay
    from nfl.betting.models import BetSlip as NflBetSlip
    from nfl.betting.models import Parlay as NflParlay

    profit_expr = ExpressionWrapper(
        F("payout") - F("stake"), output_field=DecimalField()
    )
    wins = []

    # --- BetSlips ---
    bet_configs = [
        (EplBetSlip, "epl", "match__home_team", "match__away_team", "match"),
        (NbaBetSlip, "nba", "game__home_team", "game__away_team", "game"),
        (NflBetSlip, "nfl", "game__home_team", "game__away_team", "game"),
    ]
    for Model, league, home_rel, away_rel, event_rel in bet_configs:
        qs = (
            Model.objects.filter(user=user, status="WON", payout__isnull=False)
            .annotate(profit=profit_expr)
            .select_related(home_rel, away_rel)
            .order_by("-profit")[:limit]
        )
        for bet in qs:
            event = getattr(bet, event_rel)
            if league == "epl":
                desc = f"{event.home_team.short_name or event.home_team.tla} vs {event.away_team.short_name or event.away_team.tla}"
                odds = f"{bet.odds_at_placement:.2f}"
            else:
                desc = (
                    f"{event.home_team.abbreviation} vs {event.away_team.abbreviation}"
                )
                odds = (
                    f"{'+' if bet.odds_at_placement > 0 else ''}{bet.odds_at_placement}"
                )
            wins.append(
                {
                    "profit": bet.profit,
                    "payout": bet.payout,
                    "stake": bet.stake,
                    "date": bet.updated_at,
                    "league": league,
                    "type": "bet",
                    "description": desc,
                    "odds": odds,
                }
            )

    # --- Parlays ---
    parlay_configs = [
        (EplParlay, "epl"),
        (NbaParlay, "nba"),
        (NflParlay, "nfl"),
    ]
    for Model, league in parlay_configs:
        qs = (
            Model.objects.filter(user=user, status="WON", payout__isnull=False)
            .annotate(profit=profit_expr)
            .order_by("-profit")[:limit]
        )
        for parlay in qs:
            leg_count = parlay.legs.count()
            if league == "epl":
                odds = f"{parlay.combined_odds:.2f}x"
            else:
                odds = (
                    f"{'+' if parlay.combined_odds > 0 else ''}{parlay.combined_odds}"
                )
            wins.append(
                {
                    "profit": parlay.profit,
                    "payout": parlay.payout,
                    "stake": parlay.stake,
                    "date": parlay.updated_at,
                    "league": league,
                    "type": "parlay",
                    "description": f"Parlay \u2022 {leg_count} legs",
                    "odds": odds,
                }
            )

    wins.sort(key=lambda w: w["profit"], reverse=True)
    return wins[:limit]


class ProfileView(TemplateView):
    """Public profile page for any user — persona, stats, and badges."""

    template_name = "hub/profile.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        User = get_user_model()
        profile_user = get_object_or_404(User, slug=self.kwargs["slug"])

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

        # Biggest wins — all users
        ctx["biggest_wins"] = _get_biggest_wins(profile_user)

        # Recent bets & comments — bot profiles only (for now)
        if profile_user.is_bot:
            from epl.betting.models import BetSlip as EplBetSlip
            from epl.betting.models import Parlay as EplParlay
            from epl.discussions.models import Comment as EplComment
            from nba.betting.models import BetSlip as NbaBetSlip
            from nba.betting.models import Parlay as NbaParlay
            from nba.discussions.models import Comment as NbaComment

            # Recent bets + parlays → unified activity feed
            activity = []
            for bet in (
                EplBetSlip.objects.filter(user=profile_user)
                .select_related("match__home_team", "match__away_team")
                .order_by("-created_at")[:10]
            ):
                activity.append(
                    {
                        "type": "bet",
                        "league": "epl",
                        "date": bet.created_at,
                        "item": bet,
                    }
                )
            for bet in (
                NbaBetSlip.objects.filter(user=profile_user)
                .select_related("game__home_team", "game__away_team")
                .order_by("-created_at")[:10]
            ):
                activity.append(
                    {
                        "type": "bet",
                        "league": "nba",
                        "date": bet.created_at,
                        "item": bet,
                    }
                )
            for parlay in (
                EplParlay.objects.filter(user=profile_user)
                .prefetch_related("legs__match__home_team", "legs__match__away_team")
                .order_by("-created_at")[:5]
            ):
                activity.append(
                    {
                        "type": "parlay",
                        "league": "epl",
                        "date": parlay.created_at,
                        "item": parlay,
                    }
                )
            for parlay in (
                NbaParlay.objects.filter(user=profile_user)
                .prefetch_related("legs__game__home_team", "legs__game__away_team")
                .order_by("-created_at")[:5]
            ):
                activity.append(
                    {
                        "type": "parlay",
                        "league": "nba",
                        "date": parlay.created_at,
                        "item": parlay,
                    }
                )

            activity.sort(key=lambda a: a["date"], reverse=True)
            ctx["recent_activity"] = activity[:10]

            # Recent comments
            comments = []
            for c in (
                EplComment.objects.filter(user=profile_user, is_deleted=False)
                .select_related("match__home_team", "match__away_team", "parent")
                .order_by("-created_at")[:10]
            ):
                comments.append({"league": "epl", "comment": c})
            for c in (
                NbaComment.objects.filter(user=profile_user, is_deleted=False)
                .select_related("game__home_team", "game__away_team", "parent")
                .order_by("-created_at")[:10]
            ):
                comments.append({"league": "nba", "comment": c})

            comments.sort(key=lambda c: c["comment"].created_at, reverse=True)
            ctx["recent_comments"] = comments[:10]

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
    profile_image_form=None,
    save_success=False,
    currency_save_success=False,
    image_save_success=False,
):
    try:
        balance = user.balance.balance
    except UserBalance.DoesNotExist:
        balance = None

    masked_email = user.email.split("@")[0][:3] + "***@" + user.email.split("@")[1]

    # Stats
    try:
        stats = user.stats
    except UserStats.DoesNotExist:
        stats = None

    # Badge grid — all badges with earned date (or None if locked)
    earned_map = {
        ub.badge_id: ub.earned_at
        for ub in UserBadge.objects.filter(user=user).select_related("badge")
    }
    all_badges = []
    for badge in Badge.objects.all():
        badge.earned = earned_map.get(badge.pk)
        all_badges.append(badge)

    return {
        "display_name_form": display_name_form or DisplayNameForm(instance=user),
        "currency_form": currency_form or CurrencyForm(instance=user),
        "profile_image_form": profile_image_form or ProfileImageForm(instance=user),
        "balance": balance,
        "account_masked_email": masked_email,
        "save_success": save_success,
        "currency_save_success": currency_save_success,
        "image_save_success": image_save_success,
        "stats": stats,
        "user_rank": get_user_rank(user),
        "all_badges": all_badges,
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


class ProfileImageUploadView(LoginRequiredMixin, View):
    def post(self, request):
        form = ProfileImageForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            return render(
                request,
                "hub/account.html",
                _account_context(
                    request.user,
                    profile_image_form=ProfileImageForm(instance=request.user),
                    image_save_success=True,
                ),
            )
        return render(
            request,
            "hub/account.html",
            _account_context(request.user, profile_image_form=form),
        )


class BalanceHistoryAPI(View):
    """Return daily balance history as JSON for chart rendering."""

    DEFAULT_DAYS = 30
    MAX_DAYS = 90

    def get(self, request, slug):
        User = get_user_model()
        user = get_object_or_404(User, slug=slug)

        try:
            days = int(request.GET.get("days", self.DEFAULT_DAYS))
        except (TypeError, ValueError):
            days = self.DEFAULT_DAYS
        days = min(max(days, 1), self.MAX_DAYS)

        all_txns = list(
            BalanceTransaction.objects.filter(user=user)
            .order_by("created_at")
            .values_list("created_at", "balance_after")
        )

        if not all_txns:
            return JsonResponse({"data": []})

        today = timezone.now().date()
        data = []
        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            day_balance = next(
                (bal for ts, bal in reversed(all_txns) if ts.date() <= day),
                None,
            )
            if day_balance is not None:
                data.append({"t": day.isoformat(), "y": float(day_balance)})

        return JsonResponse({"data": data})


# ---------------------------------------------------------------------------
# Global Standings
# ---------------------------------------------------------------------------


class StandingsView(TemplateView):
    template_name = "hub/standings.html"

    def _get_board_type(self):
        board_type = self.request.GET.get("type", "balance")
        return board_type if board_type in BOARD_TYPES else "balance"

    def get_template_names(self):
        htmx = getattr(self.request, "htmx", False)
        if htmx and not htmx.boosted:
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
        from epl.betting.models import FuturesBet as EplFuturesBet
        from epl.betting.models import Parlay as EplParlay
        from nba.betting.models import BetSlip as NbaBetSlip
        from nba.betting.models import FuturesBet as NbaFuturesBet
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
        epl_futures = EplFuturesBet.objects.filter(user=user).select_related(
            "outcome__market", "outcome__team"
        )
        nba_futures = NbaFuturesBet.objects.filter(user=user).select_related(
            "outcome__market", "outcome__team"
        )

        # Aggregate totals
        all_querysets = [
            epl_bets,
            nba_bets,
            epl_parlays,
            nba_parlays,
            epl_futures,
            nba_futures,
        ]
        total_staked = Decimal("0")
        total_payout = Decimal("0")
        for qs in all_querysets:
            totals = qs.aggregate(total_staked=Sum("stake"), total_payout=Sum("payout"))
            total_staked += totals["total_staked"] or Decimal("0")
            total_payout += totals["total_payout"] or Decimal("0")

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
        for fb in epl_futures:
            activity.append(
                {
                    "type": "futures",
                    "league": "epl",
                    "date": fb.created_at,
                    "item": fb,
                }
            )
        for fb in nba_futures:
            activity.append(
                {
                    "type": "futures",
                    "league": "nba",
                    "date": fb.created_at,
                    "item": fb,
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
ADMIN_FULL_PAGE_SIZE = 25
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
        from nfl.betting.models import BetSlip as NflBetSlip
        from nfl.betting.models import Parlay as NflParlay
        from nfl.discussions.models import Comment as NflComment

        ctx["total_users"] = User.objects.count()
        ctx["active_bets"] = (
            EplBetSlip.objects.filter(status="PENDING").count()
            + NbaBetSlip.objects.filter(status="PENDING").count()
            + NflBetSlip.objects.filter(status="PENDING").count()
        )
        ctx["active_parlays"] = (
            EplParlay.objects.filter(status="PENDING").count()
            + NbaParlay.objects.filter(status="PENDING").count()
            + NflParlay.objects.filter(status="PENDING").count()
        )
        ctx["total_comments"] = (
            EplComment.objects.filter(is_deleted=False).count()
            + NbaComment.objects.filter(is_deleted=False).count()
            + NflComment.objects.filter(is_deleted=False).count()
        )
        ctx["total_bets_all_time"] = (
            EplBetSlip.objects.count()
            + NbaBetSlip.objects.count()
            + NflBetSlip.objects.count()
            + EplParlay.objects.count()
            + NbaParlay.objects.count()
            + NflParlay.objects.count()
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
        nfl_in_play = (
            NflBetSlip.objects.filter(status="PENDING").aggregate(total=Sum("stake"))[
                "total"
            ]
            or 0
        )
        ctx["total_in_play"] = epl_in_play + nba_in_play + nfl_in_play

        # Per-league breakdowns
        ctx["epl_bets"] = EplBetSlip.objects.count() + EplParlay.objects.count()
        ctx["nba_bets"] = NbaBetSlip.objects.count() + NbaParlay.objects.count()
        ctx["nfl_bets"] = NflBetSlip.objects.count() + NflParlay.objects.count()
        ctx["epl_comments"] = EplComment.objects.filter(is_deleted=False).count()
        ctx["nba_comments"] = NbaComment.objects.filter(is_deleted=False).count()
        ctx["nfl_comments"] = NflComment.objects.filter(is_deleted=False).count()
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


_APP_LABEL_TO_LEAGUE = {
    "epl_betting": "epl",
    "epl_discussions": "epl",
    "nba_betting": "nba",
    "nba_discussions": "nba",
    "nfl_betting": "nfl",
    "nfl_discussions": "nfl",
}


def _admin_merged_querysets(*querysets, offset, page_size):
    from heapq import merge
    from operator import attrgetter

    limit = offset + page_size
    item_lists = [list(qs[:limit]) for qs in querysets]
    merged = list(merge(*item_lists, key=attrgetter("created_at"), reverse=True))
    results = merged[offset : offset + page_size]
    for item in results:
        item.league = _APP_LABEL_TO_LEAGUE.get(item._meta.app_label, "")
    return results


class AdminBetsPartialView(SuperuserRequiredMixin, View):
    def get(self, request):
        from epl.betting.models import BetSlip as EplBetSlip
        from epl.betting.models import Parlay as EplParlay
        from nba.betting.models import BetSlip as NbaBetSlip
        from nba.betting.models import Parlay as NbaParlay
        from nfl.betting.models import BetSlip as NflBetSlip
        from nfl.betting.models import Parlay as NflParlay

        offset = _admin_parse_offset(request)
        prefetch_limit = offset + ADMIN_PAGE_SIZE * 2

        # Merge all bets from all leagues
        epl_bets = EplBetSlip.objects.select_related(
            "user", "match__home_team", "match__away_team"
        ).order_by("-created_at")
        nba_bets = NbaBetSlip.objects.select_related(
            "user", "game__home_team", "game__away_team"
        ).order_by("-created_at")
        nfl_bets = NflBetSlip.objects.select_related(
            "user", "game__home_team", "game__away_team"
        ).order_by("-created_at")
        all_bets = _admin_merged_querysets(
            epl_bets, nba_bets, nfl_bets, offset=0, page_size=prefetch_limit
        )

        # Merge all parlays from all leagues
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
        nfl_parlays = (
            NflParlay.objects.select_related("user")
            .prefetch_related("legs__game__home_team", "legs__game__away_team")
            .order_by("-created_at")
        )
        all_parlays = _admin_merged_querysets(
            epl_parlays, nba_parlays, nfl_parlays, offset=0, page_size=prefetch_limit
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
            + NflBetSlip.objects.count()
            + EplParlay.objects.count()
            + NbaParlay.objects.count()
            + NflParlay.objects.count()
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
        from nfl.discussions.models import Comment as NflComment

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
        nfl_comments = (
            NflComment.objects.filter(is_deleted=False)
            .select_related("user", "game__home_team", "game__away_team")
            .order_by("-created_at")
        )
        items = _admin_merged_querysets(
            epl_comments,
            nba_comments,
            nfl_comments,
            offset=offset,
            page_size=ADMIN_PAGE_SIZE,
        )
        total = (
            EplComment.objects.filter(is_deleted=False).count()
            + NbaComment.objects.filter(is_deleted=False).count()
            + NflComment.objects.filter(is_deleted=False).count()
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


class AdminBetsFullView(SuperuserRequiredMixin, TemplateView):
    """Full page: all bets & parlays across leagues, paginated."""

    template_name = "hub/admin_bets_full.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        from epl.betting.models import BetSlip as EplBetSlip
        from epl.betting.models import Parlay as EplParlay
        from nba.betting.models import BetSlip as NbaBetSlip
        from nba.betting.models import Parlay as NbaParlay
        from nfl.betting.models import BetSlip as NflBetSlip
        from nfl.betting.models import Parlay as NflParlay

        page = max(1, int(self.request.GET.get("page", 1)))
        offset = (page - 1) * ADMIN_FULL_PAGE_SIZE
        prefetch_limit = offset + ADMIN_FULL_PAGE_SIZE * 2

        epl_bets = EplBetSlip.objects.select_related(
            "user", "match__home_team", "match__away_team"
        ).order_by("-created_at")
        nba_bets = NbaBetSlip.objects.select_related(
            "user", "game__home_team", "game__away_team"
        ).order_by("-created_at")
        nfl_bets = NflBetSlip.objects.select_related(
            "user", "game__home_team", "game__away_team"
        ).order_by("-created_at")
        all_bets = _admin_merged_querysets(
            epl_bets, nba_bets, nfl_bets, offset=0, page_size=prefetch_limit
        )

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
        nfl_parlays = (
            NflParlay.objects.select_related("user")
            .prefetch_related("legs__game__home_team", "legs__game__away_team")
            .order_by("-created_at")
        )
        all_parlays = _admin_merged_querysets(
            epl_parlays, nba_parlays, nfl_parlays, offset=0, page_size=prefetch_limit
        )

        from heapq import merge
        from operator import attrgetter

        merged = list(
            merge(all_bets, all_parlays, key=attrgetter("created_at"), reverse=True)
        )
        items = merged[offset : offset + ADMIN_FULL_PAGE_SIZE]
        for item in items:
            item.league = _APP_LABEL_TO_LEAGUE.get(item._meta.app_label, "")

        ctx["items"] = items
        ctx["page"] = page
        ctx["has_next"] = len(items) == ADMIN_FULL_PAGE_SIZE
        ctx["has_prev"] = page > 1
        return ctx


class AdminCommentsFullView(SuperuserRequiredMixin, TemplateView):
    """Full page: all comments across leagues, paginated."""

    template_name = "hub/admin_comments_full.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        from epl.discussions.models import Comment as EplComment
        from nba.discussions.models import Comment as NbaComment
        from nfl.discussions.models import Comment as NflComment

        page = max(1, int(self.request.GET.get("page", 1)))
        offset = (page - 1) * ADMIN_FULL_PAGE_SIZE

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
        nfl_comments = (
            NflComment.objects.filter(is_deleted=False)
            .select_related("user", "game__home_team", "game__away_team")
            .order_by("-created_at")
        )
        items = _admin_merged_querysets(
            epl_comments,
            nba_comments,
            nfl_comments,
            offset=offset,
            page_size=ADMIN_FULL_PAGE_SIZE,
        )

        ctx["items"] = items
        ctx["page"] = page
        ctx["has_next"] = len(items) == ADMIN_FULL_PAGE_SIZE
        ctx["has_prev"] = page > 1
        return ctx


# ---------------------------------------------------------------------------
# Inbox (notifications)
# ---------------------------------------------------------------------------


class InboxView(LoginRequiredMixin, TemplateView):
    """User's notification inbox."""

    template_name = "hub/inbox.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()

        notifications = (
            Notification.objects.filter(
                recipient=self.request.user,
                expires_at__gt=now,
            )
            .select_related("actor")
            .order_by("-created_at")[:100]
        )

        context["notifications"] = notifications
        context["unread_count"] = sum(1 for n in notifications if not n.is_read)
        return context


class MarkNotificationReadView(LoginRequiredMixin, View):
    """Mark a single notification as read and redirect to its URL."""

    def post(self, request, id_hash):
        notification = get_object_or_404(
            Notification,
            id_hash=id_hash,
            recipient=request.user,
        )
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])

        if request.headers.get("HX-Request"):
            return render(
                request,
                "hub/partials/inbox_notification.html",
                {
                    "notification": notification,
                },
            )

        return redirect(notification.url or "hub:inbox")


class MarkAllReadView(LoginRequiredMixin, View):
    """Mark all unread notifications as read."""

    def post(self, request):
        Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

        if request.headers.get("HX-Request"):
            from django.http import HttpResponse as HttpResp

            return HttpResp(headers={"HX-Refresh": "true"})
        return redirect("hub:inbox")
