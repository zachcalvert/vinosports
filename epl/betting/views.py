import logging
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Min, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from epl.betting.context_processors import parlay_slip as _parlay_slip_ctx
from epl.betting.forms import PlaceBetForm, PlaceParlayForm
from epl.betting.models import BetSlip, Parlay, ParlayLeg
from epl.discussions.models import Comment
from epl.matches.models import Match, Odds
from epl.website.challenge_engine import update_challenge_progress
from epl.website.templatetags.currency_tags import format_currency
from vinosports.betting.balance import log_transaction
from vinosports.betting.constants import (
    PARLAY_MAX_LEGS,
    PARLAY_MAX_PAYOUT,
    PARLAY_MIN_LEGS,
)
from vinosports.betting.featured import FeaturedParlay
from vinosports.betting.leaderboard import get_public_identity, get_user_rank
from vinosports.betting.models import (
    Badge,
    Bailout,
    BalanceTransaction,
    Bankruptcy,
    BetStatus,
    UserBadge,
    UserBalance,
    UserStats,
)
from vinosports.rewards.models import RewardDistribution

logger = logging.getLogger(__name__)


def _get_latest_odds_refresh(match_ids):
    if not match_ids:
        return None
    return Odds.objects.filter(match_id__in=match_ids).aggregate(
        latest_refresh=Max("fetched_at")
    )["latest_refresh"]


class OddsBoardView(TemplateView):
    template_name = "epl_betting/odds_board.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        upcoming = (
            Match.objects.filter(
                season=settings.EPL_CURRENT_SEASON,
                status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
            )
            .select_related("home_team", "away_team")
            .order_by("kickoff")
        )

        match_list = list(upcoming)
        match_ids = [m.pk for m in match_list]

        best_odds = (
            Odds.objects.filter(match_id__in=match_ids)
            .values("match_id")
            .annotate(
                best_home=Min("home_win"),
                best_draw=Min("draw"),
                best_away=Min("away_win"),
            )
        )
        odds_map = {o["match_id"]: o for o in best_odds}

        matches_with_odds = []
        for match in match_list:
            odds = odds_map.get(match.pk, {})
            match.best_home_odds = odds.get("best_home")
            match.best_draw_odds = odds.get("best_draw")
            match.best_away_odds = odds.get("best_away")
            if any(
                odd is not None
                for odd in (
                    match.best_home_odds,
                    match.best_draw_odds,
                    match.best_away_odds,
                )
            ):
                matches_with_odds.append(match)

        ctx["matches"] = matches_with_odds
        ctx["last_odds_refresh"] = _get_latest_odds_refresh(match_ids)
        ctx["rendered_at"] = timezone.now()
        return ctx


class OddsBoardPartialView(OddsBoardView):
    """Returns just the odds board body for HTMX polling."""

    template_name = "epl_betting/partials/odds_board_body.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)


def _get_match_sentiment(match):
    """Aggregate community sentiment for a match from all placed BetSlips."""
    rows = (
        BetSlip.objects.filter(match=match)
        .values("selection")
        .annotate(count=Count("id"))
    )
    counts = {r["selection"]: r["count"] for r in rows}
    total = sum(counts.values())
    if not total:
        return None
    home_pct = round(counts.get(BetSlip.Selection.HOME_WIN, 0) / total * 100)
    draw_pct = round(counts.get(BetSlip.Selection.DRAW, 0) / total * 100)
    away_pct = 100 - home_pct - draw_pct
    most_popular_count = max(counts.values())
    most_popular_label = next(
        label
        for sel, label in BetSlip.Selection.choices
        if counts.get(sel, 0) == most_popular_count
    )
    return {
        "total": total,
        "home_pct": home_pct,
        "draw_pct": draw_pct,
        "away_pct": away_pct,
        "most_popular": most_popular_label,
    }


