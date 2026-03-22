from decimal import Decimal

from vinosports.betting.models import BalanceTransaction


def log_transaction(user_balance, amount, transaction_type, description=""):
    """Atomically modify a UserBalance and create a BalanceTransaction log entry.

    MUST be called inside a transaction.atomic() block with user_balance
    already locked via select_for_update().

    Args:
        user_balance: UserBalance instance (already locked)
        amount: Decimal, signed (+credit, -debit)
        transaction_type: BalanceTransaction.Type value
        description: optional human-readable note
    """
    amount = Decimal(str(amount))
    user_balance.balance += amount
    user_balance.save(update_fields=["balance"])

    BalanceTransaction.objects.create(
        user=user_balance.user,
        amount=amount,
        balance_after=user_balance.balance,
        transaction_type=transaction_type,
        description=description,
    )
