"""
One-time management command to grant every existing user a $100,000 starter bonus.

Idempotent: skips users who already received the bonus (matched by description).

Usage:
    python manage.py backfill_starter_bonus
    python manage.py backfill_starter_bonus --dry-run
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from vinosports.betting.balance import log_transaction
from vinosports.betting.models import BalanceTransaction, UserBalance

BONUS_AMOUNT = Decimal("100000.00")
DESCRIPTION = "One-time starter bonus backfill"


class Command(BaseCommand):
    help = "Grant every existing user a $100,000 starter bonus (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without making changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Find users who already received this bonus
        already_received = set(
            BalanceTransaction.objects.filter(
                description=DESCRIPTION,
            ).values_list("user_id", flat=True)
        )

        balances = UserBalance.objects.select_related("user").all()
        credited = 0
        skipped = 0

        for ub in balances:
            if ub.user_id in already_received:
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"  [DRY RUN] Would credit {ub.user.email}: "
                    f"+${BONUS_AMOUNT} (current: ${ub.balance})"
                )
                credited += 1
                continue

            with transaction.atomic():
                balance = UserBalance.objects.select_for_update().get(pk=ub.pk)
                log_transaction(
                    balance,
                    BONUS_AMOUNT,
                    BalanceTransaction.Type.ADMIN_RESET,
                    DESCRIPTION,
                )
            credited += 1

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Credited {credited} user(s) with ${BONUS_AMOUNT}. "
                f"Skipped {skipped} (already received)."
            )
        )
