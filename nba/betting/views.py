import logging
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from nba.betting.balance import log_transaction
from nba.betting.context_processors import PARLAY_SESSION_KEY
from nba.betting.forms import PlaceBetForm, PlaceFuturesBetForm, PlaceParlayForm
from nba.betting.models import (
    BetSlip,
    FuturesBet,
    FuturesMarket,
    FuturesOutcome,
    Parlay,
    ParlayLeg,
)
from nba.betting.settlement import (
    american_to_decimal,
    calculate_payout,
    decimal_to_american,
    grant_bailout,
)
from nba.games.models import Game, GameStatus
from vinosports.betting.constants import PARLAY_MAX_LEGS, PARLAY_MIN_LEGS
from vinosports.betting.featured import FeaturedParlay
from vinosports.betting.models import BalanceTransaction, UserBalance
from vinosports.challenges.engine import update_challenge_progress

logger = logging.getLogger(__name__)


class BetFormView(LoginRequiredMixin, View):
    def get(self, request, id_hash):
        game = get_object_or_404(Game, id_hash=id_hash, status=GameStatus.SCHEDULED)
        best_odds = game.odds.order_by("-fetched_at").first()
        return render(
            request,
            "nba_betting/partials/bet_form.html",
            {
                "game": game,
                "best_odds": best_odds,
                "bet_form": PlaceBetForm(),
            },
        )


class QuickBetFormView(LoginRequiredMixin, View):
    """Return a compact inline bet form for game cards (dashboard / schedule)."""

    MARKET_ODDS_MAP = {
        ("MONEYLINE", "HOME"): "home_moneyline",
        ("MONEYLINE", "AWAY"): "away_moneyline",
        ("SPREAD", "HOME"): "spread_home",
        ("SPREAD", "AWAY"): "spread_away",
        ("TOTAL", "OVER"): "over_odds",
        ("TOTAL", "UNDER"): "under_odds",
    }

    def get(self, request, id_hash):
        game = get_object_or_404(
            Game.objects.select_related("home_team", "away_team"),
            id_hash=id_hash,
        )
        market = request.GET.get("market", "MONEYLINE")
        selection = request.GET.get("selection", "HOME")
        container_id = request.GET.get("container", "")

        best_odds = game.odds.order_by("-fetched_at").first()
        odds_field = self.MARKET_ODDS_MAP.get((market, selection))
        selected_odds = (
            getattr(best_odds, odds_field, None) if best_odds and odds_field else None
        )

        line = None
        if best_odds and market == "SPREAD":
            line = (
                best_odds.spread_line
                if selection == "HOME"
                else (-best_odds.spread_line if best_odds.spread_line else None)
            )
        elif best_odds and market == "TOTAL":
            line = best_odds.total_line

        return render(
            request,
            "nba_betting/partials/quick_bet_form.html",
            {
                "game": game,
                "market": market,
                "selection": selection,
                "container_id": container_id,
                "selected_odds": selected_odds,
                "line": line,
            },
        )