class PlaceBetView(LoginRequiredMixin, View):
    """Handle bet placement via HTMX POST."""

    def _error_template(self, container_id):
        """Return the appropriate error template based on context."""
        if container_id:
            return "epl_betting/partials/quick_bet_form.html"
        return "epl_betting/partials/bet_form.html"

    def _get_odds_context(self, match, selection="", container_id=""):
        """Return odds context for payout preview on error re-renders."""
        if container_id:
            # Quick bet form: pass selected_odds for the chosen outcome
            odds_field_map = {
                "HOME_WIN": "home_win",
                "DRAW": "draw",
                "AWAY_WIN": "away_win",
            }
            odds_field = odds_field_map.get(selection)
            if odds_field:
                result = Odds.objects.filter(match=match).aggregate(
                    best=Min(odds_field)
                )
                return {"selected_odds": result.get("best")}
            return {}
        # Full bet form: pass all three best odds
        result = Odds.objects.filter(match=match).aggregate(
            best_home=Min("home_win"),
            best_draw=Min("draw"),
            best_away=Min("away_win"),
        )
        return {
            "best_home": result["best_home"],
            "best_draw": result["best_draw"],
            "best_away": result["best_away"],
        }

    def post(self, request, match_slug):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"),
            slug=match_slug,
        )
        container_id = request.POST.get("container_id", "")

        # Only allow bets on upcoming matches
        if match.status not in (Match.Status.SCHEDULED, Match.Status.TIMED):
            selection_val = request.POST.get("selection", "")
            return render(
                request,
                self._error_template(container_id),
                {
                    "match": match,
                    "form": PlaceBetForm(),
                    "selection": selection_val,
                    "container_id": container_id,
                    "error": "This match is no longer accepting bets.",
                    **self._get_odds_context(match, selection_val, container_id),
                },
            )

        form = PlaceBetForm(request.POST)
        if not form.is_valid():
            selection_val = request.POST.get("selection", "")
            return render(
                request,
                self._error_template(container_id),
                {
                    "match": match,
                    "form": form,
                    "selection": selection_val,
                    "container_id": container_id,
                    "error": None,
                    **self._get_odds_context(match, selection_val, container_id),
                },
            )

        selection = form.cleaned_data["selection"]
        stake = form.cleaned_data["stake"]

        # Look up best odds for this selection
        odds_field = {
            BetSlip.Selection.HOME_WIN: "home_win",
            BetSlip.Selection.DRAW: "draw",
            BetSlip.Selection.AWAY_WIN: "away_win",
        }[selection]

        best_odds_val = (
            Odds.objects.filter(match=match).aggregate(best=Min(odds_field)).get("best")
        )
        if not best_odds_val:
            return render(
                request,
                self._error_template(container_id),
                {
                    "match": match,
                    "form": form,
                    "selection": selection,
                    "container_id": container_id,
                    "error": "No odds available for this match.",
                    **self._get_odds_context(match, selection, container_id),
                },
            )

        # Atomic: deduct balance + create bet
        try:
            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(user=request.user)

                if balance.balance < stake:
                    return render(
                        request,
                        self._error_template(container_id),
                        {
                            "match": match,
                            "form": form,
                            "selection": selection,
                            "container_id": container_id,
                            "error": f"Insufficient balance. You have {format_currency(balance.balance, request.user.currency)}.",
                            **self._get_odds_context(match, selection, container_id),
                        },
                    )

                match_label = (
                    f"{match.home_team.short_name or match.home_team.name}"
                    f" vs {match.away_team.short_name or match.away_team.name}"
                )
                log_transaction(
                    balance,
                    -stake,
                    BalanceTransaction.Type.BET_PLACEMENT,
                    f"Bet on {match_label}",
                )

                bet = BetSlip.objects.create(
                    user=request.user,
                    match=match,
                    selection=selection,
                    odds_at_placement=best_odds_val,
                    stake=stake,
                )
        except UserBalance.DoesNotExist:
            # Auto-create balance if missing (shouldn't happen with signup flow)
            balance = UserBalance.objects.create(
                user=request.user, balance=Decimal("1000.00") - stake
            )
            BalanceTransaction.objects.create(
                user=request.user,
                amount=Decimal("1000.00"),
                balance_after=Decimal("1000.00"),
                transaction_type=BalanceTransaction.Type.SIGNUP,
                description="Initial signup bonus",
            )
            BalanceTransaction.objects.create(
                user=request.user,
                amount=-stake,
                balance_after=balance.balance,
                transaction_type=BalanceTransaction.Type.BET_PLACEMENT,
                description=f"Bet on {match.home_team.short_name or match.home_team.name} vs {match.away_team.short_name or match.away_team.name}",
            )
            bet = BetSlip.objects.create(
                user=request.user,
                match=match,
                selection=selection,
                odds_at_placement=best_odds_val,
                stake=stake,
            )

        potential_payout = stake * best_odds_val

        # Update challenge progress (runs after any active transaction commits)
        _user = request.user
        _ctx = {
            "match": match,
            "odds": best_odds_val,
            "stake": stake,
            "selection": selection,
            "league": "epl",
        }
        transaction.on_commit(
            lambda: update_challenge_progress(_user, "bet_placed", _ctx)
        )

        return render(
            request,
            "epl_betting/partials/bet_confirmation.html",
            {
                "bet": bet,
                "match": match,
                "potential_payout": potential_payout,
                "balance": balance.balance,
                "sentiment": _get_match_sentiment(match),
            },
        )


