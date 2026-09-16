from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database.connection import get_db
from app.services.trade_intent_service import (
    TradeIntentError,
    trade_intent_service,
)


router = APIRouter(
    prefix="/api/trade-intents",
    tags=["Trade Intents"],
)


class CreateTradeIntentRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=50)
    broker_symbol: str = Field(min_length=1, max_length=100)
    direction: str = Field(min_length=1, max_length=20)
    volume: Decimal = Field(gt=0)
    signal_entry_price: Decimal = Field(gt=0)
    execution_price: Decimal = Field(gt=0)
    stop_loss: Decimal = Field(gt=0)
    take_profit: Decimal = Field(gt=0)
    risk_percent: Decimal | None = Field(
        default=None,
        gt=0,
        le=100,
    )
    ai_management_enabled: bool = True
    signal_price_deviation_percent: Decimal | None = Field(
        default=None,
        ge=0,
    )
    margin_required: Decimal | None = Field(
        default=None,
        ge=0,
    )
    free_margin: Decimal | None = Field(
        default=None,
        ge=0,
    )
    preview_status: str = Field(
        default="ready_for_confirmation",
        min_length=1,
        max_length=50,
    )
    warnings: list[str] = Field(default_factory=list)


@router.post("")
def create_trade_intent(
    request: CreateTradeIntentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        result = trade_intent_service.create(
            db=db,
            user_id=current_user.id,
            symbol=request.symbol,
            broker_symbol=request.broker_symbol,
            direction=request.direction,
            volume=request.volume,
            signal_entry_price=request.signal_entry_price,
            execution_price=request.execution_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            risk_percent=request.risk_percent,
            ai_management_enabled=request.ai_management_enabled,
            signal_price_deviation_percent=(
                request.signal_price_deviation_percent
            ),
            margin_required=request.margin_required,
            free_margin=request.free_margin,
            preview_status=request.preview_status,
            warnings=request.warnings,
        )

        return result.serialize()

    except TradeIntentError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get("/{intent_id}")
def get_trade_intent(
    intent_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Read-only trade-intent endpoint.

    This endpoint MUST NOT validate, confirm, expire, execute,
    or otherwise consume the trade intent.
    """
    try:
        result = trade_intent_service.get_intent(
            db=db,
            intent_id=intent_id,
            user_id=current_user.id,
        )

        return result.serialize()

    except TradeIntentError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
