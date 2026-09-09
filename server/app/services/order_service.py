from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.trading_account import TradingAccount
from app.models.transaction import Transaction
from app.schemas.order import OrderCreate


def generate_order_reference() -> str:
    return f"ORD-{uuid4().hex[:12].upper()}"


def calculate_order_cost(
    quantity: Decimal,
    entry_price: Decimal,
) -> Decimal:
    return quantity * entry_price


def calculate_profit_loss(
    side: str,
    quantity: Decimal,
    entry_price: Decimal,
    close_price: Decimal,
) -> Decimal:
    if side == "buy":
        return (close_price - entry_price) * quantity

    if side == "sell":
        return (entry_price - close_price) * quantity

    raise ValueError("Invalid order side")


def create_order(
    db: Session,
    user_id: int,
    order_data: OrderCreate,
) -> Order:
    account = (
        db.query(TradingAccount)
        .filter(TradingAccount.user_id == user_id)
        .first()
    )

    if account is None:
        raise ValueError("Trading account not found")

    order_cost = calculate_order_cost(
        order_data.quantity,
        order_data.entry_price,
    )

    if account.available_balance < order_cost:
        raise ValueError("Insufficient available balance")

    order = Order(
        user_id=user_id,
        trading_account_id=account.id,
        symbol=order_data.symbol,
        side=order_data.side,
        quantity=order_data.quantity,
        entry_price=order_data.entry_price,
        stop_loss=order_data.stop_loss,
        take_profit=order_data.take_profit,
        status="open",
        profit_loss=Decimal("0.00"),
    )

    account.available_balance -= order_cost

    db.add(order)
    db.commit()
    db.refresh(order)

    return order


def close_order(
    db: Session,
    user_id: int,
    order_id: int,
    close_price: Decimal,
    close_reason: str = "manual",
) -> Order:
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.user_id == user_id,
        )
        .first()
    )

    if order is None:
        raise ValueError("Order not found")

    if order.status != "open":
        raise ValueError("Order is already closed")

    if close_reason not in {"manual", "stop_loss", "take_profit"}:
        raise ValueError("Invalid close reason")

    account = (
        db.query(TradingAccount)
        .filter(
            TradingAccount.id == order.trading_account_id,
            TradingAccount.user_id == user_id,
        )
        .first()
    )

    if account is None:
        raise ValueError("Trading account not found")

    profit_loss = calculate_profit_loss(
        side=order.side,
        quantity=order.quantity,
        entry_price=order.entry_price,
        close_price=close_price,
    )

    reserved_amount = calculate_order_cost(
        order.quantity,
        order.entry_price,
    )

    returned_amount = reserved_amount + profit_loss

    if returned_amount < Decimal("0.00"):
        raise ValueError("Calculated closing amount cannot be negative")

    order.profit_loss = profit_loss
    order.status = "closed"
    order.closed_at = datetime.now(timezone.utc)

    account.balance += profit_loss
    account.available_balance += returned_amount

    transaction = Transaction(
        user_id=user_id,
        trading_account_id=account.id,
        transaction_type="trade",
        amount=profit_loss,
        currency=account.currency,
        status="completed",
        reference=f"TRD-{uuid4().hex[:12].upper()}",
        description=(
            f"Closed {order.side.upper()} {order.symbol} order #{order.id} "
            f"at {close_price} "
            f"({close_reason.replace('_', ' ')})"
        ),
    )

    db.add(transaction)

    try:
        db.commit()
        db.refresh(order)
    except Exception:
        db.rollback()
        raise

    return order


def get_user_orders(
    db: Session,
    user_id: int,
) -> list[Order]:
    return (
        db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.opened_at.desc())
        .all()
    )


def get_user_order(
    db: Session,
    user_id: int,
    order_id: int,
) -> Order | None:
    return (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.user_id == user_id,
        )
        .first()
    )