class MyBetsView(LoginRequiredMixin, TemplateView):
    template_name = "epl_betting/my_bets.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        bets = BetSlip.objects.filter(user=user).select_related(
            "match__home_team", "match__away_team"
        )

        parlays = Parlay.objects.filter(user=user).prefetch_related(
            "legs__match__home_team", "legs__match__away_team"
        )

        bet_totals = bets.aggregate(
            total_staked=Sum("stake"),
            total_payout=Sum("payout"),
        )
        parlay_totals = parlays.aggregate(
            parlay_staked=Sum("stake"),
            parlay_payout=Sum("payout"),
        )
        total_staked = (bet_totals["total_staked"] or Decimal("0")) + (
            parlay_totals["parlay_staked"] or Decimal("0")
        )
        total_payout = (bet_totals["total_payout"] or Decimal("0")) + (
            parlay_totals["parlay_payout"] or Decimal("0")
        )

        balance = getattr(user, "balance", None)
        current_balance = balance.balance if balance else Decimal("1000.00")

        reward_distributions = RewardDistribution.objects.filter(
            user=user
        ).select_related("reward")
        total_rewards = reward_distributions.aggregate(total=Sum("reward__amount"))[
            "total"
        ] or Decimal("0")

        # Build unified activity feed sorted by date descending
        activity = []
        for bet in bets:
            activity.append({"type": "bet", "date": bet.created_at, "item": bet})
        for parlay in parlays:
            activity.append(
                {"type": "parlay", "date": parlay.created_at, "item": parlay}
            )
        for dist in reward_distributions:
            activity.append({"type": "reward", "date": dist.created_at, "item": dist})
        activity.sort(key=lambda a: a["date"], reverse=True)

        ctx["bets"] = bets
        ctx["total_staked"] = total_staked
        ctx["total_payout"] = total_payout
        ctx["net_pnl"] = total_payout - total_staked
        ctx["current_balance"] = current_balance
        ctx["total_rewards"] = total_rewards
        ctx["activity"] = activity
        return ctx


class ProfileView(TemplateView):
    """Public profile page showing a user's betting stats."""

    template_name = "epl_betting/profile.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        User = get_user_model()
        profile_user = get_object_or_404(User, slug=self.kwargs["slug"])

        if profile_user.is_superuser:
            raise Http404

        # Identity
        ctx["profile_user"] = profile_user
        ctx["display_identity"] = get_public_identity(profile_user)

        # Stats
        try:
            stats = profile_user.stats
        except UserStats.DoesNotExist:
            stats = None
        ctx["stats"] = stats

        # Balance & rank
        try:
            balance = profile_user.balance
            ctx["balance"] = balance.balance
        except UserBalance.DoesNotExist:
            ctx["balance"] = Decimal("1000.00")

        ctx["user_rank"] = get_user_rank(profile_user)

        # Recent bets (last 20 settled)
        recent_bets = (
            BetSlip.objects.filter(user=profile_user)
            .exclude(status=BetStatus.PENDING)
            .select_related("match__home_team", "match__away_team")
            .order_by("-created_at")[:20]
        )
        ctx["recent_bets"] = recent_bets

        # Recent parlays (last 10 settled)
        recent_parlays = (
            Parlay.objects.filter(user=profile_user)
            .exclude(status=BetStatus.PENDING)
            .prefetch_related("legs__match__home_team", "legs__match__away_team")
            .order_by("-created_at")[:10]
        )
        ctx["recent_parlays"] = recent_parlays

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

        # Balance chart: only show on own profile
        ctx["is_own_profile"] = (
            self.request.user.is_authenticated
            and self.request.user.pk == profile_user.pk
        )

        # Recent comments (last 20 non-deleted, newest first)
        recent_comments = (
            Comment.objects.filter(user=profile_user, is_deleted=False)
            .select_related("match__home_team", "match__away_team", "parent")
            .order_by("-created_at")[:20]
        )
        ctx["recent_comments"] = recent_comments

        return ctx


