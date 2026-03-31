"""
Compatibility wrapper around vinosports.betting.balance for NFL services.

The original log_transaction(user, amount, type, desc) handles locking
internally. The vinosports-core version requires the caller to lock first.
This wrapper preserves the simpler API.
"""

from decimal import Decimal

from django.db import transaction as db_transaction

from vinosports.betting.balance import log_transaction as _core_log_transaction
from vinosports.betting.models import BalanceTransaction, UserBalance


def log_transaction(
    user,
    amount: Decimal,
    transaction_type: str,
    description: str = "",
) -> BalanceTransaction:
    """
    Atomically update the user's balance and append a transaction record.

    Raises ValueError if the resulting balance would go negative.
    """
    with db_transaction.atomic():
        balance_obj = UserBalance.objects.select_for_update().get(user=user)
        new_balance = balance_obj.balance + Decimal(str(amount))
        if new_balance < 0:
            raise ValueError(
                f"Insufficient balance: {balance_obj.balance} + {amount} = {new_balance}"
            )
        _core_log_transaction(balance_obj, amount, transaction_type, description)
        return balance_obj
