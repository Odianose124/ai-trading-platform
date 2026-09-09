from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.models.order import Order
from app.models.transaction import Transaction
from app.models.user import User
from app.services.risk_management_service import (
    assess_risk,
    serialize_risk_assessment,
)
from app.services.trading_account_service import get_trading_account


router = APIRouter(
    prefix="/api/risk-management",
    tags=["Risk Management"],
)


class RiskAssessmentRequest(BaseModel):
    direction: str = Field(
        min_length=1,
        max_length=10,
    )

    entry_price: Decimal = Field(gt=0)

    stop_loss: Decimal = Field(gt=0)

    take_profit_1: Decimal = Field(gt=0)

    take_profit_2: Decimal = Field(gt=0)

    risk_percent: Decimal = Field(
        default=Decimal("1.00"),
        gt=0,
        le=Decimal("2.00"),
    )

    leverage: Decimal = Field(
        default=Decimal("1.00"),
        gt=0,
        le=Decimal("1000.00"),
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

    from datetime import datetime, timezone

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


def calculate_total_exposure(
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


@router.post("/assess")
def assess_current_trade_risk(
    risk_data: RiskAssessmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = get_trading_account(
        db=db,
        user_id=current_user.id,
    )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trading account not found",
        )

    daily_loss_amount = calculate_daily_loss(
        db=db,
        user_id=current_user.id,
    )

    total_exposure_amount = calculate_total_exposure(
        db=db,
        user_id=current_user.id,
    )

    assessment = assess_risk(
        account_balance=Decimal(
            str(account.balance)
        ),
        available_balance=Decimal(
            str(account.available_balance)
        ),
        entry_price=risk_data.entry_price,
        stop_loss=risk_data.stop_loss,
        take_profit_1=risk_data.take_profit_1,
        take_profit_2=risk_data.take_profit_2,
        risk_percent=risk_data.risk_percent,
        daily_loss_amount=daily_loss_amount,
        total_exposure_amount=total_exposure_amount,
        leverage=risk_data.leverage,
        direction=risk_data.direction,
    )

    response = serialize_risk_assessment(
        assessment
    )

    response["account"] = {
        "id": account.id,
        "balance": account.balance,
        "available_balance": account.available_balance,
        "currency": account.currency,
    }

    response["risk_context"] = {
        "daily_loss_amount": daily_loss_amount,
        "total_open_exposure": total_exposure_amount,
    }

    return response


@router.get("/account")
def get_risk_account_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = get_trading_account(
        db=db,
        user_id=current_user.id,
    )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trading account not found",
        )

    daily_loss_amount = calculate_daily_loss(
        db=db,
        user_id=current_user.id,
    )

    total_exposure_amount = calculate_total_exposure(
        db=db,
        user_id=current_user.id,
    )

    return {
        "account_id": account.id,
        "balance": account.balance,
        "available_balance": account.available_balance,
        "currency": account.currency,
        "daily_loss_amount": daily_loss_amount,
        "total_open_exposure": total_exposure_amount,
        "daily_loss_limit_percent": Decimal("5.00"),
        "maximum_exposure_percent": Decimal("1000.00"),
        "maximum_exposure_multiple": Decimal("10.00"),
        "default_leverage": Decimal("1.00"),
    }