class PlaceBetView(LoginRequiredMixin, View):
    def _error_template(self, container_id):
        if container_id:
            return "nba_betting/partials/quick_bet_form.html"
        return "nba_betting/partials/bet_form.html"

    def _quick_bet_context(self, game, request_post):
        """Build context for re-rendering the quick bet form on error."""
        market = request_post.get("market", "MONEYLINE")
        selection = request_post.get("selection", "HOME")
        container_id = request_post.get("container_id", "")
        odds_val = request_post.get("odds")
        line_val = request_post.get("line")
        return {
            "game": game,
            "market": market,
            "selection": selection,
            "container_id": container_id,
            "selected_odds": int(odds_val) if odds_val else None,
            "line": float(line_val) if line_val else None,
        }

    def post(self, request, id_hash):
        game = get_object_or_404(Game, id_hash=id_hash, status=GameStatus.SCHEDULED)
        form = PlaceBetForm(request.POST)
        container_id = request.POST.get("container_id", "")

        if not form.is_valid():
            if getattr(request, "htmx", False):
                if container_id:
                    return render(
                        request,
                        self._error_template(container_id),
                        {
                            **self._quick_bet_context(game, request.POST),
                            "error": "Please check your bet details.",
                        },
                    )
                best_odds = game.odds.order_by("-fetched_at").first()
                return render(
                    request,
                    "nba_betting/partials/bet_form.html",
                    {
                        "game": game,
                        "best_odds": best_odds,
                        "bet_form": form,
                        "error": "Please check your bet details.",
                    },
                )
            return HttpResponse("Invalid form", status=400)

        market = form.cleaned_data["market"]
        selection = form.cleaned_data["selection"]
        odds = form.cleaned_data["odds"]
        line = form.cleaned_data.get("line")
        stake = form.cleaned_data["stake"]

        try:
            log_transaction(
                request.user,
                -stake,
                BalanceTransaction.Type.BET_PLACEMENT,
                f"Bet on {game}",
            )
        except ValueError:
            if getattr(request, "htmx", False):
                if container_id:
                    return render(
                        request,
                        self._error_template(container_id),
                        {
                            **self._quick_bet_context(game, request.POST),
                            "error": "Insufficient balance.",
                        },
                    )
                best_odds = game.odds.order_by("-fetched_at").first()
                return render(
                    request,
                    "nba_betting/partials/bet_form.html",
                    {
                        "game": game,
                        "best_odds": best_odds,
                        "bet_form": PlaceBetForm(request.POST),
                        "error": "Insufficient balance.",
                    },
                )
            return HttpResponse("Insufficient balance", status=400)

        bet = BetSlip.objects.create(
            user=request.user,
            game=game,
            market=market,
            selection=selection,
            odds_at_placement=odds,
            line=line,
            stake=stake,
        )

        _user = request.user
        _ctx = {
            "game": game,
            "odds": odds,
            "stake": stake,
            "selection": selection,
            "league": "nba",
        }
        transaction.on_commit(
            lambda: update_challenge_progress(_user, "bet_placed", _ctx)
        )

        from nba.activity.services import queue_activity_event

        queue_activity_event(
            "user_bet",
            f"{request.user.display_name or request.user.email} bet ${stake} on {game}",
            url=game.get_absolute_url(),
            icon="coin",
        )

        if getattr(request, "htmx", False):
            if container_id:
                return render(
                    request,
                    "nba_betting/partials/quick_bet_confirmation.html",
                    {
                        "bet": bet,
                        "game": game,
                        "container_id": container_id,
                    },
                )
            from nba.games.views import (
                _get_game_sentiment,
                _get_spread_sentiment,
                _get_total_sentiment,
            )

            return render(
                request,
                "nba_betting/partials/bet_confirmation.html",
                {
                    "bet": bet,
                    "game": game,
                    "sentiment": _get_game_sentiment(game),
                    "spread_sentiment": _get_spread_sentiment(game),
                    "total_sentiment": _get_total_sentiment(game),
                },
            )
        return redirect("nba_games:game_detail", id_hash=game.id_hash)


class MyBetsView(LoginRequiredMixin, View):
    def get(self, request):
        tab = request.GET.get("tab", "pending")
        from vinosports.betting.models import BetStatus

        if tab == "pending":
            bets = BetSlip.objects.filter(user=request.user, status=BetStatus.PENDING)
        elif tab == "won":
            bets = BetSlip.objects.filter(user=request.user, status=BetStatus.WON)
        elif tab == "lost":
            bets = BetSlip.objects.filter(user=request.user, status=BetStatus.LOST)
        else:
            bets = BetSlip.objects.filter(user=request.user)

        bets = bets.select_related(
            "game", "game__home_team", "game__away_team"
        ).order_by("-created_at")[:50]
        parlays = (
            Parlay.objects.filter(user=request.user)
            .prefetch_related("legs__game__home_team", "legs__game__away_team")
            .order_by("-created_at")[:20]
        )

        ctx = {
            "bets": bets,
            "parlays": parlays,
            "tab": tab,
        }

        if getattr(request, "htmx", False):
            return render(request, "nba_betting/partials/bet_list.html", ctx)
        return render(request, "nba_betting/my_bets.html", ctx)


class BailoutView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            grant_bailout(request.user)
        except ValueError:
            return HttpResponse("Not eligible for bailout", status=400)

        from nba.activity.services import queue_activity_event

        queue_activity_event(
            "bailout",
            f"{request.user.display_name or request.user.email} received a bailout!",
            icon="life-buoy",
        )
        return redirect("/")


class AddToParlayView(LoginRequiredMixin, View):
    def post(self, request):
        game_id = request.POST.get("game_id")
        market = request.POST.get("market")
        selection = request.POST.get("selection")
        odds = request.POST.get("odds")
        line = request.POST.get("line")

        slip = request.session.get(PARLAY_SESSION_KEY, [])

        if len(slip) >= PARLAY_MAX_LEGS:
            return HttpResponse("Max legs reached", status=400)

        for leg in slip:
            if str(leg.get("game_id")) == str(game_id):
                return HttpResponse("Game already in parlay", status=400)

        slip.append(
            {
                "game_id": int(game_id),
                "market": market,
                "selection": selection,
                "odds": int(odds) if odds else None,
                "line": float(line) if line else None,
            }
        )
        request.session[PARLAY_SESSION_KEY] = slip
        request.session.modified = True

        if getattr(request, "htmx", False):
            return render(request, "nba_betting/partials/parlay_slip.html")
        return redirect(request.META.get("HTTP_REFERER", "/"))


