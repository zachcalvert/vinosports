import logging
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Count, Min
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import TemplateView

from vinosports.betting.balance import log_transaction
from vinosports.betting.constants import (
    PARLAY_MAX_LEGS,
    PARLAY_MAX_PAYOUT,
    PARLAY_MIN_LEGS,
)
from vinosports.betting.models import BalanceTransaction, UserBalance
from worldcup.betting.forms import PlaceBetForm, PlaceFuturesBetForm, PlaceParlayForm
from worldcup.betting.models import (
    BetSlip,
    FuturesBet,
    FuturesMarket,
    FuturesOutcome,
    Parlay,
    ParlayLeg,
)
from worldcup.matches.models import Match, Odds
from worldcup.website.templatetags.currency_tags import format_currency

logger = logging.getLogger(__name__)

ODDS_FIELD_MAP = {
    "HOME_WIN": "home_win",
    "DRAW": "draw",
    "AWAY_WIN": "away_win",
}

_WC_PARLAY_SESSION_KEY = "wc_parlay_slip"
_PARLAY_ODDS_FIELD_MAP = {
    BetSlip.Selection.HOME_WIN: "home_win",
    BetSlip.Selection.DRAW: "draw",
    BetSlip.Selection.AWAY_WIN: "away_win",
}


def _get_match_sentiment(match):
    """Return sentiment dict for a match, or None if no bets placed."""
    qs = BetSlip.objects.filter(match=match)
    total = qs.count()
    if not total:
        return None

    counts = {
        row["selection"]: row["cnt"]
        for row in qs.values("selection").annotate(cnt=Count("id"))
    }

    def pct(sel):
        return round(counts.get(sel, 0) / total * 100)

    home_pct = pct(BetSlip.Selection.HOME_WIN)
    draw_pct = pct(BetSlip.Selection.DRAW)
    away_pct = pct(BetSlip.Selection.AWAY_WIN)

    most = max(counts, key=counts.get, default=None)
    most_popular = dict(BetSlip.Selection.choices).get(most, "") if most else ""

    return {
        "total": total,
        "home_pct": home_pct,
        "draw_pct": draw_pct,
        "away_pct": away_pct,
        "most_popular": most_popular,
    }


# ── Parlay session helpers ─────────────────────────────────────────────────────


def _wc_get_slip(request):
    return list(request.session.get(_WC_PARLAY_SESSION_KEY, []))


def _wc_save_slip(request, slip):
    request.session[_WC_PARLAY_SESSION_KEY] = slip
    request.session.modified = True


def _wc_build_slip_context(request):
    """Build parlay slip template context (mirrors context_processors.parlay_slip)."""
    if not request.user.is_authenticated:
        return {
            "parlay_leg_count": 0,
            "parlay_legs_needed": PARLAY_MIN_LEGS,
            "parlay_legs": [],
            "parlay_combined_odds": None,
            "parlay_min_legs": PARLAY_MIN_LEGS,
            "parlay_max_legs": PARLAY_MAX_LEGS,
            "parlay_max_payout": PARLAY_MAX_PAYOUT,
            "parlay_form": PlaceParlayForm(),
        }

    raw = _wc_get_slip(request)
    match_ids = {e.get("match_id") for e in raw if e.get("match_id")}
    matches_by_id = (
        {
            m.pk: m
            for m in Match.objects.filter(pk__in=match_ids).select_related(
                "home_team", "away_team"
            )
        }
        if match_ids
        else {}
    )

    legs = []
    combined_odds = Decimal("1.00")
    for entry in raw:
        match = matches_by_id.get(entry.get("match_id"))
        if not match:
            continue
        selection = entry.get("selection", "")
        odds_field = _PARLAY_ODDS_FIELD_MAP.get(selection)
        best_odds = None
        if odds_field:
            best_odds = (
                Odds.objects.filter(match=match)
                .aggregate(best=Min(odds_field))
                .get("best")
            )
        legs.append(
            {
                "match": match,
                "selection": selection,
                "selection_display": dict(BetSlip.Selection.choices).get(
                    selection, selection
                ),
                "odds": best_odds,
            }
        )
        if best_odds:
            combined_odds *= best_odds

    if not legs:
        combined_odds = Decimal("1.00")

    leg_count = len(legs)
    return {
        "parlay_legs": legs,
        "parlay_combined_odds": combined_odds if legs else None,
        "parlay_leg_count": leg_count,
        "parlay_legs_needed": max(0, PARLAY_MIN_LEGS - leg_count),
        "parlay_min_legs": PARLAY_MIN_LEGS,
        "parlay_max_legs": PARLAY_MAX_LEGS,
        "parlay_max_payout": PARLAY_MAX_PAYOUT,
        "parlay_form": PlaceParlayForm(),
    }