class BalanceHistoryAPI(LoginRequiredMixin, View):
    """Return daily balance history (last 10 days) as JSON for chart rendering."""

    WINDOW_DAYS = 10

    def get(self, request, slug):
        if request.user.slug != slug:
            return JsonResponse({"error": "Forbidden"}, status=403)

        all_txns = list(
            BalanceTransaction.objects.filter(user=request.user)
            .order_by("created_at")
            .values_list("created_at", "balance_after")
        )

        if not all_txns:
            return JsonResponse({"data": []})

        today = timezone.now().date()
        data = []
        for i in range(self.WINDOW_DAYS - 1, -1, -1):
            day = today - timedelta(days=i)
            # Walk backwards through transactions to find the last balance on or before this day
            day_balance = next(
                (bal for ts, bal in reversed(all_txns) if ts.date() <= day),
                None,
            )
            if day_balance is not None:
                data.append({"t": day.isoformat(), "y": float(day_balance)})

        return JsonResponse({"data": data})


class QuickBetFormView(LoginRequiredMixin, View):
    """Return an inline bet form for the odds board."""

    ODDS_FIELD_MAP = {
        "HOME_WIN": "home_win",
        "DRAW": "draw",
        "AWAY_WIN": "away_win",
    }

    def get(self, request, match_slug):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"),
            slug=match_slug,
        )
        selection = request.GET.get("selection", "")
        container_id = request.GET.get("container", "")
        form = PlaceBetForm(initial={"selection": selection})

        selected_odds = None
        odds_field = self.ODDS_FIELD_MAP.get(selection)
        if odds_field:
            result = Odds.objects.filter(match=match).aggregate(best=Min(odds_field))
            selected_odds = result.get("best")

        return render(
            request,
            "epl_betting/partials/quick_bet_form.html",
            {
                "match": match,
                "form": form,
                "selection": selection,
                "container_id": container_id,
                "selected_odds": selected_odds,
            },
        )


class BailoutView(LoginRequiredMixin, View):
    """Process a bailout request for a bankrupt user."""

    MIN_BET = Decimal("0.50")

    def post(self, request):
        with transaction.atomic():
            try:
                balance = UserBalance.objects.select_for_update().get(user=request.user)
            except UserBalance.DoesNotExist:
                return JsonResponse({"error": "No balance found."}, status=400)

            pending_count = BetSlip.objects.filter(
                user=request.user, status=BetStatus.PENDING
            ).count()
            pending_parlays = Parlay.objects.filter(
                user=request.user, status=BetStatus.PENDING
            ).count()

            if (
                balance.balance >= self.MIN_BET
                or pending_count > 0
                or pending_parlays > 0
            ):
                return JsonResponse({"error": "You are not bankrupt."}, status=400)

            bankruptcy = Bankruptcy.objects.create(
                user=request.user,
                balance_at_bankruptcy=balance.balance,
            )

            amount = random.randint(1000, 3000)

            Bailout.objects.create(
                user=request.user,
                bankruptcy=bankruptcy,
                amount=amount,
            )

            log_transaction(
                balance,
                Decimal(amount),
                BalanceTransaction.Type.BAILOUT,
                "Bankruptcy bailout",
            )

        return JsonResponse(
            {
                "success": True,
                "amount": amount,
                "new_balance": str(balance.balance),
            }
        )


# ── Parlay helpers ────────────────────────────────────────────────────────────

_PARLAY_SESSION_KEY = "parlay_slip"
_ODDS_FIELD_MAP = {
    BetSlip.Selection.HOME_WIN: "home_win",
    BetSlip.Selection.DRAW: "draw",
    BetSlip.Selection.AWAY_WIN: "away_win",
}


def _get_slip(request):
    """Return the current parlay slip from the session (list of dicts)."""
    return list(request.session.get(_PARLAY_SESSION_KEY, []))


def _save_slip(request, slip):
    request.session[_PARLAY_SESSION_KEY] = slip
    request.session.modified = True