class RemoveFromParlayView(LoginRequiredMixin, View):
    def post(self, request):
        game_id = request.POST.get("game_id")
        slip = request.session.get(PARLAY_SESSION_KEY, [])
        slip = [leg for leg in slip if str(leg.get("game_id")) != str(game_id)]
        request.session[PARLAY_SESSION_KEY] = slip
        request.session.modified = True

        if getattr(request, "htmx", False):
            return render(request, "nba_betting/partials/parlay_slip.html")
        return redirect(request.META.get("HTTP_REFERER", "/"))


class ClearParlayView(LoginRequiredMixin, View):
    def post(self, request):
        request.session[PARLAY_SESSION_KEY] = []
        request.session.modified = True

        if getattr(request, "htmx", False):
            return render(request, "nba_betting/partials/parlay_slip.html")
        return redirect(request.META.get("HTTP_REFERER", "/"))


class PlaceParlayView(LoginRequiredMixin, View):
    def post(self, request):
        form = PlaceParlayForm(request.POST)
        if not form.is_valid():
            return HttpResponse("Invalid stake", status=400)

        stake = form.cleaned_data["stake"]
        slip = request.session.get(PARLAY_SESSION_KEY, [])

        if len(slip) < PARLAY_MIN_LEGS:
            return HttpResponse("Not enough legs", status=400)

        combined_decimal = Decimal("1")
        for entry in slip:
            if entry.get("odds"):
                combined_decimal *= american_to_decimal(int(entry["odds"]))

        combined_odds = decimal_to_american(combined_decimal)
        max_payout = calculate_payout(stake, combined_odds)
        cap = Decimal("10000.00")
        max_payout = min(max_payout, cap)

        with transaction.atomic():
            try:
                log_transaction(
                    request.user,
                    -stake,
                    BalanceTransaction.Type.PARLAY_PLACEMENT,
                    f"Parlay: {len(slip)} legs",
                )
            except ValueError:
                return HttpResponse("Insufficient balance", status=400)

            parlay = Parlay.objects.create(
                user=request.user,
                stake=stake,
                combined_odds=combined_odds,
                max_payout=max_payout,
            )

            for entry in slip:
                ParlayLeg.objects.create(
                    parlay=parlay,
                    game_id=entry["game_id"],
                    market=entry.get("market", "MONEYLINE"),
                    selection=entry.get("selection", "HOME"),
                    line=entry.get("line"),
                    odds_at_placement=entry.get("odds", 0),
                )

        _user = request.user
        _ctx = {
            "stake": stake,
            "leg_count": len(slip),
            "combined_odds": combined_odds,
            "league": "nba",
        }
        transaction.on_commit(
            lambda: update_challenge_progress(_user, "parlay_placed", _ctx)
        )

        request.session[PARLAY_SESSION_KEY] = []
        request.session.modified = True

        if getattr(request, "htmx", False):
            return render(
                request,
                "nba_betting/partials/parlay_confirmation.html",
                {"parlay": parlay},
            )
        return redirect("nba_betting:my_bets")


# Market+selection → Odds model field (reuses QuickBetFormView mapping)
_MARKET_ODDS_MAP = {
    ("MONEYLINE", "HOME"): "home_moneyline",
    ("MONEYLINE", "AWAY"): "away_moneyline",
    ("SPREAD", "HOME"): "spread_home",
    ("SPREAD", "AWAY"): "spread_away",
    ("TOTAL", "OVER"): "over_odds",
    ("TOTAL", "UNDER"): "under_odds",
}