class OddsBoardView(TemplateView):
    template_name = "worldcup_betting/odds_board.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        upcoming = (
            Match.objects.filter(
                status__in=[Match.Status.SCHEDULED, Match.Status.TIMED]
            )
            .select_related("home_team", "away_team", "stage", "group")
            .order_by("kickoff")
        )

        bettable = {Match.Status.SCHEDULED, Match.Status.TIMED}
        matches_with_odds = []
        for match in upcoming:
            odds = match.odds.first()
            matches_with_odds.append(
                {
                    "match": match,
                    "odds": odds,
                    "is_bettable": match.status in bettable,
                }
            )

        ctx["matches_with_odds"] = matches_with_odds
        return ctx


class OddsBoardPartialView(OddsBoardView):
    template_name = "worldcup_betting/partials/odds_board_body.html"


class QuickBetFormView(LoginRequiredMixin, View):
    """Return an inline bet form for a specific selection."""

    def get(self, request, match_slug):
        match = get_object_or_404(
            Match.objects.select_related("home_team", "away_team"),
            slug=match_slug,
        )
        selection = request.GET.get("selection", "")
        container_id = request.GET.get("container", "")

        selected_odds = None
        odds_field = ODDS_FIELD_MAP.get(selection)
        if odds_field:
            result = Odds.objects.filter(match=match).aggregate(best=Min(odds_field))
            selected_odds = result.get("best")

        return render(
            request,
            "worldcup_betting/partials/quick_bet_form.html",
            {
                "match": match,
                "form": PlaceBetForm(initial={"selection": selection}),
                "selection": selection,
                "container_id": container_id,
                "selected_odds": selected_odds,
            },
        )


class PlaceBetView(LoginRequiredMixin, View):
    """Handle bet placement via HTMX POST."""

    def _error_template(self, container_id):
        if container_id:
            return "worldcup_betting/partials/quick_bet_form.html"
        return "worldcup_betting/partials/bet_form.html"

    def _get_odds_context(self, match, selection="", container_id=""):
        if container_id:
            odds_field = ODDS_FIELD_MAP.get(selection)
            if odds_field:
                result = Odds.objects.filter(match=match).aggregate(
                    best=Min(odds_field)
                )
                return {"selected_odds": result.get("best")}
            return {}
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
                status=422,
            )

        selection = form.cleaned_data["selection"]
        stake = form.cleaned_data["stake"]

        odds_field = ODDS_FIELD_MAP[selection]
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

        match_label = (
            f"{match.home_team.short_name or match.home_team.name}"
            f" vs {match.away_team.short_name or match.away_team.name}"
        )

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
                            "error": (
                                f"Insufficient balance. You have "
                                f"{format_currency(balance.balance, request.user.currency)}."
                            ),
                            **self._get_odds_context(match, selection, container_id),
                        },
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

                from hub.consumers import notify_admin_dashboard

                notify_admin_dashboard("new_bet")

        except UserBalance.DoesNotExist:
            balance = UserBalance.objects.create(
                user=request.user, balance=Decimal("100000.00") - stake
            )
            BalanceTransaction.objects.create(
                user=request.user,
                amount=Decimal("100000.00"),
                balance_after=Decimal("100000.00"),
                transaction_type=BalanceTransaction.Type.SIGNUP,
                description="Initial signup bonus",
            )
            BalanceTransaction.objects.create(
                user=request.user,
                amount=-stake,
                balance_after=balance.balance,
                transaction_type=BalanceTransaction.Type.BET_PLACEMENT,
                description=f"Bet on {match_label}",
            )
            bet = BetSlip.objects.create(
                user=request.user,
                match=match,
                selection=selection,
                odds_at_placement=best_odds_val,
                stake=stake,
            )

        potential_payout = stake * best_odds_val
        sentiment = _get_match_sentiment(match)

        return render(
            request,
            "worldcup_betting/partials/bet_confirmation.html",
            {
                "bet": bet,
                "match": match,
                "potential_payout": potential_payout,
                "balance": balance.balance,
                "sentiment": sentiment,
            },
        )


