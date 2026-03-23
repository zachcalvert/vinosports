from decimal import Decimal

from betting.models import BetSlip
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Count, Q, Sum

from vinosports.betting.models import BetStatus, UserStats

User = get_user_model()


class Command(BaseCommand):
    help = "Recalculate UserStats from settled bet history (safe no-op if no bets)"

    def handle(self, *args, **options):
        users_with_bets = User.objects.filter(
            bet_slips__status__in=[BetStatus.WON, BetStatus.LOST],
        ).distinct()

        count = users_with_bets.count()
        if not count:
            self.stdout.write(self.style.WARNING("  Stats: no settled bets found"))
            return

        updated = 0
        for user in users_with_bets.iterator():
            agg = BetSlip.objects.filter(
                user=user,
                status__in=[BetStatus.WON, BetStatus.LOST],
            ).aggregate(
                total_bets=Count("pk"),
                total_wins=Count("pk", filter=Q(status=BetStatus.WON)),
                total_losses=Count("pk", filter=Q(status=BetStatus.LOST)),
                total_staked=Sum("stake"),
                total_payout=Sum("payout"),
            )

            total_staked = agg["total_staked"] or Decimal("0")
            total_payout = agg["total_payout"] or Decimal("0")

            UserStats.objects.update_or_create(
                user=user,
                defaults={
                    "total_bets": agg["total_bets"],
                    "total_wins": agg["total_wins"],
                    "total_losses": agg["total_losses"],
                    "total_staked": total_staked,
                    "total_payout": total_payout,
                    "net_profit": total_payout - total_staked,
                },
            )
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"  Stats: backfilled for {updated} users")
        )
