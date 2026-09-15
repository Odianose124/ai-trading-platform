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
from app.execution.position_manager import PositionManager
from app.models.mt5_trading_account import MT5TradingAccount
from app.models.transaction import Transaction
from app.models.user import User
from app.mt5.connection import (
    MT5AccountMismatchError,
    MT5ConnectionError,
    mt5_connection,
)
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


position_manager = PositionManager()


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
    positions: list[dict],
) -> Decimal:
    """
    Calculate gross notional exposure from the authoritative MT5-owned
    positions returned by PositionManager.

    Only platform-owned positions are included because PositionManager
    filters by the authoritative platform magic number.
    """

    total_exposure = Decimal("0.00")

    for position in positions:
        volume = Decimal(
            str(position["volume"])
        )

        entry_price = Decimal(
            str(position["entry_price"])
        )

        total_exposure += (
            volume * entry_price
        )

    return total_exposure


def get_authoritative_mt5_context(
    db: Session,
    user_id: int,
) -> tuple[MT5TradingAccount, dict, list[dict]]:
    """
    Resolve and verify the authenticated user's registered MT5 account,
    then read the live broker account and platform-owned positions.
    """

    mt5_account = (
        db.query(MT5TradingAccount)
        .filter(
            MT5TradingAccount.user_id == user_id,
            MT5TradingAccount.is_active.is_(True),
        )
        .first()
    )

    if mt5_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active MT5 trading account not found",
        )

    try:
        broker_account = mt5_connection.verify_account(
            expected_login=mt5_account.mt5_login,
            expected_server=mt5_account.server,
        )

        positions = position_manager.get_positions()

    except MT5AccountMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except MT5ConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return (
        mt5_account,
        broker_account,
        positions,
    )


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
    # APPLICATION ACCOUNT VALIDATION
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
    # AUTHORITATIVE MT5 ACCOUNT / POSITION CONTEXT
    # ---------------------------------------------------------

    (
        mt5_account,
        broker_account,
        positions,
    ) = get_authoritative_mt5_context(
        db=db,
        user_id=current_user.id,
    )

    total_exposure_amount = (
        calculate_total_open_exposure(
            positions=positions,
        )
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
        ) from exc

    # ---------------------------------------------------------
    # RISK CONTEXT
    # ---------------------------------------------------------

    daily_loss_amount = calculate_daily_loss(
        db=db,
        user_id=current_user.id,
    )

    # ---------------------------------------------------------
    # EXECUTION GATE
    # ---------------------------------------------------------

    decision = evaluate_execution_gate(
        setup=setup,

        account_balance=Decimal(
            str(broker_account["balance"])
        ),

        available_balance=Decimal(
            str(broker_account["free_margin"])
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
        "balance": broker_account["balance"],
        "available_balance": broker_account["free_margin"],
        "currency": broker_account["currency"],
    }

    response["mt5_account"] = {
        "id": mt5_account.id,
        "login": mt5_account.mt5_login,
        "server": mt5_account.server,
        "currency": mt5_account.currency,
        "ownership_verified": True,
    }

    response["risk_context"] = {
        "risk_percent": risk_percent,
        "leverage": leverage,
        "daily_loss_amount": daily_loss_amount,
        "total_open_exposure": (
            total_exposure_amount
        ),
        "platform_owned_open_positions": len(
            positions
        ),
    }

    response["execution_status"] = (
        "approved"
        if decision.execution_allowed
        else "blocked"
    )

    return response