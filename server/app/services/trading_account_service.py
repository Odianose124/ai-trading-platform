from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.trading_account import TradingAccount
from app.models.transaction import Transaction
from app.services.transaction_service import generate_transaction_reference


def create_trading_account(
    db: Session,
    user_id: int,
) -> TradingAccount:
    trading_account = TradingAccount(
        user_id=user_id,
        balance=Decimal("0.00"),
        available_balance=Decimal("0.00"),
        currency="USD",
    )

    db.add(trading_account)
    db.commit()
    db.refresh(trading_account)

    return trading_account


def get_trading_account(
    db: Session,
    user_id: int,
) -> TradingAccount | None:
    return (
        db.query(TradingAccount)
        .filter(TradingAccount.user_id == user_id)
        .first()
    )


def deposit_funds(
    db: Session,
    user_id: int,
    amount: Decimal,
) -> TradingAccount:
    trading_account = get_trading_account(db, user_id)

    if trading_account is None:
        raise ValueError("Trading account not found")

    trading_account.balance += amount
    trading_account.available_balance += amount

    transaction = Transaction(
        user_id=user_id,
        trading_account_id=trading_account.id,
        transaction_type="deposit",
        amount=amount,
        currency=trading_account.currency,
        status="completed",
        reference=generate_transaction_reference(),
        description="Account deposit",
    )

    db.add(transaction)
    db.commit()
    db.refresh(trading_account)

    return trading_account


def withdraw_funds(
    db: Session,
    user_id: int,
    amount: Decimal,
) -> TradingAccount:
    trading_account = get_trading_account(db, user_id)

    if trading_account is None:
        raise ValueError("Trading account not found")

    if amount > trading_account.available_balance:
        raise ValueError("Insufficient available balance")

    trading_account.balance -= amount
    trading_account.available_balance -= amount

    transaction = Transaction(
        user_id=user_id,
        trading_account_id=trading_account.id,
        transaction_type="withdrawal",
        amount=amount,
        currency=trading_account.currency,
        status="completed",
        reference=generate_transaction_reference(),
        description="Account withdrawal",
    )

    db.add(transaction)
    db.commit()
    db.refresh(trading_account)

    return trading_account