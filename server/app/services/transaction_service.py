from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.trading_account import TradingAccount
from app.models.transaction import Transaction


def generate_transaction_reference() -> str:
    return f"TXN-{uuid4().hex[:12].upper()}"


def create_transaction(
    db: Session,
    user_id: int,
    trading_account_id: int,
    transaction_type: str,
    amount: Decimal,
    currency: str = "USD",
    status: str = "completed",
    description: str | None = None,
) -> Transaction:
    transaction = Transaction(
        user_id=user_id,
        trading_account_id=trading_account_id,
        transaction_type=transaction_type,
        amount=amount,
        currency=currency,
        status=status,
        reference=generate_transaction_reference(),
        description=description,
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return transaction


def get_user_transactions(
    db: Session,
    user_id: int,
) -> list[Transaction]:
    return (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .all()
    )