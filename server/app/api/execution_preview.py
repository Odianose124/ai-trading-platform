from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.mt5_trading_account import MT5TradingAccount
from app.models.user import User
from app.services.execution_preview_service import (
    ExecutionPreviewError,
    execution_preview_service,
)
from app.core.auth import get_current_user


router = APIRouter(
    prefix="/api/execution",
    tags=["Execution Preview"],
)


class ExecutionPreviewRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30)
    direction: str = Field(..., min_length=1, max_length=10)

    volume: Decimal = Field(..., gt=0)

    signal_entry_price: Decimal = Field(..., gt=0)
    stop_loss: Decimal = Field(..., gt=0)
    take_profit: Decimal = Field(..., gt=0)

    risk_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )


@router.post(
    "/preview",
    status_code=status.HTTP_200_OK,
)
def create_execution_preview(
    payload: ExecutionPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a live execution preview.

    IMPORTANT:
    This endpoint DOES NOT send an MT5 order.
    """

    mt5_account = (
        db.query(MT5TradingAccount)
        .filter(
            MT5TradingAccount.user_id == current_user.id,
            MT5TradingAccount.is_active.is_(True),
        )
        .first()
    )

    if mt5_account is None or mt5_account.id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active MT5 trading account not found.",
        )

    try:
        preview = execution_preview_service.preview(
            mt5_account_id=mt5_account.id,
            user_id=current_user.id,
            symbol=payload.symbol,
            direction=payload.direction,
            volume=payload.volume,
            signal_entry_price=payload.signal_entry_price,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
            risk_percent=payload.risk_percent,
        )

        return preview.serialize()

    except ExecutionPreviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution preview failed: {str(exc)}",
        ) from exc
