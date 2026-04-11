from django.contrib import admin
from django.db import transaction
from django.utils import timezone

from vinosports.betting.balance import log_transaction
from vinosports.betting.models import (
    BalanceTransaction,
    BetStatus,
    PropBet,
    PropBetSlip,
    UserBalance,
)


@admin.register(PropBet)
class PropBetAdmin(admin.ModelAdmin):
    list_display = ["title", "creator", "status", "open_at", "close_at", "settled_at"]
    list_filter = ["status"]
    search_fields = ["title", "creator__email"]
    raw_id_fields = ["creator", "settled_by"]
    readonly_fields = ["id_hash", "settled_at"]

    actions = ["settle_yes", "settle_no", "cancel_prop"]

    def _ensure_superuser(self, request):
        if not request.user.is_superuser:
            self.message_user(
                request, "Only superusers may settle prop bets.", level=40
            )
            return False
        return True

    def _settle(self, request, queryset, outcome: bool):
        """Settle props and pay out winning bets.

        outcome: True = YES wins, False = NO wins.
        """
        if not self._ensure_superuser(request):
            return

        now = timezone.now()
        winning_selection = "YES" if outcome else "NO"
        settled_count = 0

        for prop in queryset.filter(status__in=["OPEN", "CLOSED"]):
            prop.settled_outcome = outcome
            prop.status = "SETTLED"
            prop.settled_by = request.user
            prop.settled_at = now
            prop.save(
                update_fields=["settled_outcome", "status", "settled_by", "settled_at"]
            )

            # Pay out winners, mark losers
            for bet in prop.bets.filter(status=BetStatus.PENDING).select_related(
                "user"
            ):
                with transaction.atomic():
                    if bet.selection == winning_selection:
                        payout = bet.stake * bet.odds
                        bet.status = BetStatus.WON
                        bet.payout = payout
                        bet.save(update_fields=["status", "payout"])

                        balance = UserBalance.objects.select_for_update().get(
                            user=bet.user
                        )
                        log_transaction(
                            balance,
                            payout,
                            BalanceTransaction.Type.BET_WIN,
                            f"Prop bet won: {prop.title}",
                        )
                    else:
                        bet.status = BetStatus.LOST
                        bet.payout = 0
                        bet.save(update_fields=["status", "payout"])

            settled_count += 1

        self.message_user(
            request,
            f"Settled {settled_count} prop(s) as {winning_selection}.",
        )

    def settle_yes(self, request, queryset):
        self._settle(request, queryset, outcome=True)

    settle_yes.short_description = "Settle as YES (pay YES bettors)"

    def settle_no(self, request, queryset):
        self._settle(request, queryset, outcome=False)

    settle_no.short_description = "Settle as NO (pay NO bettors)"

    def cancel_prop(self, request, queryset):
        """Cancel props and refund all pending bets."""
        if not self._ensure_superuser(request):
            return

        cancelled = 0
        for prop in queryset.exclude(status="SETTLED"):
            prop.status = "CANCELLED"
            prop.save(update_fields=["status"])

            for bet in prop.bets.filter(status=BetStatus.PENDING).select_related(
                "user"
            ):
                with transaction.atomic():
                    bet.status = BetStatus.VOID
                    bet.payout = bet.stake
                    bet.save(update_fields=["status", "payout"])

                    balance = UserBalance.objects.select_for_update().get(user=bet.user)
                    log_transaction(
                        balance,
                        bet.stake,
                        BalanceTransaction.Type.BET_VOID,
                        f"Prop bet cancelled: {prop.title}",
                    )

            cancelled += 1

        self.message_user(request, f"Cancelled {cancelled} prop(s), bets refunded.")

    cancel_prop.short_description = "Cancel & refund all bets"


@admin.register(PropBetSlip)
class PropBetSlipAdmin(admin.ModelAdmin):
    list_display = ["user", "prop", "selection", "odds", "stake", "status", "payout"]
    list_filter = ["status", "selection"]
    search_fields = ["user__email", "prop__title"]
    raw_id_fields = ["user", "prop"]