# Market+selection → line field (when applicable)
_MARKET_LINE_MAP = {
    "SPREAD": "spread_line",
    "TOTAL": "total_line",
}


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
            league="nba",
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
        leg_data = []
        for leg in legs:
            try:
                game = Game.objects.select_related("home_team", "away_team").get(
                    pk=leg.event_id, status=GameStatus.SCHEDULED
                )
            except Game.DoesNotExist:
                return render(
                    request,
                    "vinosports/betting/featured_parlay_card.html",
                    {
                        "parlay": fp,
                        "featured_error": f"{leg.event_label} is no longer accepting bets.",
                    },
                )

            market = leg.extras_json.get("market", "MONEYLINE")
            selection = leg.selection
            odds_field = _MARKET_ODDS_MAP.get((market, selection))
            if not odds_field:
                return render(
                    request,
                    "vinosports/betting/featured_parlay_card.html",
                    {"parlay": fp, "featured_error": "Invalid selection in parlay."},
                )

            best_odds_row = game.odds.order_by("-fetched_at").first()
            current_odds = (
                getattr(best_odds_row, odds_field, None) if best_odds_row else None
            )
            if not current_odds:
                return render(
                    request,
                    "vinosports/betting/featured_parlay_card.html",
                    {
                        "parlay": fp,
                        "featured_error": f"No odds available for {leg.event_label}.",
                    },
                )

            line = None
            line_field = _MARKET_LINE_MAP.get(market)
            if line_field and best_odds_row:
                line = getattr(best_odds_row, line_field, None)
                # Spread away line is the inverse of the home line
                if market == "SPREAD" and selection == "AWAY" and line is not None:
                    line = -line

            leg_data.append(
                {
                    "game": game,
                    "market": market,
                    "selection": selection,
                    "odds": current_odds,
                    "line": line,
                }
            )

        # Compute combined odds (American → decimal → multiply → back to American)
        combined_decimal = Decimal("1")
        for ld in leg_data:
            combined_decimal *= american_to_decimal(int(ld["odds"]))

        combined_odds = decimal_to_american(combined_decimal)
        max_payout = min(calculate_payout(stake, combined_odds), Decimal("10000.00"))

        try:
            balance_obj = log_transaction(
                request.user,
                -stake,
                BalanceTransaction.Type.PARLAY_PLACEMENT,
                f"Featured parlay: {fp.title}",
            )
        except ValueError:
            return render(
                request,
                "vinosports/betting/featured_parlay_card.html",
                {"parlay": fp, "featured_error": "Insufficient balance."},
            )

        parlay = Parlay.objects.create(
            user=request.user,
            stake=stake,
            combined_odds=combined_odds,
            max_payout=max_payout,
            featured_parlay=fp,
        )
        ParlayLeg.objects.bulk_create(
            [
                ParlayLeg(
                    parlay=parlay,
                    game=ld["game"],
                    market=ld["market"],
                    selection=ld["selection"],
                    line=ld["line"],
                    odds_at_placement=ld["odds"],
                )
                for ld in leg_data
            ]
        )

        _user = request.user
        _ctx = {
            "stake": stake,
            "leg_count": len(leg_data),
            "combined_odds": combined_odds,
            "league": "nba",
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
                "potential_payout": max_payout,
                "stake": stake,
                "balance": balance_obj.balance,
                "my_bets_url": "nba_betting:my_bets",
            },
        )


# ---------------------------------------------------------------------------
# Futures views
# ---------------------------------------------------------------------------


class FuturesListView(TemplateView):
    """List all open futures markets for the current season."""

    template_name = "nba_betting/futures/futures_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from vinosports.betting.models import FuturesMarketStatus

        today = timezone.now().date()
        season = str(today.year if today.month >= 10 else today.year - 1)

        markets = FuturesMarket.objects.filter(
            season=season,
            status=FuturesMarketStatus.OPEN,
        ).order_by("market_type")

        markets_with_outcomes = []
        for market in markets:
            outcomes = (
                FuturesOutcome.objects.filter(market=market, is_active=True)
                .select_related("team")
                .order_by("odds")[:10]
            )
            markets_with_outcomes.append({"market": market, "outcomes": outcomes})

        ctx["markets"] = markets_with_outcomes
        return ctx


class FuturesMarketDetailView(TemplateView):
    """Show all outcomes for a single futures market."""

    template_name = "nba_betting/futures/futures_detail.html"

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
        form = PlaceFuturesBetForm()
        return render(
            request,
            "nba_betting/futures/partials/_bet_form.html",
            {"outcome": outcome, "form": form},
        )


class PlaceFuturesBetView(LoginRequiredMixin, View):
    """Handle futures bet placement via HTMX POST."""

    def post(self, request, id_hash):
        outcome = get_object_or_404(
            FuturesOutcome.objects.select_related("market", "team"),
            id_hash=id_hash,
        )

        from vinosports.betting.models import FuturesMarketStatus

        if outcome.market.status != FuturesMarketStatus.OPEN:
            return render(
                request,
                "nba_betting/futures/partials/_bet_form.html",
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
                "nba_betting/futures/partials/_bet_form.html",
                {"outcome": outcome, "form": form, "error": "Invalid stake."},
            )

        stake = form.cleaned_data["stake"]

        try:
            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(user=request.user)
                if balance.balance < stake:
                    return render(
                        request,
                        "nba_betting/futures/partials/_bet_form.html",
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
                    f"Futures bet: {outcome.team.name} to win {outcome.market.name}",
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
                "nba_betting/futures/partials/_bet_form.html",
                {
                    "outcome": outcome,
                    "form": form,
                    "error": "Something went wrong. Please try again.",
                },
            )

        potential_payout = bet.calculate_payout()

        return render(
            request,
            "nba_betting/futures/partials/_bet_confirmation.html",
            {
                "bet": bet,
                "outcome": outcome,
                "potential_payout": potential_payout,
                "balance": UserBalance.objects.get(user=request.user).balance,
            },
        )
