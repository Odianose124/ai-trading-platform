from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.order import Order
from app.services.order_service import close_order


def check_order_trigger(
    order: Order,
    market_price: Decimal,
) -> str | None:
    if order.status != "open":
        return None

    if order.side == "buy":
        if order.stop_loss is not None and market_price <= order.stop_loss:
            return "stop_loss"

        if order.take_profit is not None and market_price >= order.take_profit:
            return "take_profit"

    elif order.side == "sell":
        if order.stop_loss is not None and market_price >= order.stop_loss:
            return "stop_loss"

        if order.take_profit is not None and market_price <= order.take_profit:
            return "take_profit"

    return None


def process_order_price(
    db: Session,
    order: Order,
    market_price: Decimal,
) -> Order | None:
    close_reason = check_order_trigger(
        order=order,
        market_price=market_price,
    )

    if close_reason is None:
        return None

    return close_order(
        db=db,
        user_id=order.user_id,
        order_id=order.id,
        close_price=market_price,
        close_reason=close_reason,
    )


def process_open_orders(
    db: Session,
    market_prices: dict[str, Decimal],
) -> list[Order]:
    open_orders = (
        db.query(Order)
        .filter(Order.status == "open")
        .all()
    )

    closed_orders: list[Order] = []

    for order in open_orders:
        market_price = market_prices.get(order.symbol)

        if market_price is None:
            continue

        closed_order = process_order_price(
            db=db,
            order=order,
            market_price=market_price,
        )

        if closed_order is not None:
            closed_orders.append(closed_order)

    return closed_orders