def _build_slip_context(request):
    """Build the template context for the parlay slip panel (used by HTMX views)."""
    return _parlay_slip_ctx(request)


# ── Parlay slip management views ──────────────────────────────────────────────


class AddToParlayView(LoginRequiredMixin, View):
    """Add a selection to the session parlay slip."""

    def post(self, request):
        try:
            match_id = int(request.POST.get("match_id", 0))
        except (ValueError, TypeError):
            match_id = 0
        selection = request.POST.get("selection", "")

        if not match_id or selection not in dict(BetSlip.Selection.choices):
            return render(
                request,
                "epl_betting/partials/parlay_slip.html",
                {**_build_slip_context(request), "parlay_error": "Invalid selection."},
            )

        slip = _get_slip(request)

        # Enforce max legs
        if len(slip) >= PARLAY_MAX_LEGS:
            return render(
                request,
                "epl_betting/partials/parlay_slip.html",
                {
                    **_build_slip_context(request),
                    "parlay_error": f"Maximum {PARLAY_MAX_LEGS} legs allowed.",
                },
            )

        # Check for duplicate match
        if any(entry["match_id"] == match_id for entry in slip):
            return render(
                request,
                "epl_betting/partials/parlay_slip.html",
                {
                    **_build_slip_context(request),
                    "parlay_error": "This match is already in your parlay.",
                },
            )

        # Verify the match exists and is bettable
        try:
            match = Match.objects.get(
                pk=match_id,
                status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
            )
        except Match.DoesNotExist:
            return render(
                request,
                "epl_betting/partials/parlay_slip.html",
                {
                    **_build_slip_context(request),
                    "parlay_error": "Match not available for betting.",
                },
            )

        slip.append({"match_id": match.pk, "selection": selection})
        _save_slip(request, slip)

        return render(
            request,
            "epl_betting/partials/parlay_slip.html",
            _build_slip_context(request),
        )


class RemoveFromParlayView(LoginRequiredMixin, View):
    """Remove a leg from the session parlay slip."""

    def post(self, request):
        try:
            match_id = int(request.POST.get("match_id", 0))
        except (ValueError, TypeError):
            match_id = 0

        slip = [entry for entry in _get_slip(request) if entry["match_id"] != match_id]
        _save_slip(request, slip)

        return render(
            request,
            "epl_betting/partials/parlay_slip.html",
            _build_slip_context(request),
        )


class ClearParlayView(LoginRequiredMixin, View):
    """Clear the entire parlay slip."""

    def post(self, request):
        _save_slip(request, [])
        return render(
            request,
            "epl_betting/partials/parlay_slip.html",
            _build_slip_context(request),
        )


class ParlaySlipPartialView(LoginRequiredMixin, View):
    """Return the current parlay slip panel (GET, for initial page load)."""

    def get(self, request):
        return render(
            request,
            "epl_betting/partials/parlay_slip.html",
            _build_slip_context(request),
        )


