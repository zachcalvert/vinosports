from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from nba.betting.balance import log_transaction
from nba.betting.context_processors import PARLAY_SESSION_KEY
from nba.betting.forms import PlaceBetForm, PlaceParlayForm
from nba.betting.models import BetSlip, Parlay, ParlayLeg
from nba.betting.settlement import (
    american_to_decimal,
    calculate_payout,
    decimal_to_american,
    grant_bailout,
)
from nba.games.models import Game, GameStatus
from vinosports.betting.constants import PARLAY_MAX_LEGS, PARLAY_MIN_LEGS
from vinosports.betting.models import BalanceTransaction


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


class PlaceBetView(LoginRequiredMixin, View):
    def post(self, request, id_hash):
        game = get_object_or_404(Game, id_hash=id_hash, status=GameStatus.SCHEDULED)
        form = PlaceBetForm(request.POST)

        if not form.is_valid():
            if getattr(request, "htmx", False):
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

        from nba.activity.services import queue_activity_event

        queue_activity_event(
            "user_bet",
            f"{request.user.display_name or request.user.email} bet ${stake} on {game}",
            url=game.get_absolute_url(),
            icon="coin",
        )

        if getattr(request, "htmx", False):
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

        request.session[PARLAY_SESSION_KEY] = []
        request.session.modified = True

        if getattr(request, "htmx", False):
            return render(
                request,
                "nba_betting/partials/parlay_confirmation.html",
                {"parlay": parlay},
            )
        return redirect("nba_betting:my_bets")