# ── Parlay views ───────────────────────────────────────────────────────────────


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
                "worldcup_betting/partials/parlay_slip.html",
                {
                    **_wc_build_slip_context(request),
                    "parlay_error": "Invalid selection.",
                },
            )

        slip = _wc_get_slip(request)

        if len(slip) >= PARLAY_MAX_LEGS:
            return render(
                request,
                "worldcup_betting/partials/parlay_slip.html",
                {
                    **_wc_build_slip_context(request),
                    "parlay_error": f"Maximum {PARLAY_MAX_LEGS} legs allowed.",
                },
            )

        if any(entry["match_id"] == match_id for entry in slip):
            return render(
                request,
                "worldcup_betting/partials/parlay_slip.html",
                {
                    **_wc_build_slip_context(request),
                    "parlay_error": "This match is already in your parlay.",
                },
            )

        try:
            match = Match.objects.get(
                pk=match_id,
                status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
            )
        except Match.DoesNotExist:
            return render(
                request,
                "worldcup_betting/partials/parlay_slip.html",
                {
                    **_wc_build_slip_context(request),
                    "parlay_error": "Match not available for betting.",
                },
            )

        slip.append({"match_id": match.pk, "selection": selection})
        _wc_save_slip(request, slip)

        return render(
            request,
            "worldcup_betting/partials/parlay_slip.html",
            _wc_build_slip_context(request),
        )


class RemoveFromParlayView(LoginRequiredMixin, View):
    """Remove a leg from the session parlay slip."""

    def post(self, request):
        try:
            match_id = int(request.POST.get("match_id", 0))
        except (ValueError, TypeError):
            match_id = 0

        slip = [e for e in _wc_get_slip(request) if e["match_id"] != match_id]
        _wc_save_slip(request, slip)

        return render(
            request,
            "worldcup_betting/partials/parlay_slip.html",
            _wc_build_slip_context(request),
        )


class ClearParlayView(LoginRequiredMixin, View):
    """Clear the entire parlay slip."""

    def post(self, request):
        _wc_save_slip(request, [])
        return render(
            request,
            "worldcup_betting/partials/parlay_slip.html",
            _wc_build_slip_context(request),
        )