class PlaceParlayView(LoginRequiredMixin, View):
    """Validate and place a parlay bet atomically."""

    def post(self, request):
        slip = _get_slip(request)

        def _error(msg):
            ctx = _build_slip_context(request)
            ctx["parlay_error"] = msg
            return render(request, "epl_betting/partials/parlay_slip.html", ctx)

        # Leg count validation
        if len(slip) < PARLAY_MIN_LEGS:
            return _error(f"A parlay requires at least {PARLAY_MIN_LEGS} selections.")
        if len(slip) > PARLAY_MAX_LEGS:
            return _error(f"Maximum {PARLAY_MAX_LEGS} legs allowed.")

        form = PlaceParlayForm(request.POST)
        if not form.is_valid():
            ctx = _build_slip_context(request)
            ctx["parlay_form"] = form
            ctx["parlay_error"] = "Please enter a valid stake."
            return render(request, "epl_betting/partials/parlay_slip.html", ctx)

        stake = form.cleaned_data["stake"]

        # Validate every match and collect odds
        leg_data = []  # [{"match": ..., "selection": ..., "odds": ...}]
        match_ids = [entry.get("match_id") for entry in slip if entry.get("match_id")]
        matches_by_id = {
            m.pk: m
            for m in Match.objects.filter(pk__in=match_ids).select_related(
                "home_team", "away_team"
            )
        }

        for entry in slip:
            match = matches_by_id.get(entry.get("match_id"))
            if not match:
                return _error("One or more matches could not be found.")
            if match.status not in (Match.Status.SCHEDULED, Match.Status.TIMED):
                return _error(
                    f"{match.home_team.short_name or match.home_team.name} vs "
                    f"{match.away_team.short_name or match.away_team.name} is no longer accepting bets."
                )
            selection = entry.get("selection", "")
            odds_field = _ODDS_FIELD_MAP.get(selection)
            if not odds_field:
                return _error("Invalid selection in parlay.")
            best_odds = (
                Odds.objects.filter(match=match)
                .aggregate(best=Min(odds_field))
                .get("best")
            )
            if not best_odds:
                return _error(
                    f"No odds available for "
                    f"{match.home_team.short_name or match.home_team.name} vs "
                    f"{match.away_team.short_name or match.away_team.name}."
                )
            leg_data.append({"match": match, "selection": selection, "odds": best_odds})

        # Compute combined odds
        combined_odds = Decimal("1.00")
        for ld in leg_data:
            combined_odds *= ld["odds"]
        combined_odds = combined_odds.quantize(Decimal("0.01"))

        potential_payout = min(stake * combined_odds, PARLAY_MAX_PAYOUT)

        # Deduplicate leg_data by match (defensive against concurrent add requests)
        seen_match_ids = set()
        unique_leg_data = []
        for ld in leg_data:
            if ld["match"].pk not in seen_match_ids:
                seen_match_ids.add(ld["match"].pk)
                unique_leg_data.append(ld)
        leg_data = unique_leg_data

        # Atomic: deduct balance + create Parlay + ParlayLegs
        try:
            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(user=request.user)

                if balance.balance < stake:
                    return _error(
                        f"Insufficient balance. You have {format_currency(balance.balance, request.user.currency)}."
                    )

                log_transaction(
                    balance,
                    -stake,
                    BalanceTransaction.Type.PARLAY_PLACEMENT,
                    f"Parlay with {len(leg_data)} legs",
                )

                parlay = Parlay.objects.create(
                    user=request.user,
                    stake=stake,
                    combined_odds=combined_odds,
                    max_payout=PARLAY_MAX_PAYOUT,
                )
                ParlayLeg.objects.bulk_create(
                    [
                        ParlayLeg(
                            parlay=parlay,
                            match=ld["match"],
                            selection=ld["selection"],
                            odds_at_placement=ld["odds"],
                        )
                        for ld in leg_data
                    ]
                )
        except UserBalance.DoesNotExist:
            return _error("Balance not found. Please refresh and try again.")
        except IntegrityError:
            return _error(
                "Duplicate match detected in parlay. Please clear and rebuild your slip."
            )

        # Clear session slip
        _save_slip(request, [])

        # Update challenge progress
        _user = request.user
        _ctx = {
            "stake": stake,
            "leg_count": len(leg_data),
            "combined_odds": combined_odds,
            "league": "epl",
        }
        transaction.on_commit(
            lambda: update_challenge_progress(_user, "parlay_placed", _ctx)
        )

        return render(
            request,
            "epl_betting/partials/parlay_confirmation.html",
            {
                "parlay": parlay,
                "leg_data": leg_data,
                "combined_odds": combined_odds,
                "potential_payout": potential_payout,
                "stake": stake,
                "balance": balance.balance,
            },
        )


