from datetime import datetime, timezone
from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.market_data import market_data_manager
from app.core.auth import get_current_user
from app.database.connection import get_db
from app.models.order import Order
from app.models.transaction import Transaction
from app.models.user import User
from app.services.execution_gate_service import (
    evaluate_execution_gate,
    serialize_execution_decision,
)
from app.services.timeframe_service import TIMEFRAME_MINUTES
from app.services.trade_setup_service import analyze_trade_setup
from app.services.trading_account_service import get_trading_account


router = APIRouter(
    prefix="/api/execution",
    tags=["Execution"],
)


def calculate_daily_loss(
    db: Session,
    user_id: int,
) -> Decimal:
    """
    Calculate today's realized trading losses.

    Only negative trade transactions are included.
    Deposits and withdrawals are excluded.
    """

    now = datetime.now(timezone.utc)

    day_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    result = (
        db.query(
            func.coalesce(
                func.sum(Transaction.amount),
                0,
            )
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "trade",
            Transaction.created_at >= day_start,
            Transaction.amount < 0,
        )
        .scalar()
    )

    return abs(
        Decimal(
            str(result or 0)
        )
    )


def calculate_total_open_exposure(
    db: Session,
    user_id: int,
) -> Decimal:
    """
    Calculate the notional value of all currently open positions.
    """

    open_orders = (
        db.query(Order)
        .filter(
            Order.user_id == user_id,
            Order.status == "open",
        )
        .all()
    )

    total_exposure = Decimal("0.00")

    for order in open_orders:
        quantity = Decimal(
            str(order.quantity)
        )

        entry_price = Decimal(
            str(order.entry_price)
        )

        total_exposure += (
            quantity * entry_price
        )

    return total_exposure


@router.get(
    "/decision/{symbol}/{timeframe}"
)
async def get_execution_decision(
    symbol: str,
    timeframe: str,
    risk_percent: Decimal = Query(
        default=Decimal("1.00"),
        gt=0,
        le=Decimal("2.00"),
    ),
    leverage: Decimal = Query(
        default=Decimal("1.00"),
        gt=0,
        le=Decimal("1000.00"),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    normalized_symbol = symbol.strip().upper()

    normalized_timeframe = (
        timeframe.strip().lower()
    )

    # ---------------------------------------------------------
    # TIMEFRAME VALIDATION
    # ---------------------------------------------------------

    if normalized_timeframe not in TIMEFRAME_MINUTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported timeframe: "
                f"{normalized_timeframe}. "
                f"Supported timeframes: "
                f"{', '.join(TIMEFRAME_MINUTES.keys())}"
            ),
        )

    # ---------------------------------------------------------
    # ACCOUNT VALIDATION
    # ---------------------------------------------------------

    account = get_trading_account(
        db=db,
        user_id=current_user.id,
    )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trading account not found",
        )

    # ---------------------------------------------------------
    # LIVE MARKET PRICE
    # ---------------------------------------------------------

    current_price = market_data_manager.get_price(
        normalized_symbol
    )

    if current_price is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"No live market price is currently "
                f"available for {normalized_symbol}"
            ),
        )

    # ---------------------------------------------------------
    # TRADE SETUP ANALYSIS
    # ---------------------------------------------------------

    try:
        setup = analyze_trade_setup(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            current_price=current_price,
            db=db,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # ---------------------------------------------------------
    # RISK CONTEXT
    # ---------------------------------------------------------

    daily_loss_amount = calculate_daily_loss(
        db=db,
        user_id=current_user.id,
    )

    total_exposure_amount = (
        calculate_total_open_exposure(
            db=db,
            user_id=current_user.id,
        )
    )

    # ---------------------------------------------------------
    # EXECUTION GATE
    # ---------------------------------------------------------

    decision = evaluate_execution_gate(
        setup=setup,

        account_balance=Decimal(
            str(account.balance)
        ),

        available_balance=Decimal(
            str(account.available_balance)
        ),

        daily_loss_amount=daily_loss_amount,

        total_exposure_amount=(
            total_exposure_amount
        ),

        risk_percent=risk_percent,

        leverage=leverage,
    )

    # ---------------------------------------------------------
    # SERIALIZE RESPONSE
    # ---------------------------------------------------------

    response = serialize_execution_decision(
        decision
    )

    response["market"] = {
        "symbol": normalized_symbol,
        "current_price": current_price,
        "source": "Binance",
    }

    response["account"] = {
        "id": account.id,
        "balance": account.balance,
        "available_balance": account.available_balance,
        "currency": account.currency,
    }

    response["risk_context"] = {
        "risk_percent": risk_percent,
        "leverage": leverage,
        "daily_loss_amount": daily_loss_amount,
        "total_open_exposure": (
            total_exposure_amount
        ),
    }

    response["execution_status"] = (
        "approved"
        if decision.execution_allowed
        else "blocked"
    )

    return response