class PlaceParlayView(LoginRequiredMixin, View):
    """Validate and place a parlay bet atomically."""

    def post(self, request):
        slip = _wc_get_slip(request)

        def _error(msg):
            ctx = _wc_build_slip_context(request)
            ctx["parlay_error"] = msg
            return render(request, "worldcup_betting/partials/parlay_slip.html", ctx)

        if len(slip) < PARLAY_MIN_LEGS:
            return _error(f"A parlay requires at least {PARLAY_MIN_LEGS} selections.")
        if len(slip) > PARLAY_MAX_LEGS:
            return _error(f"Maximum {PARLAY_MAX_LEGS} legs allowed.")

        form = PlaceParlayForm(request.POST)
        if not form.is_valid():
            ctx = _wc_build_slip_context(request)
            ctx["parlay_form"] = form
            ctx["parlay_error"] = "Please enter a valid stake."
            return render(request, "worldcup_betting/partials/parlay_slip.html", ctx)

        stake = form.cleaned_data["stake"]

        match_ids = [e.get("match_id") for e in slip if e.get("match_id")]
        matches_by_id = {
            m.pk: m
            for m in Match.objects.filter(pk__in=match_ids).select_related(
                "home_team", "away_team"
            )
        }

        leg_data = []
        for entry in slip:
            match = matches_by_id.get(entry.get("match_id"))
            if not match:
                return _error("One or more matches could not be found.")
            if match.status not in (Match.Status.SCHEDULED, Match.Status.TIMED):
                return _error(
                    f"{match.home_team.short_name or match.home_team.name} vs "
                    f"{match.away_team.short_name or match.away_team.name} "
                    "is no longer accepting bets."
                )
            selection = entry.get("selection", "")
            odds_field = _PARLAY_ODDS_FIELD_MAP.get(selection)
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

        combined_odds = Decimal("1.00")
        for ld in leg_data:
            combined_odds *= ld["odds"]
        combined_odds = combined_odds.quantize(Decimal("0.01"))

        potential_payout = min(stake * combined_odds, PARLAY_MAX_PAYOUT)

        # Deduplicate
        seen = set()
        unique_legs = []
        for ld in leg_data:
            if ld["match"].pk not in seen:
                seen.add(ld["match"].pk)
                unique_legs.append(ld)
        leg_data = unique_legs

        try:
            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(user=request.user)

                if balance.balance < stake:
                    return _error(
                        f"Insufficient balance. You have "
                        f"{format_currency(balance.balance, request.user.currency)}."
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

                from hub.consumers import notify_admin_dashboard

                notify_admin_dashboard("new_bet")

        except UserBalance.DoesNotExist:
            return _error("Balance not found. Please refresh and try again.")
        except IntegrityError:
            return _error(
                "Duplicate match detected in parlay. Please clear and rebuild your slip."
            )

        _wc_save_slip(request, [])

        return render(
            request,
            "worldcup_betting/partials/parlay_confirmation.html",
            {
                "parlay": parlay,
                "leg_data": leg_data,
                "combined_odds": combined_odds,
                "potential_payout": potential_payout,
                "stake": stake,
                "balance": balance.balance,
            },
        )


# ── Futures views ──────────────────────────────────────────────────────────────


class FuturesView(TemplateView):
    """List all open WC futures markets."""

    template_name = "worldcup_betting/futures/futures_list.html"

    def get_context_data(self, **kwargs):
        from vinosports.betting.models import FuturesMarketStatus

        ctx = super().get_context_data(**kwargs)
        markets = (
            FuturesMarket.objects.filter(
                season="2026",
                status=FuturesMarketStatus.OPEN,
            )
            .select_related("group")
            .order_by("market_type")
        )

        winner = None
        finalist = None
        group_winners = []

        for market in markets:
            if market.market_type == FuturesMarket.MarketType.WINNER:
                outcomes = (
                    FuturesOutcome.objects.filter(market=market, is_active=True)
                    .select_related("team")
                    .order_by("odds")[:10]
                )
                winner = {"market": market, "outcomes": outcomes}
            elif market.market_type == FuturesMarket.MarketType.FINALIST:
                outcomes = (
                    FuturesOutcome.objects.filter(market=market, is_active=True)
                    .select_related("team")
                    .order_by("odds")[:8]
                )
                finalist = {"market": market, "outcomes": outcomes}
            elif market.market_type == FuturesMarket.MarketType.GROUP_WINNER:
                outcomes = (
                    FuturesOutcome.objects.filter(market=market, is_active=True)
                    .select_related("team")
                    .order_by("odds")[:4]
                )
                group_winners.append({"market": market, "outcomes": outcomes})

        group_winners.sort(
            key=lambda x: x["market"].group.letter if x["market"].group else ""
        )

        ctx["winner"] = winner
        ctx["finalist"] = finalist
        ctx["group_winners"] = group_winners
        return ctx


class FuturesMarketDetailView(TemplateView):
    """Show all outcomes for a single futures market."""

    template_name = "worldcup_betting/futures/futures_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        market = get_object_or_404(FuturesMarket, id_hash=kwargs["id_hash"])
        outcomes = (
            FuturesOutcome.objects.filter(market=market, is_active=True)
            .select_related("team")
            .order_by("odds")
        )
        ctx["market"] = market
        ctx["outcomes"] = outcomes
        return ctx


class FuturesBetFormView(LoginRequiredMixin, View):
    """HTMX GET — return inline bet form for a futures outcome."""

    def get(self, request, id_hash):
        outcome = get_object_or_404(
            FuturesOutcome.objects.select_related("market", "team"),
            id_hash=id_hash,
        )
        return render(
            request,
            "worldcup_betting/futures/partials/_bet_form.html",
            {"outcome": outcome, "form": PlaceFuturesBetForm()},
        )


class PlaceFuturesBetView(LoginRequiredMixin, View):
    """Handle futures bet placement via HTMX POST."""

    def post(self, request, id_hash):
        from vinosports.betting.models import FuturesMarketStatus

        outcome = get_object_or_404(
            FuturesOutcome.objects.select_related("market", "team"),
            id_hash=id_hash,
        )

        if outcome.market.status != FuturesMarketStatus.OPEN:
            return render(
                request,
                "worldcup_betting/futures/partials/_bet_form.html",
                {
                    "outcome": outcome,
                    "form": PlaceFuturesBetForm(),
                    "error": "This market is no longer accepting bets.",
                },
            )

        form = PlaceFuturesBetForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "worldcup_betting/futures/partials/_bet_form.html",
                {"outcome": outcome, "form": form, "error": "Invalid stake."},
            )

        stake = form.cleaned_data["stake"]

        try:
            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(user=request.user)
                if balance.balance < stake:
                    return render(
                        request,
                        "worldcup_betting/futures/partials/_bet_form.html",
                        {
                            "outcome": outcome,
                            "form": form,
                            "error": "Insufficient balance.",
                        },
                    )

                log_transaction(
                    balance,
                    -stake,
                    BalanceTransaction.Type.FUTURES_PLACEMENT,
                    f"Futures: {outcome.team.name} — {outcome.market.name}",
                )

                bet = FuturesBet.objects.create(
                    user=request.user,
                    outcome=outcome,
                    stake=stake,
                    odds_at_placement=outcome.odds,
                )

        except Exception:
            logger.exception("PlaceFuturesBetView: error placing bet")
            return render(
                request,
                "worldcup_betting/futures/partials/_bet_form.html",
                {
                    "outcome": outcome,
                    "form": form,
                    "error": "Something went wrong. Please try again.",
                },
            )

        potential_payout = (stake * bet.odds_at_placement).quantize(Decimal("0.01"))

        return render(
            request,
            "worldcup_betting/futures/partials/_bet_confirmation.html",
            {
                "bet": bet,
                "outcome": outcome,
                "potential_payout": potential_payout,
            },
        )