class PlaceFeaturedParlayView(LoginRequiredMixin, View):
    """Place a parlay matching a featured parlay's legs at a user-chosen stake."""

    def _card_error(self, request, fp, msg):
        return render(
            request,
            "vinosports/betting/featured_parlay_card.html",
            {"parlay": fp, "featured_error": msg},
        )

    def post(self, request, pk):
        fp = get_object_or_404(
            FeaturedParlay.objects.prefetch_related("legs"),
            pk=pk,
            league="epl",
            status=FeaturedParlay.Status.ACTIVE,
        )

        # Validate stake from form input
        try:
            stake = Decimal(request.POST.get("stake", ""))
        except Exception:
            return self._card_error(request, fp, "Please enter a valid wager amount.")
        if stake < Decimal("0.50"):
            return self._card_error(request, fp, "Minimum wager is $0.50.")
        if stake > Decimal("10000"):
            return self._card_error(request, fp, "Maximum wager is $10,000.")

        # Prevent duplicate opt-ins
        if Parlay.objects.filter(user=request.user, featured_parlay=fp).exists():
            return render(
                request,
                "vinosports/betting/featured_parlay_card.html",
                {"parlay": fp, "featured_error": "You've already placed this parlay."},
            )

        legs = list(fp.legs.all())
        if len(legs) < PARLAY_MIN_LEGS:
            return render(
                request,
                "vinosports/betting/featured_parlay_card.html",
                {
                    "parlay": fp,
                    "featured_error": "This parlay doesn't have enough legs.",
                },
            )

        # Validate every leg and collect current odds
        match_ids = [leg.event_id for leg in legs]
        matches_by_id = {
            m.pk: m
            for m in Match.objects.filter(pk__in=match_ids).select_related(
                "home_team", "away_team"
            )
        }

        leg_data = []
        for leg in legs:
            match = matches_by_id.get(leg.event_id)
            if not match or match.status not in (
                Match.Status.SCHEDULED,
                Match.Status.TIMED,
            ):
                return render(
                    request,
                    "vinosports/betting/featured_parlay_card.html",
                    {
                        "parlay": fp,
                        "featured_error": f"{leg.event_label} is no longer accepting bets.",
                    },
                )
            odds_field = _ODDS_FIELD_MAP.get(leg.selection)
            if not odds_field:
                return render(
                    request,
                    "vinosports/betting/featured_parlay_card.html",
                    {"parlay": fp, "featured_error": "Invalid selection in parlay."},
                )
            best_odds = (
                Odds.objects.filter(match=match)
                .aggregate(best=Min(odds_field))
                .get("best")
            )
            if not best_odds:
                return render(
                    request,
                    "vinosports/betting/featured_parlay_card.html",
                    {
                        "parlay": fp,
                        "featured_error": f"No odds available for {leg.event_label}.",
                    },
                )
            leg_data.append(
                {"match": match, "selection": leg.selection, "odds": best_odds}
            )

        # Compute combined odds
        combined_odds = Decimal("1.00")
        for ld in leg_data:
            combined_odds *= ld["odds"]
        combined_odds = combined_odds.quantize(Decimal("0.01"))

        potential_payout = min(stake * combined_odds, PARLAY_MAX_PAYOUT)

        try:
            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(user=request.user)

                if balance.balance < stake:
                    return render(
                        request,
                        "vinosports/betting/featured_parlay_card.html",
                        {
                            "parlay": fp,
                            "featured_error": f"Insufficient balance. You have {format_currency(balance.balance, request.user.currency)}.",
                        },
                    )

                log_transaction(
                    balance,
                    -stake,
                    BalanceTransaction.Type.PARLAY_PLACEMENT,
                    f"Featured parlay: {fp.title}",
                )

                parlay = Parlay.objects.create(
                    user=request.user,
                    stake=stake,
                    combined_odds=combined_odds,
                    max_payout=PARLAY_MAX_PAYOUT,
                    featured_parlay=fp,
                )
                ParlayLeg.objects.bulk_create(
                    [
                        ParlayLeg(
                            parlay=parlay,
                            match=ld["match"],
                            selection=ld["selection"],
                            odds_at_placement=ld["odds"],
                        )
                        for ld in leg_data
                    ]
                )
        except UserBalance.DoesNotExist:
            return render(
                request,
                "vinosports/betting/featured_parlay_card.html",
                {
                    "parlay": fp,
                    "featured_error": "Balance not found. Please refresh and try again.",
                },
            )

        # Update challenge progress
        _user = request.user
        _ctx = {
            "stake": stake,
            "leg_count": len(leg_data),
            "combined_odds": combined_odds,
            "league": "epl",
        }
        transaction.on_commit(
            lambda: update_challenge_progress(_user, "parlay_placed", _ctx)
        )

        return render(
            request,
            "vinosports/betting/featured_parlay_confirmed.html",
            {
                "parlay": parlay,
                "featured_parlay": fp,
                "leg_data": leg_data,
                "combined_odds": combined_odds,
                "potential_payout": potential_payout,
                "stake": stake,
                "balance": balance.balance,
                "my_bets_url": "epl_betting:my_bets",
            },
        )
