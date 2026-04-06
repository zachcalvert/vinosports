import logging
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Min
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import TemplateView

from vinosports.betting.balance import log_transaction
from vinosports.betting.models import BalanceTransaction, UserBalance
from worldcup.betting.forms import PlaceBetForm
from worldcup.betting.models import BetSlip
from worldcup.matches.models import Match, Odds
from worldcup.website.templatetags.currency_tags import format_currency

logger = logging.getLogger(__name__)

ODDS_FIELD_MAP = {
    "HOME_WIN": "home_win",
    "DRAW": "draw",
    "AWAY_WIN": "away_win",
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

        matches_with_odds = []
        for match in upcoming:
            odds = match.odds.first()
            matches_with_odds.append({"match": match, "odds": odds})

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

        return render(
            request,
            "worldcup_betting/partials/bet_confirmation.html",
            {
                "bet": bet,
                "match": match,
                "potential_payout": potential_payout,
                "balance": balance.balance,
            },
        )
